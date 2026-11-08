#!/bin/zsh

# https://github.com/ohmyzsh/ohmyzsh/

### Change the Theme
# https://github.com/ohmyzsh/ohmyzsh/wiki/themes
# sed -i "s/^ZSH_THEME=.*/ZSH_THEME=philips/" ~/.zshrc
sed -i "s/^ZSH_THEME=.*/ZSH_THEME=robbyrussell/" ~/.zshrc

### Apply the custom Zsh prompt and remove the right prompt
cat << 'EOF' >> ~/.zshrc
ZSH_THEME_GIT_PROMPT_ADDED="%{$fg[green]%} %{%G✚%}"
ZSH_THEME_GIT_PROMPT_MODIFIED="%{$fg[blue]%} %{%G✹%}"
ZSH_THEME_GIT_PROMPT_DELETED="%{$fg[red]%} %{%G✖%}"
ZSH_THEME_GIT_PROMPT_RENAMED="%{$fg[magenta]%} %{%G➜%}"
ZSH_THEME_GIT_PROMPT_UNMERGED="%{$fg[yellow]%} %{%G═%}"
ZSH_THEME_GIT_PROMPT_UNTRACKED="%{$fg[cyan]%} %{%G✭%}"

PROMPT='%{$fg[blue]%}%B%c/%b%{$reset_color%} $(git_prompt_info)%(!.#.$) '
RPROMPT=''

# Export the AGE private key variable for all Zsh sessions
export AGE_PRIVATE_KEY="/home/avd/.ssh/id_ed25519_vault"

EOF

# The timezone (TZ) and AGE_PRIVATE_KEY are set in "containerEnv" in devcontainer.json.
# To list the valid timezone names: find /usr/share/zoneinfo/ -type f
# Set the timezone
# To see a flat list of all nested city/region files: find /usr/share/zoneinfo/ -type f
sudo ln -fs /usr/share/zoneinfo/America/Montreal /etc/localtime
sudo dpkg-reconfigure --frontend noninteractive tzdata

# Add the 'avd' user to the 'docker' group
# ⛔⛔⛔ DON'T DO THAT ⛔⛔⛔
# Get the GID of the 'avd' group
# AVD_GID=$(getent group avd | cut -d: -f3)
# echo "The GID of group avd is: $AVD_GID"

# SOCK_GID=$(stat -c "%g" /var/run/docker.sock)
# echo "The GID is: $SOCK_GID"
# sudo groupadd -g $SOCK_GID docker
# sudo groupmod -g $AVD_GID docker
# sudo usermod -aG docker $USER
# sudo newgrp docker

exit 0
