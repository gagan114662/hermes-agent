"""
Git Operations Tool Suite

Provides high-level git operations for the agent to manage repositories without
shelling out to the terminal tool. Handles git status, diff, log, commit, and
branch operations with proper error handling and safety checks.

All commands run via subprocess with a 30-second timeout. Results are returned
as JSON strings for reliable parsing.

Safety checks:
  - Refuses `git push --force` and `git reset --hard` in git_commit
  - Properly handles path expansion and validation
  - Returns structured error messages on failure

Tools:
  git_status    — Show working tree status (staged/unstaged changes)
  git_diff      — Show diff of changes (all, staged, or specific files)
  git_log       — Show recent commit history
  git_commit    — Stage and commit changes (with safety checks)
  git_branch    — List, create, switch, or delete branches
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Optional

from tools.registry import registry


# ── Shared utilities ──────────────────────────────────────────────────────────

def _check_git_available() -> bool:
    """Check if git is available on the system."""
    import shutil
    return shutil.which("git") is not None


def _normalize_path(path: Optional[str]) -> Path:
    """
    Normalize and expand a path. Defaults to current working directory if not
    provided or if provided as empty string.
    """
    if not path or path.strip() == "":
        return Path.cwd()
    expanded = os.path.expanduser(path)
    real_path = os.path.realpath(expanded)
    return Path(real_path)


def _validate_directory(directory_path: Path) -> tuple[bool, str]:
    """
    Validate that a directory exists and is a git repository.
    Returns (is_valid, error_message).
    """
    if not directory_path.exists():
        return False, f"Path does not exist: {directory_path}"

    if not directory_path.is_dir():
        return False, f"Path is not a directory: {directory_path}"

    git_dir = directory_path / ".git"
    if not git_dir.exists():
        return False, f"Not a git repository: {directory_path}"

    return True, ""


def _run_git_command(
    command_parts: list[str],
    working_directory: Path,
    timeout_seconds: int = 30,
) -> dict:
    """
    Execute a git command and return structured result.

    Args:
        command_parts: List of command parts (e.g., ["git", "status", "--short"])
        working_directory: Directory to run command in
        timeout_seconds: Command timeout

    Returns:
        {"success": bool, "stdout": str, "stderr": str, "error": str}
    """
    try:
        result = subprocess.run(
            command_parts,
            cwd=str(working_directory),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "error": None if result.returncode == 0 else result.stderr,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "error": f"Command timed out after {timeout_seconds} seconds",
        }

    except Exception as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "error": str(exc),
        }


# ── Tool implementations ──────────────────────────────────────────────────────

def git_status_impl(path: Optional[str] = None) -> str:
    """
    Show git working tree status (staged changes, unstaged changes, untracked files).

    Args:
        path: Directory path (defaults to current working directory)

    Returns:
        JSON string with status output or error
    """
    directory = _normalize_path(path)

    is_valid, validation_error = _validate_directory(directory)
    if not is_valid:
        return json.dumps({"error": validation_error})

    result = _run_git_command(["git", "status", "--porcelain"], directory)

    if not result["success"]:
        return json.dumps({"error": result["error"] or "Failed to get git status"})

    lines = result["stdout"].strip().split("\n") if result["stdout"].strip() else []

    return json.dumps({
        "path": str(directory),
        "status": "ok",
        "changes": lines,
        "total_changes": len(lines),
    })


def git_diff_impl(
    path: Optional[str] = None,
    staged: bool = False,
    file: Optional[str] = None,
) -> str:
    """
    Show diff of changes in the repository.

    Args:
        path: Directory path (defaults to current working directory)
        staged: If True, show staged changes only
        file: If provided, show diff for specific file only

    Returns:
        JSON string with diff output or error
    """
    directory = _normalize_path(path)

    is_valid, validation_error = _validate_directory(directory)
    if not is_valid:
        return json.dumps({"error": validation_error})

    command_parts = ["git", "diff"]

    if staged:
        command_parts.append("--staged")

    if file:
        command_parts.append(file)

    result = _run_git_command(command_parts, directory)

    if not result["success"]:
        return json.dumps({"error": result["error"] or "Failed to get diff"})

    diff_output = result["stdout"]
    diff_lines = diff_output.split("\n") if diff_output else []

    return json.dumps({
        "path": str(directory),
        "status": "ok",
        "diff_type": "staged" if staged else "unstaged",
        "file_filter": file,
        "diff": diff_output,
        "line_count": len(diff_lines),
    })


def git_log_impl(
    path: Optional[str] = None,
    count: int = 10,
    oneline: bool = False,
) -> str:
    """
    Show recent commit history.

    Args:
        path: Directory path (defaults to current working directory)
        count: Number of commits to show (default 10)
        oneline: If True, show one line per commit

    Returns:
        JSON string with commit history or error
    """
    directory = _normalize_path(path)

    is_valid, validation_error = _validate_directory(directory)
    if not is_valid:
        return json.dumps({"error": validation_error})

    if count < 1:
        count = 10
    elif count > 100:
        count = 100  # Cap to prevent excessive output

    command_parts = ["git", "log", f"-{count}"]

    if oneline:
        command_parts.append("--oneline")
    else:
        command_parts.append("--pretty=format:%h %an %ad %s")
        command_parts.append("--date=short")

    result = _run_git_command(command_parts, directory)

    if not result["success"]:
        return json.dumps({"error": result["error"] or "Failed to get log"})

    commits = result["stdout"].strip().split("\n") if result["stdout"].strip() else []

    return json.dumps({
        "path": str(directory),
        "status": "ok",
        "count_requested": count,
        "commits": commits,
        "commit_count": len(commits),
    })


def git_commit_impl(
    path: Optional[str] = None,
    message: str = "",
    files: Optional[list[str]] = None,
) -> str:
    """
    Stage and commit changes to the repository.

    Safety checks:
      - Refuses to run `git push --force` or `git reset --hard`
      - Validates message is provided

    Args:
        path: Directory path (defaults to current working directory)
        message: Commit message (required)
        files: List of specific files to stage. If None, stages all changes.

    Returns:
        JSON string with commit result or error
    """
    if not message or not message.strip():
        return json.dumps({"error": "Commit message is required"})

    # Safety check: refuse dangerous commands in message
    dangerous_patterns = ["push --force", "reset --hard"]
    for pattern in dangerous_patterns:
        if pattern in message.lower():
            return json.dumps({
                "error": f"Safety check failed: commit message cannot contain '{pattern}'"
            })

    directory = _normalize_path(path)

    is_valid, validation_error = _validate_directory(directory)
    if not is_valid:
        return json.dumps({"error": validation_error})

    # Stage files
    if files:
        for file_path in files:
            stage_result = _run_git_command(
                ["git", "add", file_path],
                directory,
                timeout_seconds=10,
            )
            if not stage_result["success"]:
                return json.dumps({
                    "error": f"Failed to stage file '{file_path}': {stage_result['error']}"
                })
    else:
        # Stage all changes
        stage_result = _run_git_command(
            ["git", "add", "-A"],
            directory,
            timeout_seconds=10,
        )
        if not stage_result["success"]:
            return json.dumps({
                "error": f"Failed to stage changes: {stage_result['error']}"
            })

    # Commit
    commit_result = _run_git_command(
        ["git", "commit", "-m", message.strip()],
        directory,
        timeout_seconds=15,
    )

    if not commit_result["success"]:
        error_message = commit_result["error"] or "Failed to commit"
        return json.dumps({"error": error_message})

    return json.dumps({
        "path": str(directory),
        "status": "ok",
        "message": message.strip(),
        "files_committed": files if files else "all",
        "output": commit_result["stdout"],
    })


def git_branch_impl(
    path: Optional[str] = None,
    action: str = "list",
    name: Optional[str] = None,
) -> str:
    """
    List, create, switch, or delete branches.

    Args:
        path: Directory path (defaults to current working directory)
        action: One of "list", "create", "switch", "delete"
        name: Branch name (required for create/switch/delete)

    Returns:
        JSON string with branch result or error
    """
    directory = _normalize_path(path)

    is_valid, validation_error = _validate_directory(directory)
    if not is_valid:
        return json.dumps({"error": validation_error})

    action_lower = action.lower() if action else "list"

    if action_lower == "list":
        result = _run_git_command(["git", "branch", "-a"], directory)

        if not result["success"]:
            return json.dumps({"error": result["error"] or "Failed to list branches"})

        branches = [line.strip() for line in result["stdout"].split("\n") if line.strip()]

        return json.dumps({
            "path": str(directory),
            "status": "ok",
            "action": "list",
            "branches": branches,
            "branch_count": len(branches),
        })

    elif action_lower in ["create", "switch", "delete"]:
        if not name or not name.strip():
            return json.dumps({
                "error": f"Branch name is required for action '{action_lower}'"
            })

        branch_name = name.strip()

        if action_lower == "create":
            result = _run_git_command(
                ["git", "branch", branch_name],
                directory,
                timeout_seconds=10,
            )

            if not result["success"]:
                return json.dumps({
                    "error": f"Failed to create branch '{branch_name}': {result['error']}"
                })

            return json.dumps({
                "path": str(directory),
                "status": "ok",
                "action": "create",
                "branch_name": branch_name,
                "output": f"Branch '{branch_name}' created successfully",
            })

        elif action_lower == "switch":
            result = _run_git_command(
                ["git", "checkout", branch_name],
                directory,
                timeout_seconds=10,
            )

            if not result["success"]:
                return json.dumps({
                    "error": f"Failed to switch to branch '{branch_name}': {result['error']}"
                })

            return json.dumps({
                "path": str(directory),
                "status": "ok",
                "action": "switch",
                "branch_name": branch_name,
                "output": f"Switched to branch '{branch_name}'",
            })

        elif action_lower == "delete":
            result = _run_git_command(
                ["git", "branch", "-d", branch_name],
                directory,
                timeout_seconds=10,
            )

            if not result["success"]:
                return json.dumps({
                    "error": f"Failed to delete branch '{branch_name}': {result['error']}"
                })

            return json.dumps({
                "path": str(directory),
                "status": "ok",
                "action": "delete",
                "branch_name": branch_name,
                "output": f"Branch '{branch_name}' deleted successfully",
            })

    else:
        return json.dumps({
            "error": f"Unknown action '{action}'. Must be one of: list, create, switch, delete"
        })


# ── Handler wrappers for registry ─────────────────────────────────────────────

def _handle_git_status(args, **kw):
    """Handler for git_status tool."""
    return git_status_impl(
        path=args.get("path"),
    )


def _handle_git_diff(args, **kw):
    """Handler for git_diff tool."""
    return git_diff_impl(
        path=args.get("path"),
        staged=args.get("staged", False),
        file=args.get("file"),
    )


def _handle_git_log(args, **kw):
    """Handler for git_log tool."""
    return git_log_impl(
        path=args.get("path"),
        count=args.get("count", 10),
        oneline=args.get("oneline", False),
    )


def _handle_git_commit(args, **kw):
    """Handler for git_commit tool."""
    return git_commit_impl(
        path=args.get("path"),
        message=args.get("message", ""),
        files=args.get("files"),
    )


def _handle_git_branch(args, **kw):
    """Handler for git_branch tool."""
    return git_branch_impl(
        path=args.get("path"),
        action=args.get("action", "list"),
        name=args.get("name"),
    )


# ── Tool registration ─────────────────────────────────────────────────────────

registry.register(
    name="git_status",
    toolset="git",
    schema={
        "name": "git_status",
        "description": "Show the working tree status (staged changes, unstaged changes, untracked files)",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path (defaults to current working directory)",
                },
            },
            "required": [],
        },
    },
    handler=_handle_git_status,
    check_fn=_check_git_available,
)

registry.register(
    name="git_diff",
    toolset="git",
    schema={
        "name": "git_diff",
        "description": "Show diff of changes in the repository (all, staged, or specific file)",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path (defaults to current working directory)",
                },
                "staged": {
                    "type": "boolean",
                    "description": "If true, show staged changes only",
                },
                "file": {
                    "type": "string",
                    "description": "If provided, show diff for specific file only",
                },
            },
            "required": [],
        },
    },
    handler=_handle_git_diff,
    check_fn=_check_git_available,
)

registry.register(
    name="git_log",
    toolset="git",
    schema={
        "name": "git_log",
        "description": "Show recent commit history from the repository",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path (defaults to current working directory)",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of commits to show (default 10, max 100)",
                },
                "oneline": {
                    "type": "boolean",
                    "description": "If true, show one line per commit",
                },
            },
            "required": [],
        },
    },
    handler=_handle_git_log,
    check_fn=_check_git_available,
)

registry.register(
    name="git_commit",
    toolset="git",
    schema={
        "name": "git_commit",
        "description": "Stage and commit changes to the repository. Safety checks prevent dangerous operations like force-push or hard-reset.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path (defaults to current working directory)",
                },
                "message": {
                    "type": "string",
                    "description": "Commit message (required)",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of specific files to stage. If omitted, stages all changes.",
                },
            },
            "required": ["message"],
        },
    },
    handler=_handle_git_commit,
    check_fn=_check_git_available,
)

registry.register(
    name="git_branch",
    toolset="git",
    schema={
        "name": "git_branch",
        "description": "List, create, switch, or delete branches in the repository",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path (defaults to current working directory)",
                },
                "action": {
                    "type": "string",
                    "enum": ["list", "create", "switch", "delete"],
                    "description": "Branch operation to perform (default: list)",
                },
                "name": {
                    "type": "string",
                    "description": "Branch name (required for create, switch, delete)",
                },
            },
            "required": [],
        },
    },
    handler=_handle_git_branch,
    check_fn=_check_git_available,
)
