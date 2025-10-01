# Staging Sync Utility

This repository contains `stage_sync.py`, a small helper for managing temporary
"staging" checkouts of local Git projects that all point at the same remote.
It automates cloning a clean copy of a project into the staging area and then
fast-forwarding the original working copy with the changes you made in staging.

## Workflow Overview

You provide the script with two directories when running commands:

- A **work root** (`--work-root`) that contains your canonical Git repositories.
- A **staging root** (`--staging-root`, defaults to the directory you launch the
  command from) that holds throwaway staging copies.

When you run `clone`, the script:

1. Ensures the target project inside the work root exists, is clean, and is on a
   branch that also exists on the remote (default remote name is `origin`).
2. Pushes the current HEAD to a uniquely named temporary remote branch and
   bootstraps a matching repository under the staging root that tracks that
   temporary branch (the generated name is derived from the staging directory
   itself rather than its full path).
3. Records the mapping in `.staging_sync.json` so future syncs can find the
   right source and destination.

When you run `sync-back`, the script:

1. Validates that both the staging copy and the work repository are clean
   unless you explicitly allow dirtiness.
2. Pushes the staging HEAD to a temporary branch on the shared remote (reusing
   the one created during `clone` unless you override it).
3. Fast-forwards (or hard-resets with `--force`) the original work branch that
   the staging copy was based on (or a branch you specify with `--branch`).
4. Pushes the updated branch back to the remote and then deletes the temporary
   branch on the remote before exiting.

The `list` subcommand prints all recorded mappings from `.staging_sync.json`.

## Prerequisites

- Python 3.8 or newer.
- Git available on your PATH.
- A work directory populated with Git repositories that share a remote named
  `origin`.
- A staging directory containing this script, unless you provide an alternate
  location via `--staging-root`.

## Bootstrapping with uv

Use `setup_staging_env.py` to create a virtual environment inside a staging
directory and install this package into it with [`uv`](https://docs.astral.sh/uv/):

```bash
python3 setup_staging_env.py /path/to/staging
```

The script creates `/path/to/staging/.venv` by default and installs the
`stage-sync` console entrypoint. Pass `--force` to recreate an existing
environment or `--venv-name` to choose a different virtualenv directory name.
After the command completes, activate the environment and run `stage-sync` as
usual, providing `--staging-root /path/to/staging` when running commands.

## Usage

Global options:

- `--work-root PATH` (required) – path to your work directory.
- `--staging-root PATH` – override the staging directory. Defaults to the
  current working directory when you run the command.
- `--config-path PATH` – override where metadata is stored. Defaults to
  `<staging-root>/.staging_sync.json`.

Paths you pass to subcommands (such as `project/in/work`) are always resolved
relative to `--work-root`; you can provide absolute paths if you prefer. The
staging copy lives under the staging root and defaults to the same name as the
project unless you override it with `--as-name`.

### `clone`

Prepare a fresh staging checkout that tracks a temporary branch on the shared
remote. Typical usage looks like this:

```bash
python3 stage_sync.py --work-root ~/code clone apps/backend
```

- `apps/backend` is the repository inside the work root you want to stage.
- The staging copy ends up at `<staging-root>/apps/backend` unless you pick a
  different name with `--as-name`.
- Use `--force` if you want to replace an existing staging copy with a fresh
  clone.

`demo-stage` in the examples below is just a friendly name for the staging
directory:

```bash
python3 stage_sync.py --work-root ~/code clone apps/backend --as-name demo-stage
```

That command keeps your original repository at `~/code/apps/backend/`, but the
throwaway staging checkout now lives at `<staging-root>/demo-stage/`.

### `sync-back`

Push the staging work to the remote temporary branch and fast-forward (or hard
reset) the work repository so it matches.

```bash
python3 stage_sync.py --work-root ~/code sync-back demo-stage
```

- `demo-stage` must match the directory name under the staging root that you
created during `clone` (either the default project name or the value passed to
`--as-name`).
- If you cloned without `--as-name`, use the project path itself (for example,
  `sync-back apps/backend`).
- Use `--auto-checkout` if your work repository is on another branch and you
want the script to switch branches for you.
- Use `--force` to hard reset the work repository instead of performing a
fast-forward merge.

If your work repository uses a different name than the staging directory, pass
`--work-name` so the script knows which repository to fast-forward:

```bash
python3 stage_sync.py --work-root ~/code sync-back demo-stage --work-name apps/backend
```

### `list`

Show the recorded staging/work mappings stored in `.staging_sync.json`.

Example commands:

```bash
# Create or refresh the staging copy
python3 stage_sync.py --work-root ~/code clone apps/backend
python3 stage_sync.py --work-root ~/code clone apps/backend --force
python3 stage_sync.py --work-root ~/code clone apps/backend --as-name demo-stage

# Push changes from staging back to the work tree
python3 stage_sync.py --work-root ~/code sync-back apps/backend
python3 stage_sync.py --work-root ~/code sync-back demo-stage --auto-checkout
python3 stage_sync.py --work-root ~/code sync-back demo-stage --force

# Inspect recorded mappings
python3 stage_sync.py --work-root ~/code list
```

### Common Flags

- `--allow-dirty-stage`, `--allow-dirty-work`: bypass clean working tree
  checks (use sparingly).
- `--branch`: choose which work branch should receive the staged changes.
- `--temp-branch`: override the generated temporary remote branch name.
- `--auto-checkout`: switch the work repo to the target branch automatically
  if it is on a different branch.
- `--force`: during `clone`, replaces the staging directory; during
  `sync-back`, performs a hard reset instead of a fast-forward merge.

## Temporary Branch Lifecycle

- Temporary branches are named `staging-sync/<staging-name>-<base-branch>-<timestamp>`,
  so the staging directory name (not its path) is what shows up on the remote.
- `sync-back` always publishes the staging work by pushing to that temporary
  branch and then removes it remotely with `git push origin :refs/heads/<temp>`
  in a `finally` block, even if the fast-forward or push fails.
- The staging repository keeps its local branch so you can continue iterating,
  and the next `sync-back` will re-create the remote branch automatically if it
  was deleted.
- There is no flag to skip the cleanup; use `--temp-branch` only to control the
  name when you need to inspect the remote manually before the script finishes.

## Configuration File

The script stores per-staging metadata in `.staging_sync.json` inside the
staging root (or a custom path if you pass `--config-path`). You usually do not
need to edit this file manually; it keeps track of the work/staging paths, the
base branch the staging copy was created from, and the temporary branch names
used for the last sync.

## Tips

- Always commit or stash changes in both repos before running `sync-back` to
  avoid losing work.
- After finishing a staging review, remove the staging directory manually if
  you no longer need it. The script will recreate it on the next `clone`.
