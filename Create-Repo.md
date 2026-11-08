## Create the repos

Create the repos in GitLab and GitHub via the GUI. Leave them **empty**: don't create a `README.md`, `.gitignore` or `LICENSE` file (see [Push](#push) for what happens if you do).

* 🦊 Create a new project in GitLab
* 😺 Create a new project in GitHub

The repos are:

* `git@gitlab.com:ansible-avd/ansible-vault.git`
* `git@github.com:ddella/ansible-vault.git`

## </> Initialise a Git repo

The project will push to both GitLab and GitHub. Initialise the Git repository:

```bash
cd <existing_folder>
git init --initial-branch=main --object-format=sha1
```

* `--object-format=sha1` is the right choice because GitHub doesn't accept SHA-256 repositories and GitLab's SHA-256 support is only partial. SHA-1 is already Git's default, so the flag changes nothing, but it records your choice.
* `--initial-branch=main` matches the default branch name used by both GitHub and GitLab, so your first push won't create a mismatched default branch.

## Push to both remotes

To push to both remote repositories, a common setup is a single `origin` remote with two push URLs.

Run these commands only once:

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

Fetches come from GitLab, and every push goes to both. You need the first `--add --push` line: once any push URL is set, Git stops pushing to the fetch URL. If you'd rather push to each host separately, add two remotes instead (`gitlab` and `github`).

> ‼️ **IMPORTANT** ‼️
> Since this repo is about Ansible Vault, add a `.gitignore` (see [Source control](#source-control-gitignore)) **before** your first commit so you don't commit secrets by accident.

## Push

Time to push the initial commit. This pushes to both remote repos in one command:

```bash
git add .
git commit -m "Initial commit"
git push -u origin main
```

It worked for GitLab but failed for GitHub:

```text
To github.com:ddella/ansible-vault.git
 ! [rejected]        main -> main (fetch first)
error: failed to push some refs to 'github.com:ddella/ansible-vault.git'
```

When I created the repo on GitHub, it made its own "Initial commit" containing a `LICENSE` file. That commit had no common history with my local `main`, so GitHub rejected the push. GitLab accepted it because that repo was empty.

First, fetch GitHub's `main` into a temporary ref to see what's on it. Nothing is merged or pushed yet:

```bash
git fetch git@github.com:ddella/ansible-vault.git main:refs/remotes/github-tmp/main
git log --oneline --stat github-tmp/main
```

**Option 1: keep the LICENSE (recommended).** Merge GitHub's commit into your branch, then push to both hosts so they end up with the same history:

```bash
# Bring GitHub's LICENSE file into the local repo
git merge github-tmp/main --allow-unrelated-histories -m "Merge GitHub initial commit (LICENSE)"
# Push to both
git push origin main
# Remove the temporary ref
git update-ref -d refs/remotes/github-tmp/main
```

**Option 2: discard GitHub's commit.** If you don't want that LICENSE, overwrite GitHub with your history:

```bash
git push --force git@github.com:ddella/ansible-vault.git main
git update-ref -d refs/remotes/github-tmp/main
```

To avoid this next time, create the remote repo empty: leave the `README`, `.gitignore` and `LICENSE` boxes unchecked.
