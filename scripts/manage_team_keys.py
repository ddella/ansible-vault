#!/usr/bin/env python3
"""Manage the SSH public keys allowed to decrypt an Ansible Vault master password.

The master password is stored in a base64-encoded age file (for example
.secrets/.global-ansible-vault.age), encrypted for every SSH public key listed
in a recipients file (for example .secrets/team_ssh_keys.txt).

Adding or removing a key means changing the recipients file AND re-encrypting
the master password for the new list. This script does both, safely:

  * it decrypts the current password with YOUR private key (from the kernel
    key cache, or from a key file),
  * re-encrypts it for the new list of keys,
  * checks that the result decrypts to the same password,
  * keeps backups, and only then replaces the files.

With --rotate, it also generates a NEW master password and re-encrypts the
Ansible Vault with it (ansible-vault rekey). Use it when you remove a key:
the person you removed knew the old password.

The cleartext password never touches the disk: it is passed between programs
through pipes.

Examples:
  manage_team_keys.py list
  manage_team_keys.py add ~/alice.pub
  manage_team_keys.py add "ssh-ed25519 AAAA... alice@example.com"
  manage_team_keys.py remove eve@example.com --rotate
  manage_team_keys.py remove SHA256:Xb3...
  manage_team_keys.py reencrypt
  manage_team_keys.py rotate
  manage_team_keys.py verify
"""

from __future__ import annotations

import argparse
import base64
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SUPPORTED_KEY_TYPES = ("ssh-ed25519", "ssh-rsa")
REPO_ROOT = Path(__file__).resolve().parent.parent


class KeyError_(Exception):
    """Error shown to the user without a traceback."""


# --------------------------------------------------------------------------- #
# Recipients file
# --------------------------------------------------------------------------- #
@dataclass
class KeyLine:
    lineno: int          # 1-based line number in the file
    raw: str             # original line, without the newline
    key_type: str = ""
    blob: str = ""
    comment: str = ""
    fingerprint: str = ""

    @property
    def is_key(self) -> bool:
        return bool(self.blob)


def fingerprint(key_type: str, blob: str) -> str:
    """SHA256 fingerprint of a public key, as printed by ssh-keygen -l."""
    result = subprocess.run(
        ["ssh-keygen", "-l", "-E", "sha256", "-f", "-"],
        input=f"{key_type} {blob}\n", capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise KeyError_(f"Not a valid SSH public key: {result.stderr.strip()}")
    return result.stdout.split()[1]


def parse_public_key(text: str) -> tuple[str, str, str]:
    """Return (type, blob, comment) for one public key line, or raise."""
    parts = text.strip().split(maxsplit=2)
    if len(parts) < 2:
        raise KeyError_("Not an SSH public key: expected '<type> <base64> [comment]'.")
    key_type, blob = parts[0], parts[1]
    comment = parts[2] if len(parts) == 3 else ""
    if key_type not in SUPPORTED_KEY_TYPES:
        raise KeyError_(
            f"Key type '{key_type}' is not supported by age. "
            f"Use one of: {', '.join(SUPPORTED_KEY_TYPES)}."
        )
    return key_type, blob, comment


def read_keys_file(path: Path) -> list[KeyLine]:
    if not path.exists():
        raise KeyError_(f"Recipients file not found: {path}")
    lines = []
    for n, raw in enumerate(path.read_text().splitlines(), start=1):
        line = KeyLine(lineno=n, raw=raw)
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            line.key_type, line.blob, line.comment = parse_public_key(stripped)
            line.fingerprint = fingerprint(line.key_type, line.blob)
        lines.append(line)
    return lines


def keys_text(lines: list[KeyLine]) -> str:
    return "".join(f"{line.raw}\n" for line in lines)


def find_keys(lines: list[KeyLine], selector: str) -> list[KeyLine]:
    """Match keys by fingerprint, exact comment, line number or key blob."""
    keys = [k for k in lines if k.is_key]
    if selector.isdigit():
        return [k for k in keys if k.lineno == int(selector)]
    by_fp = [k for k in keys if k.fingerprint in (selector, f"SHA256:{selector}")]
    if by_fp:
        return by_fp
    by_comment = [k for k in keys if k.comment == selector]
    if by_comment:
        return by_comment
    return [k for k in keys if k.blob == selector or f"{k.key_type} {k.blob}" in selector]


# --------------------------------------------------------------------------- #
# age helpers
# --------------------------------------------------------------------------- #
class Identity:
    """Your SSH private key, from the kernel key cache or from a file."""

    def __init__(self, args: argparse.Namespace):
        self.file = Path(args.identity).expanduser() if args.identity else None
        self.cache_script = Path(args.key_cache_script)
        self.cache_name = args.key_cache_name
        self._cached: bytes | None = None

    def describe(self) -> str:
        if self.file:
            return f"key file {self.file}"
        return f"kernel key cache '{self.cache_name}'"

    def _from_cache(self) -> bytes:
        if self._cached is None:
            result = subprocess.run(
                [sys.executable, str(self.cache_script), "get", "--name", self.cache_name],
                capture_output=True,
            )
            if result.returncode != 0 or not result.stdout.strip():
                raise KeyError_(
                    f"Could not read your SSH private key from the kernel key cache "
                    f"'{self.cache_name}': {result.stderr.decode().strip() or 'empty output'}\n"
                    f"Store it first:  {self.cache_script} store ~/.ssh/id_ed25519_vault_lab "
                    f"--hours 1 --name {self.cache_name}\n"
                    f"or pass --identity ~/.ssh/<your private key>."
                )
            self._cached = result.stdout
        return self._cached

    def run_age_decrypt(self, ciphertext: bytes) -> subprocess.CompletedProcess:
        if self.file:
            # age asks for the key's passphrase on the TTY if needed.
            return subprocess.run(["age", "-d", "-i", str(self.file)],
                                  input=ciphertext, capture_output=True)
        # Hand the cached key to age through a pipe, never through a file.
        key = self._from_cache()
        read_fd, write_fd = os.pipe()
        try:
            proc = subprocess.Popen(
                ["age", "-d", "-i", f"/dev/fd/{read_fd}"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                pass_fds=(read_fd,),
            )
            os.close(read_fd)
            read_fd = -1
            os.write(write_fd, key)
            os.close(write_fd)
            write_fd = -1
            out, err = proc.communicate(ciphertext)
            return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)
        finally:
            for fd in (read_fd, write_fd):
                if fd >= 0:
                    os.close(fd)


def decrypt_age_file(path: Path, identity: Identity) -> bytes:
    if not path.exists():
        raise KeyError_(f"Encrypted password file not found: {path}")
    try:
        ciphertext = base64.b64decode(path.read_bytes(), validate=True)
    except ValueError:
        raise KeyError_(f"{path} is not base64-encoded.") from None
    result = identity.run_age_decrypt(ciphertext)
    if result.returncode != 0:
        raise KeyError_(
            f"Could not decrypt {path} with your {identity.describe()}:\n"
            f"  {result.stderr.decode().strip()}"
        )
    return result.stdout


def encrypt_for(password: bytes, recipients: str) -> bytes:
    """Encrypt for every key in `recipients`; return base64 text, no newline."""
    with tempfile.NamedTemporaryFile("w", prefix="recipients-", suffix=".txt") as tmp:
        tmp.write(recipients)
        tmp.flush()
        result = subprocess.run(["age", "-R", tmp.name], input=password, capture_output=True)
    if result.returncode != 0:
        raise KeyError_(f"age could not encrypt the password: {result.stderr.decode().strip()}")
    return base64.b64encode(result.stdout)


# --------------------------------------------------------------------------- #
# Ansible Vault rekey (for --rotate)
# --------------------------------------------------------------------------- #
def rekey_vault(vault_file: Path, vault_id: str, old_pw: bytes, new_pw: bytes) -> None:
    """Re-encrypt vault_file from old_pw to new_pw, passing both through pipes."""
    if not vault_file.exists():
        raise KeyError_(f"Ansible Vault file not found: {vault_file}")
    old_r, old_w = os.pipe()
    new_r, new_w = os.pipe()
    env = dict(os.environ)
    # Use ONLY the old password for decryption, not the wrapper from ansible.cfg.
    env["ANSIBLE_VAULT_IDENTITY_LIST"] = f"{vault_id}@/dev/fd/{old_r}"
    try:
        proc = subprocess.Popen(
            ["ansible-vault", "rekey", "--new-vault-id", f"{vault_id}@/dev/fd/{new_r}",
             str(vault_file)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
            pass_fds=(old_r, new_r),
        )
        for fd in (old_r, new_r):
            os.close(fd)
        old_r = new_r = -1
        os.write(old_w, old_pw)
        os.close(old_w)
        os.write(new_w, new_pw)
        os.close(new_w)
        old_w = new_w = -1
        out, err = proc.communicate()
    finally:
        for fd in (old_r, old_w, new_r, new_w):
            if fd >= 0:
                os.close(fd)
    if proc.returncode != 0:
        raise KeyError_(f"ansible-vault rekey failed:\n{err.decode().strip()}")


def check_vault_opens(vault_file: Path, vault_id: str, password: bytes) -> bool:
    read_fd, write_fd = os.pipe()
    env = dict(os.environ, ANSIBLE_VAULT_IDENTITY_LIST=f"{vault_id}@/dev/fd/{read_fd}")
    proc = subprocess.Popen(["ansible-vault", "view", str(vault_file)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            env=dict(env, PAGER="cat"), pass_fds=(read_fd,))
    os.close(read_fd)
    os.write(write_fd, password)
    os.close(write_fd)
    return proc.wait() == 0


# --------------------------------------------------------------------------- #
# Safe file replacement
# --------------------------------------------------------------------------- #
def backup(path: Path, stamp: str) -> Path:
    dest = path.with_name(f"{path.name}.{stamp}.bak")
    shutil.copy2(path, dest)
    os.chmod(dest, 0o600)
    return dest


def atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def apply_change(args, identity: Identity, new_lines: list[KeyLine], rotate: bool,
                 summary: str) -> None:
    """Re-encrypt for new_lines (optionally with a new password) and save."""
    keys_file, age_file = Path(args.keys_file), Path(args.age_file)
    new_keys = keys_text(new_lines)
    count = sum(1 for k in new_lines if k.is_key)
    if count == 0:
        raise KeyError_("Refusing to leave the recipients file without any key.")

    old_pw = decrypt_age_file(age_file, identity)
    new_pw = secrets.token_urlsafe(32).encode() if rotate else old_pw
    new_age = encrypt_for(new_pw, new_keys)

    # Your own key must still be a recipient, or you would lock yourself out.
    check = identity.run_age_decrypt(base64.b64decode(new_age))
    if check.returncode != 0 or check.stdout != new_pw:
        raise KeyError_(
            "After this change, YOUR key could no longer decrypt the master password "
            "(did you remove your own key?). Nothing was changed."
        )

    print(summary)
    print(f"  Recipients after the change: {count} key(s)")
    if rotate:
        print(f"  New master password: yes; Ansible Vault {args.vault_file} will be rekeyed")
    if args.dry_run:
        print("Dry run: nothing was changed.")
        return
    if not args.yes and sys.stdin.isatty():
        if input("Apply? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Aborted: nothing was changed.")
            return

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backups = [backup(keys_file, stamp), backup(age_file, stamp)]
    vault_file = Path(args.vault_file)
    if rotate:
        backups.append(backup(vault_file, stamp))
        rekey_vault(vault_file, args.vault_id, old_pw, new_pw)
        if not check_vault_opens(vault_file, args.vault_id, new_pw):
            shutil.copy2(backups[-1], vault_file)
            raise KeyError_("The rekeyed vault doesn't open with the new password. "
                            "The vault was restored; nothing else was changed.")

    atomic_write(age_file, new_age)
    atomic_write(keys_file, new_keys.encode())

    # Final check from what is now on disk.
    if decrypt_age_file(age_file, identity) != new_pw:
        raise KeyError_(f"Verification failed. Restore from the backups:\n  "
                        + "\n  ".join(map(str, backups)))
    print("✅ Done. Backups:")
    for b in backups:
        print(f"  {b}")
    print("Delete the backups once everything works (see the guide).")


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_list(args, _identity) -> None:
    keys = [k for k in read_keys_file(Path(args.keys_file)) if k.is_key]
    print(f"{len(keys)} key(s) in {args.keys_file}:")
    for k in keys:
        print(f"  line {k.lineno:<3} {k.key_type:<12} {k.fingerprint}  {k.comment}")


def cmd_add(args, identity) -> None:
    source = args.key
    path = Path(source).expanduser()
    text = path.read_text() if path.is_file() else source
    if "PRIVATE KEY" in text:
        raise KeyError_("That is a PRIVATE key. Give the .pub file instead.")
    key_lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    if len(key_lines) != 1:
        raise KeyError_("Give exactly one public key (a .pub file or the key text).")
    key_type, blob, comment = parse_public_key(key_lines[0])
    fp = fingerprint(key_type, blob)
    if args.comment:
        comment = args.comment
    if not comment:
        raise KeyError_("The key has no comment. Add one with --comment alice@example.com "
                        "so you can recognise it later.")

    lines = read_keys_file(Path(args.keys_file))
    for k in lines:
        if k.is_key and k.blob == blob:
            raise KeyError_(f"This key is already in the file (line {k.lineno}, {k.comment}).")
    new = KeyLine(lineno=len(lines) + 1, raw=f"{key_type} {blob} {comment}",
                  key_type=key_type, blob=blob, comment=comment, fingerprint=fp)
    apply_change(args, identity, lines + [new], rotate=args.rotate,
                 summary=f"Adding {key_type} {fp} {comment}")


def cmd_remove(args, identity) -> None:
    lines = read_keys_file(Path(args.keys_file))
    matches = find_keys(lines, args.selector)
    if not matches:
        raise KeyError_(f"No key matches '{args.selector}'. Run 'list' to see the keys.")
    if len(matches) > 1:
        found = "\n".join(f"  line {k.lineno}: {k.fingerprint} {k.comment}" for k in matches)
        raise KeyError_(f"'{args.selector}' matches several keys. Use the fingerprint "
                        f"or line number:\n{found}")
    victim = matches[0]
    if not args.rotate:
        print("⚠️  Without --rotate, the removed person still knows the current master "
              "password and can open any copy of the vault. Consider --rotate.")
    new_lines = [l for l in lines if l.lineno != victim.lineno]
    apply_change(args, identity, new_lines, rotate=args.rotate,
                 summary=f"Removing line {victim.lineno}: {victim.fingerprint} {victim.comment}")


def cmd_reencrypt(args, identity) -> None:
    lines = read_keys_file(Path(args.keys_file))
    apply_change(args, identity, lines, rotate=False,
                 summary="Re-encrypting the master password for the current recipients file")


def cmd_rotate(args, identity) -> None:
    lines = read_keys_file(Path(args.keys_file))
    apply_change(args, identity, lines, rotate=True,
                 summary="Rotating the master password for the current recipients file")


def cmd_verify(args, identity) -> None:
    lines = read_keys_file(Path(args.keys_file))
    pw = decrypt_age_file(Path(args.age_file), identity)
    print(f"✅ Your {identity.describe()} decrypts {args.age_file}")
    vault_file = Path(args.vault_file)
    ok = True
    if vault_file.exists():
        ok = check_vault_opens(vault_file, args.vault_id, pw)
        print(f"{'✅' if ok else '❌'} {vault_file} {'opens' if ok else 'does NOT open'} "
              f"with that password")
    print(f"ℹ️  {sum(1 for k in lines if k.is_key)} key(s) in {args.keys_file}. "
          f"age can't tell which of them the file was encrypted for; "
          f"run 'reencrypt' after any manual edit of the recipients file.")
    if not ok:
        sys.exit(1)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    g = common.add_argument_group("files")
    g.add_argument("--keys-file", default=str(REPO_ROOT / ".secrets/team_ssh_keys.txt"),
                   help="recipients file (default: %(default)s)")
    g.add_argument("--age-file", default=str(REPO_ROOT / ".secrets/.global-ansible-vault.age"),
                   help="encrypted master password (default: %(default)s)")
    g.add_argument("--vault-file",
                   default=str(REPO_ROOT / "global_vars/global-ansible-vault-enc.yml"),
                   help="Ansible Vault rekeyed by --rotate (default: %(default)s)")
    g.add_argument("--vault-id", default="global", help="vault ID (default: %(default)s)")
    i = common.add_argument_group("your private key")
    i.add_argument("--identity", metavar="FILE",
                   help="SSH private key file (default: use the kernel key cache)")
    i.add_argument("--key-cache-name", default="global-secrets",
                   help="name in the kernel key cache (default: %(default)s)")
    i.add_argument("--key-cache-script", default=str(REPO_ROOT / "scripts/ssh_key_cache.py"),
                   help="path to ssh_key_cache.py (default: %(default)s)")
    c = common.add_argument_group("behaviour")
    c.add_argument("--dry-run", action="store_true", help="check everything, change nothing")
    c.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation")

    parser = argparse.ArgumentParser(
        description="Add or remove SSH public keys allowed to decrypt the Ansible Vault "
                    "master password, and re-encrypt it.",
        epilog="Run '<command> -h' for the options of each command.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", parents=[common], help="list the keys").set_defaults(func=cmd_list)

    p = sub.add_parser("add", parents=[common], help="add a key and re-encrypt")
    p.add_argument("key", help="a .pub file, or the public key text in quotes")
    p.add_argument("--comment", help="label for the key (replaces the key's own comment)")
    p.add_argument("--rotate", action="store_true", help="also set a new master password")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("remove", parents=[common], help="remove a key and re-encrypt")
    p.add_argument("selector", help="fingerprint (SHA256:...), exact comment, or line number")
    p.add_argument("--rotate", action="store_true",
                   help="also set a new master password and rekey the vault (recommended)")
    p.set_defaults(func=cmd_remove)

    sub.add_parser("reencrypt", parents=[common],
                   help="re-encrypt for the recipients file as it is now"
                   ).set_defaults(func=cmd_reencrypt)
    sub.add_parser("rotate", parents=[common],
                   help="set a new master password and rekey the vault"
                   ).set_defaults(func=cmd_rotate)
    sub.add_parser("verify", parents=[common],
                   help="check you can decrypt the password and open the vault"
                   ).set_defaults(func=cmd_verify)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    for tool in ("age", "ssh-keygen") + (("ansible-vault",) if args.command in
                                         ("rotate", "verify") or getattr(args, "rotate", False)
                                         else ()):
        if not shutil.which(tool):
            print(f"❌ '{tool}' not found. Run this inside the DevContainer.", file=sys.stderr)
            return 2
    os.umask(0o077)
    try:
        args.func(args, Identity(args))
    except KeyError_ as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        # Output was piped to a program that closed early (for example 'head').
        sys.stderr.close()
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted: nothing was changed unless 'Done' was printed.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
