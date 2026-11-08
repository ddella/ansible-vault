# Ansible Vault

Complete guide to Ansible Vault

* Multiple Ansible vault files
  - Global Ansible vault for the main project
  - Presonal Ansible vault per engineer
* Master Ansible vault password encrypted at rest via SSH key
* Private SSH key encrypted (optional)

## Create repos

Create repo in GitLab and GitHub via the GUI. Make sure not to create the `README.md` and `.gitignore` files.
* 🦊 Create a new projet in GitLab
* 😺 Create a new projet in GitHub

The repo are:
* `git@gitlab.com:ansible-avd/ansible-vault.git`
* `git@github.com:ddella/ansible-vault.git`

## </> Intialise a Git repo

The project will push on both GitLab and GitHub. Let's initialise the git repository.

```bash
cd <existing_folder>
git init --initial-branch=main --object-format=sha1
```

* `--object-format=sha1` is the right choice since GitHub doesn't accept SHA-256 repositories. GitLab has only partial SHA-256 support. SHA-1 is already Git's default, so the flag changes nothing, but it does record your choice.  
* `--initial-branch=main` matches the default branch name that GitHub and GitLab both use, so your first push won't create a mismatched default branch.


## Update both

For pushing to both remote repositories, one common setup is a single `origin` remote with two push URLs:

Execute this commands only once:
```bash
git remote add origin git@gitlab.com:ansible-avd/ansible-vault.git
git remote set-url --add --push origin git@gitlab.com:ansible-avd/ansible-vault.git
git remote set-url --add --push origin git@github.com:ddella/ansible-vault.git
```
After that, a single `git push` updates both.

Output of `git remote -v`:
```text
origin  git@gitlab.com:ansible-avd/ansible-vault.git (fetch)
origin  git@gitlab.com:ansible-avd/ansible-vault.git (push)
origin  git@github.com:ddella/ansible-vault.git (push)
```

Fetches come from `GitLab`, and every push goes to both. You need the first `--add --push` line: once any push URL is set, Git stops pushing to the fetch URL. If you'd rather push to each host separately, add two remotes instead (`gitlab` and `github`).

> ‼️IMPORTANT‼️  
> Since the repo will be about Ansible Vault, add a `.gitignore` before your first commit so you don't commit secrets by accident.  

## Push

It's time to push our initial commit.

This pushes to both remote repo in one command:

```bash
git add .
git commit -m "Initial commit"
git push -u origin main
```

It worked for GitLab but failed for GitHub.

```text
To github.com:ddella/ansible-vault.git
 ! [rejected]        main -> main (fetch first)
error: failed to push some refs to 'github.com:ddella/ansible-vault.git'
```

When I created the repo on GitHub, it made its own "Initial commit" containing a `LICENSE` file. That commit had no common history with my local `main`, so GitHub rejected my initial push. It worked on GitLab because I didn't create any file.

**Option 1: keep the LICENSE (recommended).** Merge GitHub's commit into your branch, then push to both hosts so they end up with the same history:

```bash
# This pulled the file LICENSE, on GitHub, to my local repo
git merge github-tmp/main --allow-unrelated-histories -m "Merge GitHub initial commit (LICENSE)"
# Push to both
git push origin main
# Remove the temporary ref
git update-ref -d refs/remotes/github-tmp/main
```

`github-tmp/main` is a temporary ref I created when I fetched GitHub's `main` to check what was on it. I haven't merged or pushed anything.

**Option 2: discard GitHub's commit.** If you don't want that LICENSE, overwrite GitHub with your history:

```bash
git push --force git@github.com:ddella/ansible-vault.git main
git update-ref -d refs/remotes/github-tmp/main
```

To avoid this next time, just create the remote repo empty: leave the `README`, `.gitignore` and `LICENSE` boxes unchecked.

---

# Workflow for Ansible Vault

This workflow details how to create and manage multiple Ansible Vaults. You must be inside the DevContainer to execute these commands, as the environment requires `ansible-vault` and `age`. This assumes that all Ansible Vault master passwords are encrypted with a different master password, which is then encrypted with the SSH public keys of every member of the team, or just your personal SSH public key. Only one private key is needed to decrypt the password.

We will create two Ansible Vaults with the **same** top-level key. Every Ansible Vault will be structured as a Python dictionary:

* Global Vault with all the secrets for the switches.
* User-specific Vault with the CloudVision token.

> 📌 Since they have the **same** top-level key, the two vaults will be merged at runtime.  
> 📌 This workflow assumes the SSH private key is not encrypted.  

## Create Secret Directory

Create a dedicated directory to store the following components:

* The wrapper script designed to decrypt the Ansible Vault master password(s).
* The encrypted Ansible Vault master password(s).
* This script can utilize a user's SSH key pair to encrypt/decrypt the master password (this document).
* It can integrate with Azure Key Vault (not implemented yet).
* It can integrate with CyberArk (not implemented yet).

```bash
mkdir .secrets
```

> 📌 The encrypted Ansible Vault files will ultimately be created within the `global_vars` directory.  

### Source Control (.gitignore)

Ensure your `.gitignore` file contains at least the following entries. You must prevent the `.secrets/` directory and any file matching `*vault*` from leaking into source control, even if they are securely encrypted.

```text
.secrets/
*vault*
*.age
```

## 🔐 Generate Personal SSH Keys (Optional)

You may use existing SSH keys or generate new ones specifically for a project. You can choose either `ed25519` or `rsa` algorithms to encrypt the master Ansible Vault password.

> 📌 The use of the `ed25519` algorithm is highly recommended.
> This workflow assumes the `${HOME}/.ssh` directory is properly mapped to the host inside your DevContainer.

```bash
# Select the directory to store your keys
SSH_DIRECTORY="${HOME}/.ssh"
ssh-keygen -q -t ed25519 -C "email@example.com" -f "${SSH_DIRECTORY}/id_ed25519_vault_lab"
# ssh-keygen -q -t rsa -b 2048 -C "email@example.com" -f "${SSH_DIRECTORY}/id_ed25519_vault_lab"
```

You will be asked for a passphrase to encrypt your private key. If you don't want to encrypt your private key, just add ` -N ''` to `ssh-keygen`.

This command will create the SSH key pair without asking for the passphrase:
```bash
ssh-keygen -q -t ed25519 -N '' -C "My SSH Key for Ansible Vault" -f "${SSH_DIRECTORY}/id_ed25519_avd" <<<y >/dev/null 2>&1
```

## Create a File with Public SSH Keys (Optional)

If you want to encrypt your Ansible Vault master password with multiple public keys, you can compile a text file containing all the public keys authorized to encrypt the master password. This file does not require strict protection as it solely contains public keys. The Ansible master password will be encrypted against every public key listed in this file, meaning only **one** corresponding private key is required for successful decryption.

> 📌 The recommended filename is `team_ssh_keys.txt`.

This file contains all the public keys used to encrypt the master password for Ansible Vault. It is safe to transfer those keys via an unsecured medium.

```bash
cat <<EOF > .secrets/team_ssh_keys.txt
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGH1+AzG4ewffbeJCaBO8G7zE/pTCAxkOeRoUEocuWvH alice@example.com
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIC9SIgGTLAt2ApqDlfy8CTnzRpiCv/GvqrqIqfMhtOXW bob@example.com
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGtm1KWcPeloH1XEQGv4dVLlX9D+xlLOlnhZy2+gSKcu eve@example.com
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIJ6Lp60VWKC6sB5kB8Xs+13N+Ldv8qWy2MgfJhHB6dk email@example.com
EOF
```

> I have included the public key of Eve, since she will eventually be eavesdropping 🕵

## 🤝 Naming Convention

Standard naming conventions for this tutorial are:

| Cleartext file | Encrypted file | Usage | Password |
| --- | --- | --- | --- |
| global-ansible-vault.yml | global-ansible-vault-enc.yml | Global secrets | N/A |
| personal-ansible-vault.yml | personal-ansible-vault-enc.yml | Personal secrets | N/A |
| .global-ansible-vault.txt | .global-ansible-vault.age | Ansible Vault password (global) | password123 |
| .personal-ansible-vault.txt | .personal-ansible-vault.age | Ansible Vault password (personal) | password456 |

🚫❌🙅⛔ Please never add your password, I did this to follow the tutorial 🚫❌🙅⛔

---

# 🌐 🏛️ Global Vault

This creates the global Ansible Vault that contains all the secrets for the project. The master password to decrypt this vault will be encrypted with the public keys of all authorized members.

> 📌 This is usually executed by only one member of the team.


## Step 1: 🔐 Encrypt the Ansible Master Password

First, create a temporary file containing the cleartext Ansible Vault master password. This is the password used by `ansible-vault encrypt ...`.

```bash
INPUT_FILE="/workspaces/avd-non-prod/.secrets/.vault-secret-non-prod.txt"
vi "${INPUT_FILE}"
```

> ⛔ Do not use `echo -n "my-super-secret" > .secrets/.vault-secret-non-prod.txt`, as the cleartext password will be recorded in your shell history.


Encrypt the Ansible master password file using `age` with the public keys of all members of the team. Only **one** private key is needed to decrypt the password.

```bash
INPUT_FILE="/workspaces/avd-non-prod/.secrets/.vault-secret-non-prod.txt"
ENCRYPTED_FILE="/workspaces/avd-non-prod/.secrets/.vault-secret-non-prod.age"
PUBLIC_KEYS_FILE="/workspaces/avd-non-prod/.secrets/team_ssh_keys.txt"

age -R ${PUBLIC_KEYS_FILE} ${INPUT_FILE} | base64 -w 0 > ${ENCRYPTED_FILE}

# ❗🗑️ **Important:** Securely remove the file containing the cleartext password once encryption is complete.
shred -u -v -n 3 ${INPUT_FILE}
```

⚠️ TODO: We have to delete the cleartext password; can we keep the master password in CyberArk or any other vault?
