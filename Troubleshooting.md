# 🛠️⚙️🔧 Troubleshooting

This guide follows the decryption chain from the bottom up: the encrypted master password, the cached SSH key, the wrapper script, Ansible's configuration, then the vault itself. Start with the quick check, then go to the step that failed. If you already have an error message, look it up in the [error message index](#error-index).

```mermaid
flowchart LR
    s1["Step 1<br/>age + SSH key"] --> s2["Step 2<br/>Key cache"] --> s3["Step 3<br/>Wrapper script"] --> s4["Step 4–5<br/>ansible.cfg"] --> s6["Step 6–7<br/>Vault file"] --> s8["Step 8<br/>Playbook"]
    classDef step fill:#EEEDFE,stroke:#534AB7,color:#26215C
    class s1,s2,s3,s4,s6,s8 step
```

Run every command inside the DevContainer, from the repo root:

```bash
cd /workspaces/Ansible-Vault
```

> ⚠️ Several commands below print secrets. Don't paste their output into tickets, chats or screen shares.

<a id="quick-check"></a>

## ⚡ Quick check

This tells you in a few seconds which vault is broken, and whether it's the wrapper or Ansible:

```bash
for id in global personal; do
  printf '%-9s wrapper: ' "${id}"
  scripts/vault_wrapper-client.sh --vault-id "${id}" > /dev/null 2>&1 && printf '✅' || printf '❌'
  printf '   ansible-vault: '
  ansible-vault view "global_vars/${id}-ansible-vault-enc.yml" > /dev/null 2>&1 && echo '✅' || echo '❌'
done
```

| Result | Go to |
| --- | --- |
| Wrapper ❌ | [Step 1](#step-1), then [Step 2](#step-2) and [Step 3](#step-3) |
| Wrapper ✅, `ansible-vault` ❌ | [Step 4](#step-4) to [Step 7](#step-7) |
| Both ✅, playbook still fails | [Step 8](#step-8) |

<a id="step-1"></a>

## 🔓 Step 1: Decrypt the Ansible Vault master password

Decrypt the master password with your SSH **private** key, bypassing the wrapper and the key cache. The password was encrypted with one or more SSH public keys, so any **one** matching private key can decrypt it.

You will be prompted for the passphrase of your SSH private key.

### Global password

```bash
SECRET_FILE=".secrets/.global-ansible-vault.age"
IDENTITY_FILE="${HOME}/.ssh/id_ed25519_vault_lab"
base64 -d "${SECRET_FILE}" | age -d -i "${IDENTITY_FILE}"
```

### Personal password

```bash
SECRET_FILE=".secrets/.personal-ansible-vault.age"
IDENTITY_FILE="${HOME}/.ssh/id_ed25519_vault_lab"
base64 -d "${SECRET_FILE}" | age -d -i "${IDENTITY_FILE}"
```

> ✅ The output is the cleartext password used to encrypt the vault.
> ❌ `age: error: failed to decrypt SSH key file: x509: decryption password incorrect`: wrong passphrase for the SSH private key.
> ❌ `age: error: no identity matched any of the recipients`: wrong private key, or your public key wasn't one of the recipients when the password was encrypted. For the global password, check that your key is in `.secrets/team_ssh_keys.txt` and ask whoever manages it to re-encrypt the password.
> ❌ `age: error: failed to read header: parsing age header: ...`: the file isn't an age file (wrong file, or it was overwritten).
> ❌ `base64: invalid input`: the file isn't base64-encoded. It may have been saved as raw `age` output without `| base64 -w 0`, or edited by hand.
> ❌ `age: command not found`: you're outside the DevContainer, or `age` isn't installed in it.

To check that the file was encrypted by `age`, and to which recipient types, without decrypting it (`age-inspect` requires age v1.3.0 or later):

```bash
base64 -d "${SECRET_FILE}" | age-inspect --json
```

To confirm which SSH key you're using, compare its public key with the recipients list:

```bash
ssh-keygen -y -f "${IDENTITY_FILE}"   # prints the public key (asks for the passphrase)
grep -F "$(ssh-keygen -y -f "${IDENTITY_FILE}" | cut -d' ' -f2)" .secrets/team_ssh_keys.txt \
  && echo "✅ key is a recipient" || echo "❌ key is not in team_ssh_keys.txt"
```

> 📌 If Step 1 fails, the rest of the chain can't work. Fix it before you continue.

<a id="step-2"></a>

## 🧩 Step 2: Check the kernel key retention service

The wrapper doesn't read your SSH key file: it gets the decrypted key from the kernel keyring through `ssh_key_cache.py`. Check that it's there and hasn't expired:

```bash
scripts/ssh_key_cache.py stats --name global-secrets
scripts/ssh_key_cache.py stats --name personal-secrets
```

If you get `Key not found or expired`, add the SSH private key to the key retention service again:

```bash
scripts/ssh_key_cache.py store ~/.ssh/id_ed25519_vault_lab --hours 8 --name global-secrets
scripts/ssh_key_cache.py store ~/.ssh/id_ed25519_vault_lab --hours 8 --name personal-secrets
```

### The key was stored but still isn't found

Keys live in a keyring that belongs to a session. A key stored from one terminal may not be visible from another context. Show your keyrings and what they hold:

```bash
keyctl show @s    # session keyring
# keyctl show @u    # user keyring
```

> 📌 Only session keyring is used.  

Output expected:

```text
Keyring
  97091073 --alswrv   1000  1000   \_ user: global-secrets
1017931765 --alswrv   1000  1000   \_ user: personal-secrets
```

Common causes:

* **Different session.** A new DevContainer, a rebuilt container or a new `docker exec` can start a new session keyring. Store the key again from the shell you're working in.
* **`sudo` or another user.** `sudo` runs with root's keyrings, not yours. Don't run the wrapper or `ansible-vault` with `sudo`.
* **The session ended.** A key held only in the session keyring disappears with the session.

<a id="step-3"></a>

## 🎁 Step 3: Test the wrapper script

Run the wrapper directly and check that it prints the master password on `stdout`, with nothing else in the output:

```bash
scripts/vault_wrapper-client.sh --vault-id global
scripts/vault_wrapper-client.sh --vault-id personal
```

> ✅ The output is the cleartext password used to encrypt the vault. A single trailing newline is fine, because Ansible strips it.
> ❌ `Key not found or expired`: your SSH private key isn't in the kernel key retention service, or it has expired. See [Step 2](#step-2).
> ❌ `unknown vault id` (or `default_password`, if your script still prints a fallback): the vault ID doesn't exist or isn't handled by the script. A `%` right after the output is just zsh marking a missing final newline.

If the wrapper works when you run it but Ansible still fails, check the file itself:

```bash
ls -l scripts/vault_wrapper-client.sh     # must be executable: -rwx...
file scripts/vault_wrapper-client.sh      # must NOT say "with CRLF line terminators"
head -1 scripts/vault_wrapper-client.sh   # must be a valid shebang, e.g. #!/usr/bin/env bash
```

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Decryption failed (no vault secrets were found that could decrypt)` although the wrapper prints the right password | The script isn't executable, so Ansible reads it as a **plain password file** and uses the script's text as the password | `chmod +x scripts/vault_wrapper-client.sh` |
| `/usr/bin/env: 'bash\r': No such file or directory` | Windows line endings (CRLF), often after editing on Windows or a Git `autocrlf` setting | `sed -i 's/\r$//' scripts/vault_wrapper-client.sh` |
| `Vault password script ... returned non-zero (1): None` | The filename doesn't end in `-client` or `-client.EXT`, so Ansible calls it **without** `--vault-id` | Rename it to `vault_wrapper-client.sh` and update `ansible.cfg` |

> 📌 To stop Git from adding CRLF to shell scripts, add `*.sh text eol=lf` to a `.gitattributes` file at the repo root.

<a id="step-4"></a>

## ⚙️ Step 4: `ansible.cfg`

Your `ansible.cfg` must list one entry per vault ID, `<vault id>@<path to wrapper>`:

```ini
[defaults]
vault_identity_list = global@/workspaces/Ansible-Vault/scripts/vault_wrapper-client.sh, personal@/workspaces/Ansible-Vault/scripts/vault_wrapper-client.sh
```

> 📌 Adjust `global` and `personal` to match your vault IDs, and the path to match your setup.
> ⚠️ Use **absolute** paths. A relative path such as `global@scripts/vault_wrapper-client.sh` is resolved from the directory you run Ansible in, so it only works from the repo root. From anywhere else you get `The vault password file /<other dir>/scripts/vault_wrapper-client.sh was not found`.

Check what Ansible actually reads:

```bash
ansible-config dump --only-changed 2>/dev/null | grep -i vault
```

> 📌 `ANSIBLE_VAULT_IDENTITY_LIST`, if set in your environment, overrides `vault_identity_list` from `ansible.cfg`. Check with `env | grep ANSIBLE_VAULT`.

Every ID in the list is loaded, even when you only need one. If the `personal` key cache has expired, a command on the `global` vault prints a warning for `personal` but still works. To limit a single command to one vault:

```bash
ANSIBLE_VAULT_IDENTITY_LIST="global@/workspaces/Ansible-Vault/scripts/vault_wrapper-client.sh" \
  ansible-vault view global_vars/global-ansible-vault-enc.yml
```

<a id="step-5"></a>

## 📍 Step 5: Location of `ansible.cfg`

Ansible uses the first configuration file it finds, in this order: `ANSIBLE_CONFIG`, `./ansible.cfg` in the current directory, `~/.ansible.cfg`, then `/etc/ansible/ansible.cfg`. Check that `ANSIBLE_CONFIG` points to your `ansible.cfg`, and confirm which file Ansible actually loads:

```bash
echo "${ANSIBLE_CONFIG}"
ansible --version | grep "config file"
# Adjust if needed:
# export ANSIBLE_CONFIG="/workspaces/Ansible-Vault/ansible.cfg"
# or remove it:
# unset ANSIBLE_CONFIG
```

> ❌ `config file = None` with the warning `Ansible is being run in a world writable directory (...), ignoring it as an ansible.cfg source`: the folder is writable by everyone, which is common with mounted volumes in DevContainers, so Ansible ignores the `ansible.cfg` in it. Set `ANSIBLE_CONFIG` to the file's absolute path, or remove the write permission: `chmod o-w /workspaces/Ansible-Vault`.

<a id="step-6"></a>

## 🔐 Step 6: Decrypt the vault with Ansible

Once the wrapper works and Ansible reads the right configuration, open the vault:

```bash
ansible-vault view global_vars/global-ansible-vault-enc.yml
ansible-vault view global_vars/personal-ansible-vault-enc.yml
```

> ✅ The output is the vault's YAML content.
> ❌ `Decryption failed (no vault secrets were found that could decrypt)`: Ansible got a password, but not the one this vault was encrypted with. Common causes:
> * The wrapper isn't executable (see [Step 3](#step-3)).
> * The master password was rotated and you have an old `.age` file (or the other way around). Get the current `.secrets/.<id>-ansible-vault.age` from the person who rotated it.
> * The vault was encrypted with a different vault ID than the one your wrapper handles (see [Step 7](#step-7)).
>
> ❌ `The vault password file .../global was not found`: you passed `--vault-id global` without `@<source>`. Ansible then reads `global` as a file path. Drop the option (the configuration provides the source), or use `--vault-id global@/workspaces/Ansible-Vault/scripts/vault_wrapper-client.sh`.
> ❌ `Input is not vault encrypted data`: the file isn't encrypted. Check you're pointing at the `-enc.yml` file, not the cleartext template.

To see exactly which secrets Ansible loads and from where, add `-vvvv`:

```bash
ansible-vault view -vvvv global_vars/global-ansible-vault-enc.yml 2>&1 | grep -iE 'vault|secret'
```

<a id="step-7"></a>

## 🏷️ Step 7: Check the vault ID

Ansible writes the vault ID in the first line of every encrypted file:

```bash
head -1 global_vars/global-ansible-vault-enc.yml     # $ANSIBLE_VAULT;1.2;AES256;global
head -1 global_vars/personal-ansible-vault-enc.yml   # $ANSIBLE_VAULT;1.2;AES256;personal
```

> 📌 The ID must match an entry in `vault_identity_list` and a branch in the wrapper script. A header ending in `1.1;AES256` with no ID means the file was encrypted without a vault ID (for example with `--vault-password-file`). Ansible still tries every password it has, but re-encrypt it with the right ID to keep things clear.

To find every file encrypted with a given vault ID:

```bash
grep -rlxF --exclude-dir=.git '$ANSIBLE_VAULT;1.2;AES256;global' .
```

<a id="step-8"></a>

## 📚 Step 8: The playbook only sees one vault

Both vaults open, but the playbook is missing values from one of them, or fails with an undefined variable such as `'dict object' has no attribute ...`.

Both vaults use the same top-level key `vault`. With Ansible's default `hash_behaviour = replace`, the vault loaded **last** replaces the other one entirely instead of merging with it. Check what Ansible actually sees:

```bash
ansible-playbook -i localhost, -c local playbooks/read_vaults.yml -vv
ansible-config dump 2>/dev/null | grep -i hash_behaviour
```

Fixes, from least to most invasive:

* Give each vault its own top-level key (for example `vault_global` and `vault_personal`).
* Combine them where they're used: `{{ vault_global | combine(vault_personal, recursive=true) }}`.
* Set `hash_behaviour = merge` in `ansible.cfg`. This works, but it changes how **every** dictionary variable in the project is combined, so test the whole project afterwards.

<a id="error-index"></a>

## 📇 Error message index

| Error message (excerpt) | Likely cause | See |
| --- | --- | --- |
| `failed to decrypt SSH key file: x509: decryption password incorrect` | Wrong SSH key passphrase | [Step 1](#step-1) |
| `no identity matched any of the recipients` | Wrong SSH key, or your key isn't a recipient | [Step 1](#step-1) |
| `failed to read header: parsing age header` | Not an age file | [Step 1](#step-1) |
| `base64: invalid input` | `.age` file not base64-encoded | [Step 1](#step-1) |
| `Key not found or expired` | SSH key not in the kernel keyring, or expired | [Step 2](#step-2) |
| `unknown vault id` / `default_password` | Vault ID not handled by the wrapper | [Step 3](#step-3) |
| `/usr/bin/env: 'bash\r'` | CRLF line endings in the wrapper | [Step 3](#step-3) |
| `Vault password script ... returned non-zero (1): None` | Wrapper name doesn't end in `-client` | [Step 3](#step-3) |
| `Vault password client script ... returned non-zero` | The wrapper failed; the message includes its error output | [Step 3](#step-3) |
| `The vault password file .../scripts/vault_wrapper-client.sh was not found` | Relative path in `vault_identity_list`, or wrong path | [Step 4](#step-4) |
| `ignoring it as an ansible.cfg source` | World-writable directory | [Step 5](#step-5) |
| `Decryption failed (no vault secrets were found that could decrypt)` | Wrong or old password, or wrapper not executable | [Step 6](#step-6) |
| `The vault password file .../global was not found` | `--vault-id global` without `@source` | [Step 6](#step-6) |
| `Input is not vault encrypted data` | File isn't encrypted | [Step 6](#step-6) |
| Values missing from one vault in a playbook | Same top-level key in both vaults | [Step 8](#step-8) |
