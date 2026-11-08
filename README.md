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
> 📌 This workflow assumes the SSH private key is encrypted.  

## Create Secret Directory

Create a dedicated directory to store the following components:

* The wrapper script designed to decrypt the Ansible Vault master password(s).
* The encrypted Ansible Vault master password(s).
* This script can utilize a user's SSH key pair to encrypt/decrypt the master password.

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

You will be asked for a passphrase to encrypt your private key. If you don't want to encrypt your private key, just add `-N ''` to `ssh-keygen`.

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

| Cleartext file | Encrypted file | Usage | Vault id |
| --- | --- | --- | --- |
| global-ansible-vault.yml | global-ansible-vault-enc.yml | Global secrets | global |
| personal-ansible-vault.yml | personal-ansible-vault-enc.yml | Personal secrets | personal |
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
INPUT_FILE="/workspaces/Ansible-Vault/.secrets/.global-ansible-vault.txt"
vi "${INPUT_FILE}"
```

> ⛔ Do not use `echo -n "my-super-secret" > .secrets/.global-ansible-vault.txt`, as the cleartext password will be recorded in your shell history.


Encrypt the Ansible master password file using `age` with the public keys of all members of the team. Only **one** private key is needed to decrypt the password.

```bash
INPUT_FILE="/workspaces/Ansible-Vault/.secrets/.global-ansible-vault.txt"
ENCRYPTED_FILE="/workspaces/Ansible-Vault/.secrets/.global-ansible-vault.age"
PUBLIC_KEYS_FILE="/workspaces/Ansible-Vault/.secrets/team_ssh_keys.txt"

age -R ${PUBLIC_KEYS_FILE} ${INPUT_FILE} | base64 -w 0 > ${ENCRYPTED_FILE}

# ❗🗑️ **Important:** Securely remove the file containing the cleartext password once encryption is complete.
shred -u -v -n 3 ${INPUT_FILE}
```

## Step 2: 🔓 Decrypt the Ansible Master Password (Optional)

To verify the encryption was successful, attempt to decrypt the password using your SSH private key. If the private key was encrypted, `age` will ask for the `passphrase`.

```bash
PRIVATE_KEY="$HOME/.ssh/id_ed25519_vault_lab"
base64 -d ${ENCRYPTED_FILE} | age -d -i ${PRIVATE_KEY}
```

> 📌 The output must successfully display the password that was encrypted in the previous step.

## 🏛️ Step 3: Create the Ansible Vault File

Create the initial unencrypted Ansible Vault file from the master template `global-ansible-vault.yml`. Save the file in the `.secrets/` directory.

```bash
cp global-ansible-vault.yml .secrets/.
```

Edit the file `.secrets/global-ansible-vault.yml` and *modify/add/change/delete* the necessary values.

> 🚫 Do not modify the top-level key `vault`.


## 🎁 Step 4: Create the keyctl Script

If the SSH private key is encrypted, each time you will use it with `age`, you will be asked to enter the passphrase. You can skipt this step but having your private key stored in the Kernel **key retention service**. That service lets the kernel hold secrets such as passwords, Kerberos tickets, encryption keys and certificates in kernel memory. They never need to sit in a file, and access to them is controlled.

You will need a tool like, **keyctl**, to interact with the Linux kernel's **key retention service** in the userspace

**Gotchas**
- Keys disappear when their last keyring link is dropped. A key held only in `@s` is lost when the session ends.
- Containers and `sudo` can land in a different session keyring than you expect, so "key not found" is often a scoping issue. Check with `keyctl show`.
- Permission masks have separate possessor, user, group and other fields. "Possessor" means you can reach the key through your own keyrings.

The script `ssh_key_cache.py` is the wrapper around the `keyctl` utility in Linux.

This command will decrypt the SSH private key and store it in Linux kernel's **key retention service** under the name `global-secrets`.

```bash
scripts/ssh_key_cache.py store ~/.ssh/id_ed25519_vault_lab --hours 15 --name global-secrets
```

To read the secret, you use the `get` argument an pipe the result to any program that needs it to decrypt your Ansible Vault master password.

```bash
scripts/ssh_key_cache.py get --name global-secrets | <some other utility>
```

## 🎁 Step 5: Create the Wrapper Script

If you intend to test the wrapper script directly via a shell **AND** are using the script above you don't need the `AGE_PRIVATE_KEY` environment variable.

* `export AGE_PRIVATE_KEY="$HOME/.ssh/id_ed25519_vault_lab"`

The script is executed by Ansible Vault with 2 parameters:
* `/workspaces/Ansible-Vault/.secrets/vault_wrapper-client.sh --vault-id global`

To create a vault password client script:
* Create a file with a name ending in either `-client` or` -client.EXTENSION`.
* Make the file executable
* Within the script itself:
  * Print the passwords to standard output
  * Accept a `--vault-id` option
  * If the script prompts for data (for example, a database password), display the prompts to the TTY.

### 🧪 Verification

To test the wrapper script, you can run it manually and provide the following parameters:

* `--vault-id`
* `<repo>` (e.g., `global`, `personal`)

Example verification for `global`:

```bash
scripts/vault_wrapper-client.sh --vault-id global
```

It should print the unencrypted password to `stdout`.

## Step 6: ansible.cfg

Ansible automatically loads `ansible.cfg` only if it is located within your current working directory. If you run the `ansible-vault` command from a separate folder, you must define the configuration path explicitly:

```bash
export ANSIBLE_CONFIG="/workspaces/Ansible-Vault/ansible.cfg"
```

Your `ansible.cfg` should look like this:

```ini
[defaults]
vault_identity_list = global@/workspaces/Ansible-Vault/scripts/vault_wrapper-client.sh, personal@/workspaces/Ansible-Vault/scripts/vault_wrapper-client.sh
```

> 📌 This is for the `nonprod` environment.


## Step 7: Encrypt the Ansible Vault

Use the following commands to create the encrypted version of the global Ansible Vault file from your unencrypted source:

```bash
# Point to a completely different configuration file
export VAULT_FILE_CLEAR="/workspaces/Ansible-Vault/.secrets/global-ansible-vault.yml"
export VAULT_FILE_ENC="/workspaces/Ansible-Vault/global_vars/global-ansible-vault-enc.yml"
export VAULT_ID="global"

# Encrypting with Vault IDs
# override the Ansible Vault list because we haven't done 'personal' vault yet.
ANSIBLE_VAULT_IDENTITY_LIST="global@/workspaces/Ansible-Vault/scripts/vault_wrapper-client.sh" \
  ansible-vault encrypt "${VAULT_FILE_CLEAR}" --encrypt-vault-id "${VAULT_ID}" --output "${VAULT_FILE_ENC}"
```

* The encrypted Ansible Vault will reside in the directory `<repo name>/global_vars` and is defined globally.
* See the naming convention for the encrypted Ansible Vault.

> ❗ Because Ansible Vault encrypt invokes the wrapper script to perform the vault encryption, the process will fail if any preceding steps were executed incorrectly.


## 🔎 Step 8: Read the Ansible Vault

This command will read the encrypted Ansible Vault global, decrypt it and output the results on stdout.

```bash
ansible-vault decrypt --vault-id global --output - global_vars/global-ansible-vault-enc.yml
```

---

# 🧑🏻‍💻 🎟️ Personal Token for CVaaS

This creates a new Ansible Vault that contains your personal secrets.

## Step 1: 🔐 Encrypt the Ansible Master Password

First, create a temporary file containing the cleartext Ansible Vault master password. This is the password used by `ansible-vault encrypt ...`.

```bash
INPUT_FILE="/workspaces/Ansible-Vault/.secrets/.personal-ansible-vault.txt"
vi "${INPUT_FILE}"
```

> ⛔ Do not use `echo -n "my-super-secret" > .secrets/.personal-ansible-vault.txt`, as the cleartext password will be recorded in your shell history.

Encrypt the Ansible master password file using `age` but this time only with your public key. Only you can decrypt the password.

```bash
OUTPUT_FILE="/workspaces/Ansible-Vault/.secrets/.personal-ansible-vault.age"
PUBLIC_KEY="$HOME/.ssh/id_ed25519_vault_lab.pub"

# Encrypt the password and save it to a file
age --encrypt -R "${PUBLIC_KEY}" "${INPUT_FILE}" | base64 -w 0 > "${OUTPUT_FILE}"

# ❗🗑️ **Important:** Securely remove the file containing the cleartext password once encryption is complete.
shred -u -v -n 3 ${INPUT_FILE}
```

## Step 2: 🔓 Decrypt the Ansible Master Password (Optional)

To verify the encryption was successful, attempt to decrypt the password using your SSH private key.

```bash
ENCRYPTED_FILE="/workspaces/Ansible-Vault/.secrets/.personal-ansible-vault.age"
PRIVATE_KEY="$HOME/.ssh/id_ed25519_vault_lab"
base64 -d ${ENCRYPTED_FILE} | age -d -i ${PRIVATE_KEY}
```

> 📌 The output must successfully display the password that was encrypted in the previous step.

## 🏛️ Step 3: Create the personal Ansible Vault File

Create your initial unencrypted Ansible personal Vault file from the master template `personal-ansible-vault.yml`. Save the file in the `.secrets/` directory.

```bash
cp personal-ansible-vault.yml .secrets/.
```

Edit the file `.secrets/personal-ansible-vault.yml` and replace your secrets.

## 🎁 Step 4: Wrapper Script

This should have been created earlier. The decryption on the file `.personal-ansible-vault.age` is done via your SSH private key.

This needs to be added to the wrapper script so it knows how to decrypt the Ansible Vault `personal`.

```bash
### Personal Secrets for `personal`
elif [[ "$VAULT_ID" == "personal" ]]; then
  base64 -d /workspaces/Ansible-Vault/.secrets/.personal-ansible-vault.age \
  | age -d -i <(python3 /workspaces/Ansible-Vault/scripts/ssh_key_cache.py get --name personal-secrets)
```

## 🔑 Step 5: Store private key

Decrypt your private SSH key and store it in the Kernel **key retention service**.

```bash
scripts/ssh_key_cache.py store ~/.ssh/id_ed25519_vault_lab --hours 15 --name personal-secrets
```

To read the secret, you use the `get` argument an pipe the result to any program that needs it to decrypt your Ansible Vault master password.

```bash
scripts/ssh_key_cache.py get --name personal-secrets | <some other utility>
scripts/ssh_key_cache.py show --name personal-secrets 
```

### 🧪 Verification

To test the wrapper script, you can run it manually and provide the following parameters:

* `--vault-id`
* `<repo>` (e.g., `global`, `personal`)

Example verification for `personal`:

```bash
scripts/vault_wrapper-client.sh --vault-id personal
```

It should print the unencrypted password on `stdout`.

# 🔐 Step 6: Encrypt the personal Ansible Vault

Use the following commands to create the encrypted version of your personal Ansible Vault file from your unencrypted source:

```bash
export VAULT_FILE=".secrets/personal-ansible-vault.yml"
export OUTPUT_FILE="global_vars/personal-ansible-vault-enc.yml"
export VAULT_ID="personal"

# Encrypting with Vault IDs
ansible-vault encrypt ${VAULT_FILE} --encrypt-vault-id ${VAULT_ID} --output ${OUTPUT_FILE}
```

* The encrypted Ansible Vault must reside in the directory `<repo name>/global_vars` and is defined globally.

Because Ansible Vault invokes the wrapper script to perform the vault encryption, the process will fail if any preceding steps were executed incorrectly.

## 🔎 Step 7: Read the personal Ansible Vault

This command will read the encrypted personal Ansible Vault, decrypt it and output the results on stdout.

```bash
ansible-vault decrypt --vault-id personal --output - global_vars/personal-ansible-vault-enc.yml
```

## 📚 Step 8: Read the Ansible Vault with a playbook

Run the playbook `playbooks/verify_global_secrets.yml`. It will print some values included in both Ansible Vaults.

```bash
ansible-playbook -i localhost, -c local -e "user=DDN" playbooks/verify_global_secrets.yml
```

