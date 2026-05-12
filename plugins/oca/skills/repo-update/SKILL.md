---
name: oca:repo-update
description: Update OCA repository using copier. Use when the user wants to update an existing OCA repo to benefit from upstream template changes.
allowed-tools:
  - Bash(copier:*)
  - Bash(git:*)
  - Bash(gh:*)
---

# OCA Repo Update

Update the OCA repository by running `copier update`, then open a Pull Request on GitHub.

## Workflow

### 1. Check working tree

```bash
git status --porcelain
```

If there are uncommitted changes, **stop and ask the user** to commit or stash them first before continuing.

### 2. Update repo from template

```bash
copier update -f --trust -r master
```

Flags:

- `-f` — Force overwrite existing files
- `--trust` — Trust the template (allow template code execution)
- `-r master` — Use the `master` branch of the OCA template

### 3. Commit and push

Read the Odoo version from `.copier-answers.yml` (authoritative source set by copier), then use it to name the branch.

Find the user's personal fork remote by matching remotes against the authenticated GitHub username. If no personal remote is found, **stop and ask the user** which remote to use.

```bash
VERSION=$(grep '^odoo_version:' .copier-answers.yml | awk '{print $2}')
GH_USER=$(gh api user --jq '.login')
REMOTE=$(git remote -v | grep "github.com[/:]${GH_USER}/" | awk '{print $1}' | head -1)

BRANCH="${VERSION}-upgrade-project-template"
git checkout -b "$BRANCH"
git add .
git commit -m "[UPD] templates: update from OCA repo template"
git push "$REMOTE" "$BRANCH"
```

### 4. Create Pull Request

Find the upstream remote (the OCA org repo, not the personal fork):

```bash
UPSTREAM_REMOTE=$(git remote -v | grep "github\.com[/:]OCA/" | awk '{print $1}' | head -1)
UPSTREAM_REPO=$(git remote get-url "$UPSTREAM_REMOTE" | sed 's|.*github\.com[/:]||;s|\.git$||')
```

If no upstream remote is found, **stop and ask the user** which remote points to the OCA repo.

````bash
gh pr create \
  --repo "$UPSTREAM_REPO" \
  --head "${GH_USER}:${BRANCH}" \
  --base "$VERSION" \
  --title "[$VERSION] Update from OCA repo template" \
  --body "$(cat <<'EOF'
## What

Update repository structure from the upstream OCA repository template.

## Why

Sync template changes (pre-commit hooks, CI/CD configs, scaffolding,...) from the
OCA master template to keep the repository up to date.

## How

Generated via:

```bash
copier update -f --trust -r master
```

EOF
)"
````
