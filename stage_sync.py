#!/usr/bin/env python3
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

DEFAULT_STAGING_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_NAME = ".staging_sync.json"

STAGING_ROOT: Optional[Path] = None
WORK_ROOT: Optional[Path] = None
CONFIG_PATH: Optional[Path] = None
DEFAULT_REMOTE = "origin"
TEMP_BRANCH_PREFIX = "staging-sync"


def fail(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)


def run_git(
    repo_path: Path,
    args,
    *,
    check: bool = True,
    capture_output: bool = True,
):
    cmd = ["git", "-C", str(repo_path), *args]
    result = subprocess.run(cmd, text=True, capture_output=capture_output)
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, result.stdout, result.stderr
        )
    if capture_output:
        return result.stdout
    return result


def configure_paths(
    staging_root: Path,
    work_root: Path,
    config_path: Optional[Path] = None,
) -> None:
    global STAGING_ROOT, WORK_ROOT, CONFIG_PATH

    STAGING_ROOT = staging_root.expanduser().resolve()
    WORK_ROOT = work_root.expanduser().resolve()
    if config_path is not None:
        CONFIG_PATH = config_path.expanduser().resolve()
    else:
        CONFIG_PATH = STAGING_ROOT / DEFAULT_CONFIG_NAME


def get_staging_root() -> Path:
    if STAGING_ROOT is None:
        fail("Staging root not configured. Provide --staging-root.")
    return STAGING_ROOT


def get_work_root() -> Path:
    if WORK_ROOT is None:
        fail("Work root not configured. Provide --work-root.")
    return WORK_ROOT


def get_config_path() -> Path:
    if CONFIG_PATH is None:
        fail("Configuration path not initialized. Provide --staging-root or --config-path.")
    return CONFIG_PATH


def resolve_under_root(base: Path, path_candidate, label: str) -> Path:
    candidate = Path(path_candidate)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (base / candidate).resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        fail(f"{label} {resolved} is outside of {base}.")
    return resolved


def ensure_git_repo(path: Path, label: str) -> None:
    if not (path / ".git").exists():
        fail(f"{label} does not look like a git repository (missing .git directory).")


def ensure_clean(path: Path, label: str) -> None:
    status = run_git(path, ["status", "--porcelain"]).strip()
    if status:
        fail(
            f"{label} has uncommitted changes. Commit or stash them, "
            f"or re-run with the matching --allow-dirty flag."
        )


def get_current_branch(path: Path, label: str) -> str:
    branch = run_git(path, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    if branch == "HEAD":
        fail(f"{label} is in a detached HEAD state. Check out a branch first.")
    return branch


def get_remote_url(path: Path, remote: str = DEFAULT_REMOTE) -> str:
    try:
        return run_git(path, ["remote", "get-url", remote]).strip()
    except subprocess.CalledProcessError as exc:
        fail(
            f"Repository {path} does not have a remote named {remote}."
            f"\nGit output:\n{exc.stderr or exc.stdout or exc}"
        )


def ensure_branch_on_remote(path: Path, branch: str, remote: str) -> None:
    output = run_git(path, ["ls-remote", "--heads", remote, branch]).strip()
    if output:
        return
    print(
        f"Remote branch {branch} not found on {remote}. Pushing current branch before cloning."
    )
    run_git(
        path,
        ["push", "-u", remote, f"{branch}:{branch}"],
        capture_output=False,
    )


def load_config() -> dict:
    config_path = get_config_path()
    if config_path.exists():
        try:
            return json.loads(config_path.read_text())
        except json.JSONDecodeError as exc:
            fail(f"Configuration file {config_path} is not valid JSON: {exc}.")
    return {"projects": {}}


def save_config(config: dict) -> None:
    config_path = get_config_path()
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True))


def init_staging_repo(stage_path: Path, remote_url: str, branch: str) -> None:
    stage_path.mkdir(parents=True, exist_ok=True)
    run_git(stage_path, ["init"], capture_output=False)
    run_git(stage_path, ["remote", "add", DEFAULT_REMOTE, remote_url])
    run_git(stage_path, ["fetch", DEFAULT_REMOTE, branch], capture_output=False)
    run_git(
        stage_path,
        ["checkout", "-B", branch, f"{DEFAULT_REMOTE}/{branch}"],
        capture_output=False,
    )


def sanitize_for_branch(component: str) -> str:
    safe = []
    for ch in component:
        if ch.isalnum() or ch in "-_.":
            safe.append(ch)
        else:
            safe.append("-")
    sanitized = "".join(safe).strip("-")
    return sanitized or "project"


def make_temp_branch_name(stage_rel: Path, branch: str) -> str:
    sanitized_stage = sanitize_for_branch(str(stage_rel))
    sanitized_branch = sanitize_for_branch(branch)
    suffix = int(time.time())
    return f"{TEMP_BRANCH_PREFIX}/{sanitized_stage}-{sanitized_branch}-{suffix}"


def clone_project(args) -> None:
    work_root = get_work_root()
    staging_root = get_staging_root()

    if not work_root.exists():
        fail(f"Expected work directory at {work_root}, but it does not exist.")

    project_rel = Path(args.project)
    source = resolve_under_root(work_root, project_rel, "Project path")
    if not source.exists():
        fail(f"Source project {source} does not exist.")
    if not source.is_dir():
        fail(f"Source project {source} is not a directory.")
    ensure_git_repo(source, f"Source project {source}")

    branch = get_current_branch(source, f"Source project {source}")
    remote_url = get_remote_url(source)

    ensure_branch_on_remote(source, branch, DEFAULT_REMOTE)

    target_name = args.as_name or project_rel.name
    target = resolve_under_root(staging_root, target_name, "Staging target")
    if target.exists():
        if not args.force:
            fail(
                f"Target staging directory {target} already exists. "
                f"Use --force to replace it."
            )
        if target == source:
            fail("Refusing to remove the source project.")
        shutil.rmtree(target)

    print(
        f"Initializing staging repository at {target} to track {remote_url} ({branch})."
    )
    init_staging_repo(target, remote_url, branch)

    config = load_config()
    config.setdefault("projects", {})
    config["projects"][str(Path(target).relative_to(staging_root))] = {
        "work_name": str(project_rel),
        "work_path": str(source),
        "staging_path": str(target),
        "branch": branch,
        "remote": remote_url,
    }
    save_config(config)
    print(f"Staging repository ready. Branch {branch} checked out from origin.")


def sync_back(args) -> None:
    stage_rel = Path(args.staging_name)
    staging_root = get_staging_root()
    work_root = get_work_root()

    stage_path = resolve_under_root(staging_root, stage_rel, "Staging path")
    if not stage_path.exists():
        fail(f"Staging project {stage_path} does not exist.")
    ensure_git_repo(stage_path, f"Staging project {stage_path}")

    config = load_config()
    entry = config.get("projects", {}).get(str(stage_rel))

    if args.work_name:
        work_path = resolve_under_root(work_root, Path(args.work_name), "Work path")
        work_label = args.work_name
    elif entry:
        work_path = Path(entry["work_path"])
        work_label = entry.get("work_name", work_path.name)
    else:
        work_path = resolve_under_root(work_root, stage_rel.name, "Work path")
        work_label = stage_rel.name

    if not work_path.exists():
        fail(f"Work project {work_path} does not exist.")
    ensure_git_repo(work_path, f"Work project {work_path}")

    if not args.allow_dirty_stage:
        ensure_clean(stage_path, f"Staging project {stage_rel}")
    if not args.allow_dirty_work:
        ensure_clean(work_path, f"Work project {work_label}")

    branch = args.branch
    if not branch:
        branch = get_current_branch(stage_path, f"Staging project {stage_rel}")
    else:
        branch_exists = run_git(stage_path, ["branch", "--list", branch]).strip()
        if not branch_exists:
            fail(f"Branch {branch} not found in staging repository.")

    staging_remote_url = get_remote_url(stage_path)
    work_remote_url = get_remote_url(work_path)
    if work_remote_url != staging_remote_url:
        fail(
            "Work repository remote URL does not match staging remote URL."
            f"\nWork:    {work_remote_url}\nStaging: {staging_remote_url}"
        )

    temp_branch = args.temp_branch or make_temp_branch_name(stage_rel, branch)

    print(
        f"Pushing staging HEAD ({branch}) to temporary remote branch {temp_branch}"
    )
    run_git(
        stage_path,
        ["push", DEFAULT_REMOTE, f"HEAD:refs/heads/{temp_branch}"],
        capture_output=False,
    )

    try:
        print(f"Fetching {temp_branch} into work repository {work_path}")
        run_git(work_path, ["fetch", DEFAULT_REMOTE, temp_branch], capture_output=False)

        branch_exists = True
        try:
            run_git(work_path, ["rev-parse", "--verify", f"refs/heads/{branch}"])
        except subprocess.CalledProcessError:
            branch_exists = False

        if not branch_exists:
            print(f"Creating local branch {branch} from origin/{temp_branch}")
            run_git(
                work_path,
                ["checkout", "-B", branch, f"{DEFAULT_REMOTE}/{temp_branch}"],
                capture_output=False,
            )
        else:
            current_work_branch = get_current_branch(work_path, f"Work project {work_label}")
            if current_work_branch != branch:
                if args.auto_checkout:
                    print(f"Checking out branch {branch} in work repository")
                    run_git(work_path, ["checkout", branch], capture_output=False)
                else:
                    fail(
                        f"Work repository is on branch {current_work_branch}. "
                        f"Use --auto-checkout to switch automatically or check out {branch} manually."
                    )
            if args.force:
                print(f"Hard resetting work branch {branch} to origin/{temp_branch}")
                run_git(
                    work_path,
                    ["reset", "--hard", f"{DEFAULT_REMOTE}/{temp_branch}"],
                    capture_output=False,
                )
            else:
                merge_proc = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(work_path),
                        "merge",
                        "--ff-only",
                        f"{DEFAULT_REMOTE}/{temp_branch}",
                    ],
                    text=True,
                    capture_output=True,
                )
                if merge_proc.returncode != 0:
                    fail(
                        "Unable to fast-forward work branch to match temporary remote branch.\n"
                        f"git merge output:\n{merge_proc.stdout}{merge_proc.stderr}"
                    )
                if merge_proc.stdout.strip():
                    print(merge_proc.stdout.strip())

        print(f"Pushing updated branch {branch} back to origin")
        run_git(work_path, ["push", DEFAULT_REMOTE, branch], capture_output=False)
    finally:
        print(f"Removing temporary remote branch {temp_branch}")
        try:
            run_git(
                work_path,
                ["push", DEFAULT_REMOTE, f":refs/heads/{temp_branch}"],
                capture_output=False,
            )
        except subprocess.CalledProcessError as exc:
            warning = exc.stderr or exc.stdout or str(exc)
            print(
                f"Warning: failed to delete temporary branch {temp_branch}.\n{warning}",
                file=sys.stderr,
            )

    config.setdefault("projects", {})
    config_entry = {
        "work_name": work_label,
        "work_path": str(work_path),
        "staging_path": str(stage_path),
        "branch": branch,
        "remote": staging_remote_url,
        "last_temp_branch": temp_branch,
    }
    config["projects"][str(stage_rel)] = config_entry
    save_config(config)
    print(
        f"Sync complete. Work project {work_path} now contains origin/{branch} from staging."
    )


def list_projects(_args) -> None:
    config = load_config()
    projects = config.get("projects", {})
    if not projects:
        print("No staging project mappings recorded.")
        return

    for name, data in sorted(projects.items()):
        work_path = data.get("work_path", "?")
        staging_path = data.get("staging_path", "?")
        work_name = data.get("work_name", Path(work_path).name if work_path != "?" else "?")
        branch = data.get("branch", "?")
        remote = data.get("remote", "?")
        temp_branch = data.get("last_temp_branch")
        print(f"{name} -> work:{work_name} branch:{branch}")
        print(f"  staging: {staging_path}")
        print(f"  work:    {work_path}")
        print(f"  remote:  {remote}")
        if temp_branch:
            print(f"  last-temp-branch: {temp_branch}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manage staging copies of local git projects using a shared remote."
    )
    parser.add_argument(
        "--staging-root",
        help=(
            "Path to the staging root directory. Defaults to the directory "
            "containing this script."
        ),
    )
    parser.add_argument(
        "--work-root",
        help="Path to the work directory that contains your source repositories.",
    )
    parser.add_argument(
        "--config-path",
        help=(
            "Location of the metadata JSON file. Defaults to "
            f"<staging-root>/{DEFAULT_CONFIG_NAME}."
        ),
    )
    subparsers = parser.add_subparsers(dest="command")

    clone_parser = subparsers.add_parser(
        "clone", help="Prepare a staging repository for a project"
    )
    clone_parser.add_argument(
        "project", help="Project path (relative to the configured work directory)"
    )
    clone_parser.add_argument(
        "--as-name", help="Name to use for the staging copy. Defaults to the project name."
    )
    clone_parser.add_argument(
        "--force", action="store_true", help="Replace existing staging directory if it exists."
    )
    clone_parser.set_defaults(func=clone_project)

    sync_parser = subparsers.add_parser(
        "sync-back", help="Push staging changes and fast-forward the work repository"
    )
    sync_parser.add_argument("staging_name", help="Staging directory name")
    sync_parser.add_argument(
        "--work-name",
        help="Override work project name if it differs from the staging name",
    )
    sync_parser.add_argument(
        "--branch", help="Branch to sync back. Defaults to the staging HEAD branch."
    )
    sync_parser.add_argument(
        "--temp-branch",
        help="Explicit temporary branch name to use on origin during sync.",
    )
    sync_parser.add_argument(
        "--auto-checkout",
        action="store_true",
        help="Automatically switch the work repo to the target branch if needed.",
    )
    sync_parser.add_argument(
        "--force",
        action="store_true",
        help="Use git reset --hard if a fast-forward merge is not desired.",
    )
    sync_parser.add_argument(
        "--allow-dirty-stage",
        action="store_true",
        help="Allow syncing even if the staging repo has uncommitted changes.",
    )
    sync_parser.add_argument(
        "--allow-dirty-work",
        action="store_true",
        help="Allow syncing even if the work repo has uncommitted changes.",
    )
    sync_parser.set_defaults(func=sync_back)

    list_parser = subparsers.add_parser("list", help="List known staging/work mappings")
    list_parser.set_defaults(func=list_projects)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    staging_root_input = Path(args.staging_root).expanduser() if args.staging_root else DEFAULT_STAGING_ROOT
    work_root_input = args.work_root
    if work_root_input is None:
        fail("--work-root is required. Provide the path to your work directory.")
    work_root_path = Path(work_root_input).expanduser()

    config_path_input = args.config_path
    config_path_path = (
        Path(config_path_input).expanduser() if config_path_input else None
    )

    configure_paths(staging_root_input, work_root_path, config_path_path)

    try:
        args.func(args)
    except subprocess.CalledProcessError as err:
        message = err.stderr or err.stdout or str(err)
        fail(message.strip())


if __name__ == "__main__":
    main()
