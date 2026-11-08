#!/usr/bin/env zsh

### Default vault id
VAULT_ID="default"

### Parse the arguments Ansible passes
# Ex. 'ansible.cfg': vault_identity_list = nonprod@/workspaces/avd-non-prod/.secrets/vault_wrapper-client.sh 
# ARG1: "--vault-id"
# ARG2: "nonprod"
if [[ "$1" == "--vault-id" ]]; then
  VAULT_ID="$2"
fi

# ---------------------------------------------------------
# DYNAMIC PRIVATE KEY SELECTION
# ---------------------------------------------------------
### Check if the user defined a custom path via an Environment Variable
# Set the env. variable: export AGE_PRIVATE_KEY="/home/avd/.ssh/id_ed25519_avd"
if [[ -n "${AGE_PRIVATE_KEY:-}" ]]; then
  IDENTITY_FILE="$AGE_PRIVATE_KEY"

### Otherwise, fallback to checking standard default SSH paths
elif [[ -f "$HOME/.ssh/id_ed25519" ]]; then
  IDENTITY_FILE="$HOME/.ssh/id_ed25519"
elif [[ -f "$HOME/.ssh/id_rsa" ]]; then
  IDENTITY_FILE="$HOME/.ssh/id_rsa"
else
  # If no key is found, throw an error to standard error (so Ansible sees it)
  echo "Error: No default SSH key found. Please 'export AGE_PRIVATE_KEY'." >&2
  exit 1
fi
# ---------------------------------------------------------

# ---------------------------------------------------------
# DEBUG ONLY
# ---------------------------------------------------------
echo "ARG1=[${1}] - ARG2/VAULT_ID=[${VAULT_ID}] - SSH Private Key=[${AGE_PRIVATE_KEY}]" > $0.log

# ---------------------------------------------------------
# DECRYPTION BASED ON THE VAULT-ID
# ---------------------------------------------------------
# Return the correct password based on the vault-id
if [[ "$VAULT_ID" == "dev" ]]; then
  base64 -d /workspaces/avd-non-prod/.secrets/.vault-secret-dev.age | age -d -i "$IDENTITY_FILE"
elif [[ "$VAULT_ID" == "prod" ]]; then
  base64 -d /workspaces/avd-non-prod/.secrets/.vault-secret-prod.age | age -d -i "$IDENTITY_FILE"

### Global Secrets `global`
elif [[ "$VAULT_ID" == "global" ]]; then
  base64 -d /workspaces/Ansible-Vault/.secrets/.global-ansible-vault.age \
  | age -d -i <(python3 /workspaces/Ansible-Vault/scripts/ssh_key_cache.py get --name global-secrets)
### Personal Secrets for `personal`
elif [[ "$VAULT_ID" == "personal" ]]; then
  base64 -d /workspaces/Ansible-Vault/.secrets/.personal-ansible-vault.age \
  | age -d -i <(python3 /workspaces/Ansible-Vault/scripts/ssh_key_cache.py get --name personal-secrets)

### 🤔 Not sure we want this 🤔
else
  echo -n "default_password"
fi

# Capture the exit code of the pipeline
EXIT_CODE=$?

# Act on a non-zero exit code
if [ $EXIT_CODE -ne 0 ]; then
  # Print error to STDERR (>&2) so it doesn't corrupt Ansible's password read
  echo "ERROR: Failed to decrypt the vault password. Your private key used was [$IDENTITY_FILE]." >&2
  echo "Have you forgotten to set the location of your private key with the command: export AGE_PRIVATE_KEY=$HOME/.ssh/id_ed25519_project" >&2
  # Exit with the captured failing exit code
  exit $EXIT_CODE
fi
