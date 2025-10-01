# Staging Sync Utility

This repository contains `stage_sync.py`, a small helper for managing temporary
"staging" checkouts of local Git projects that all point at the same remote.
It automates cloning a clean copy of a project into the staging area and then
fast-forwarding the original working copy with the changes you made in staging.

## Workflow Overview

You provide the script with two directories when running commands:

- A **work root** (`--work-root`) that contains your canonical Git repositories.
- A **staging root** (`--staging-root`, defaults to the directory containing this
  script) that holds throwaway staging copies.

When you run `clone`, the script:

1. Ensures the target project inside the work root exists, is clean, and is on a
   branch that also exists on the remote (default remote name is `origin`).
2. Pushes the current HEAD to a uniquely named temporary remote branch and
   bootstraps a matching repository under the staging root that tracks that
   temporary branch.
3. Records the mapping in `.staging_sync.json` so future syncs can find the
   right source and destination.

When you run `sync-back`, the script:

1. Validates that both the staging copy and the work repository are clean
   unless you explicitly allow dirtiness.
2. Pushes the staging HEAD to a temporary branch on the shared remote (reusing
   the one created during `clone` unless you override it).
3. Fast-forwards (or hard-resets with `--force`) the original work branch that
   the staging copy was based on (or a branch you specify with `--branch`).
4. Pushes the updated branch back to the remote and cleans up the temporary
   branch.

The `list` subcommand prints all recorded mappings from `.staging_sync.json`.

## Prerequisites

- Python 3.8 or newer.
- Git available on your PATH.
- A work directory populated with Git repositories that share a remote named
  `origin`.
- A staging directory containing this script, unless you provide an alternate
  location via `--staging-root`.

## Usage

Global options:

- `--work-root PATH` (required) – path to your work directory.
- `--staging-root PATH` – override the staging directory. Defaults to the
  directory that contains `stage_sync.py`.
- `--config-path PATH` – override where metadata is stored. Defaults to
  `<staging-root>/.staging_sync.json`.

Example commands:

```bash
python3 stage_sync.py --work-root /path/to/work clone project/in/work
python3 stage_sync.py --work-root /path/to/work clone project/in/work --force
python3 stage_sync.py --work-root /path/to/work clone project/in/work --as-name demo-stage

python3 stage_sync.py --work-root /path/to/work sync-back demo-stage
python3 stage_sync.py --work-root /path/to/work sync-back demo-stage --auto-checkout
python3 stage_sync.py --work-root /path/to/work sync-back demo-stage --force

python3 stage_sync.py --work-root /path/to/work list
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
