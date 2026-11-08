#!/usr/bin/env python3
"""Decrypt an SSH private key and cache it in the kernel session keyring.

Requires: pip install keyctl2 cryptography bcrypt   (Python 3.10+, Linux)

Usage:
  ssh_key_cache.py store ~/.ssh/id_ed25519 [--hours 8] [--name sshkey]
  ssh_key_cache.py get [--name sshkey] | ssh-add -
  ssh_key_cache.py clear [--name sshkey]
  ssh_key_cache.py show [--name sshkey]

Allow the syscalls in the container. In .devcontainer/devcontainer.json:
    "runArgs": ["--security-opt", "seccomp=unconfined"]

‼️IMPORTANT‼️
This turns off all syscall filtering, not just the keyring calls. A tighter alternative
is to copy Docker's default seccomp profile, add add_key, keyctl and request_key to its
allow list, and pass seccomp=/path/to/profile.json. Either way, keys you store are visible
to the host kernel under your UID, which is the reason Docker blocks them by default.

Add this to Dev Container:
    "runArgs": ["--uts=host", "--security-opt", "seccomp=unconfined", "--security-opt", "systempaths=unconfined"],
"""
import argparse
import getpass
import sys
from pathlib import Path

import keyctl2
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization

RING = "session"  # same as @s; use "user" (@u) to share across all your terminals


def decrypt(path):
    """Prompt for the passphrase and return the key unencrypted (OpenSSH format)."""
    p = Path(path).expanduser()
    try:
        data = p.read_bytes()
    except FileNotFoundError:
        sys.exit(f"Key file not found: {p}")
    except IsADirectoryError:
        sys.exit(f"Not a file: {p}")
    except PermissionError:
        sys.exit(f"Permission denied reading: {p}")

    password = getpass.getpass(f"Passphrase for {p}: ").encode() or None

    # New-style keys use the OpenSSH format; older ones are PEM (RSA/EC/PKCS8)
    if b"OPENSSH PRIVATE KEY" in data:
        loader = serialization.load_ssh_private_key
    else:
        loader = serialization.load_pem_private_key

    try:
        key = loader(data, password=password)
    except UnsupportedAlgorithm as e:
        sys.exit(f"Missing dependency ({e}); run: pip install bcrypt")
    except (ValueError, TypeError) as e:
        sys.exit(f"Could not decrypt key (wrong passphrase?): {e}")

    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.OpenSSH,
        serialization.NoEncryption(),
    )


def find(name):
    """Return a Key for `name` in the keyring, or None if missing/expired."""
    try:
        return keyctl2.Key(keyctl2.search(RING, "user", name))
    except keyctl2.KeyctlError:
        return None

def store(args):
    if args.minutes is not None:
        seconds, label = int(args.minutes * 60), f"{args.minutes:g}m"
    else:
        hours = args.hours if args.hours is not None else 8
        seconds, label = int(hours * 3600), f"{hours:g}h"
    if seconds < 1:
        sys.exit("Lifetime must be at least 1 second")

    payload = decrypt(args.keyfile)
    try:
        serial = keyctl2.add_key("user", args.name, payload, RING)
        keyctl2.Key(serial).set_timeout(seconds)
    except keyctl2.KeyctlError as e:
        hint = " (blocked by container seccomp? see Docker --security-opt)" if e.errno == 1 else ""
        sys.exit(f"Keyring error: {e.strerror}{hint}")
    print(f"Stored as key {serial} in {RING} keyring for {label}", file=sys.stderr)

def get(args):
    key = find(args.name)
    if key is None:
        sys.exit("Key not found or expired")
    if sys.stdout.isatty():
        sys.exit("Refusing to print a private key to the terminal; pipe it, e.g. | ssh-add -")
    sys.stdout.buffer.write(key.read())

def clear(args):
    key = find(args.name)
    if key is None:
        print("Nothing to clear", file=sys.stderr)
        return
    key.revoke()
    print("Key revoked", file=sys.stderr)

# DEBUG

def show(args):
    """DEBUG ONLY: print the cached secret to stdout, even on a terminal. Remove for prod."""
    key = find(args.name)
    if key is None:
        sys.exit("Key not found or expired")
    print("WARNING: debug output, do not use in prod", file=sys.stderr)
    sys.stdout.buffer.write(key.read())
    sys.stdout.flush()

PERM_CLASSES = (("possessor", 24), ("user", 16), ("group", 8), ("other", 0))
PERM_BITS = (("v", 0x01), ("r", 0x02), ("w", 0x04), ("s", 0x08), ("l", 0x10), ("a", 0x20))
PROC_FLAGS = {"I": "instantiated", "R": "revoked", "D": "dead", "Q": "quota-counted",
              "U": "under construction", "N": "negative", "i": "invalidated"}


def _perm_str(perm):
    """0x3f010000 -> 'possessor=vrwsla user=v----- group=------ other=------'"""
    out = []
    for cls, shift in PERM_CLASSES:
        bits = (perm >> shift) & 0x3F
        out.append(f"{cls}=" + "".join(c if bits & m else "-" for c, m in PERM_BITS))
    return " ".join(out)


def _proc_keys_line(serial):
    """Return this key's /proc/keys fields, or None if it isn't visible there."""
    want = f"{serial:08x}"
    try:
        with open("/proc/keys") as f:
            for line in f:
                parts = line.split(None, 8)
                if parts and parts[0] == want:
                    return parts
    except OSError:
        pass
    return None


def _key_user_quota(uid):
    """Parse /proc/key-users for this UID's key count and byte quota."""
    try:
        with open("/proc/key-users") as f:
            for line in f:
                u, rest = line.split(":", 1)
                if int(u) == uid:
                    # usage nkeys/nikeys qnkeys/maxkeys qnbytes/maxbytes
                    _, _, qkeys, qbytes = rest.split()
                    return qkeys, qbytes
    except (OSError, ValueError):
        pass
    return None


def stats(args):
    """Print everything the kernel will tell us about a cached key."""
    key = find(args.name)
    if key is None:
        sys.exit("Key not found or expired")

    d = key.describe()
    perm = int(d.perm)
    rows = [
        ("name", d.description),
        ("serial", f"{key.serial} (0x{key.serial:08x})"),
        ("type", d.type),
        ("keyring", RING),
        ("owner uid/gid", f"{d.uid}/{d.gid}"),
        ("perm", f"0x{perm:08x}"),
        ("", _perm_str(perm)),
    ]

    proc = _proc_keys_line(key.serial)
    if proc:
        _, flags, usage, expiry, *_ = proc
        tail = proc[-1].rsplit(":", 1)
        rows += [
            ("state", ", ".join(PROC_FLAGS[c] for c in flags if c in PROC_FLAGS) or "-"),
            ("references", usage),
            ("expires in", "never" if expiry == "perm" else f"~{expiry} (kernel rounds this)"),
            ("payload size", f"{tail[1].strip()} bytes" if len(tail) == 2 else "?"),
        ]
    else:
        # /proc/keys is masked (e.g. Docker); size is still available via read()
        try:
            size = f"{len(key.read())} bytes"
        except keyctl2.KeyctlError as e:
            size = f"? ({e.strerror})"
        rows += [
            ("state", "instantiated (describe succeeded)"),
            ("payload size", size),
            ("expires in", "unknown (/proc/keys unavailable)"),
            ("references", "unknown (/proc/keys unavailable)"),
        ]

    quota = _key_user_quota(d.uid)
    if quota:
        rows += [("uid quota keys", quota[0]), ("uid quota bytes", quota[1])]

    width = max(len(k) for k, _ in rows)
    for k, v in rows:
        print(f"{k:<{width}}  {v}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    # s = sub.add_parser("store", help="decrypt a key and cache it")
    # s.add_argument("keyfile")
    # s.add_argument("--hours", type=float, default=8)

    s = sub.add_parser("store", help="decrypt a key and cache it")
    s.add_argument("keyfile")
    ttl = s.add_mutually_exclusive_group()
    ttl.add_argument("--hours", type=float, help="cache lifetime in hours (default 8)")
    ttl.add_argument("--minutes", type=float, help="cache lifetime in minutes")
    s.set_defaults(func=store)

    s.set_defaults(func=store)

    g = sub.add_parser("get", help="write the cached key to stdout")
    g.set_defaults(func=get)

    c = sub.add_parser("clear", help="revoke the cached key now")
    c.set_defaults(func=clear)

    d = sub.add_parser("show", help="DEBUG: print the cached secret (remove for prod)")
    d.set_defaults(func=show)

    t = sub.add_parser("stats", help="show key metadata (never the secret)")
    t.set_defaults(func=stats)

    for sp in (s, g, c, d, t):
        sp.add_argument("--name", default="sshkey", help="key name in the keyring")

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
