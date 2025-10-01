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
2. Creates (or replaces with `--force`) a matching repository under the staging
   root, adds the same remote, fetches the branch, and checks it out.
3. Records the mapping in `.staging_sync.json` so future syncs can find the
   right source and destination.

When you run `sync-back`, the script:

1. Validates that both the staging copy and the work repository are clean
   unless you explicitly allow dirtiness.
2. Pushes the staging HEAD to a temporary branch on the shared remote.
3. Fast-forwards (or hard-resets with `--force`) the work repository's branch to
   match the staging changes.
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
- `--branch`: pick a different branch than the staging HEAD while syncing.
- `--temp-branch`: override the generated temporary remote branch name.
- `--auto-checkout`: switch the work repo to the target branch automatically
  if it is on a different branch.
- `--force`: during `clone`, replaces the staging directory; during
  `sync-back`, performs a hard reset instead of a fast-forward merge.

## Configuration File

The script stores per-staging metadata in `.staging_sync.json` inside the
staging root (or a custom path if you pass `--config-path`). You usually do not
need to edit this file manually; it keeps track of the last used branch,
staging/work paths, and the temporary branch name.

## Tips

- Always commit or stash changes in both repos before running `sync-back` to
  avoid losing work.
- After finishing a staging review, remove the staging directory manually if
  you no longer need it. The script will recreate it on the next `clone`.
