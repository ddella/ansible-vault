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

This pushes to both remote repo in one command:

```bash
git push -u origin main
```

