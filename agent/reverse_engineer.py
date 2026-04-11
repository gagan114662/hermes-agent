"""Reverse engineering engine for /revengineer.

Takes a local codebase path (or GitHub URL) and extracts:
  - Architecture: components, data flow, tech stack
  - Patterns: repeatable behaviors that could become skills
  - Key behaviors: what the system actually does
  - Dependencies: runtime + dev

Outputs (written by the reverse-engineer agent after receiving the scan):
  - ~/.hermes/context/<repo-name>.md   — auto-injected into every future agent
  - ~/.hermes/skills/<pattern>/SKILL.md — one per discovered skill pattern
  - ~/.hermes/specs/<repo-name>.md     — reverse-engineered HermesSpec

Usage:
    /revengineer .
    /revengineer ~/projects/my-app
    /revengineer https://github.com/owner/repo  (clones to /tmp first)
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Max chars to read from any single file
_FILE_MAX_CHARS = 4_000

# Max total chars for the entire key-files block fed to the agent
_CONTEXT_MAX_CHARS = 40_000

# Files we always try to read (in priority order)
_PRIORITY_FILES = [
    "README.md",
    "README.rst",
    "README.txt",
    "README",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "Makefile",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".env.example",
    "CONTRIBUTING.md",
    "ARCHITECTURE.md",
    "DESIGN.md",
    "docs/architecture.md",
    "docs/design.md",
]

# Directories to skip entirely
_SKIP_DIRS = {
    ".git", ".svn", ".hg",
    "node_modules", "__pycache__", ".venv", "venv", ".env",
    "dist", "build", "target", "out", ".next", ".nuxt",
    "coverage", "htmlcov", ".pytest_cache", ".mypy_cache",
    "vendor", "third_party", ".tox", "eggs", "*.egg-info",
}

# File extensions to include in the tree (others are shown as counts)
_CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
    ".rb", ".php", ".swift", ".kt", ".cs", ".cpp", ".c", ".h",
    ".sh", ".bash", ".zsh", ".fish",
    ".yaml", ".yml", ".toml", ".json", ".env",
    ".md", ".rst", ".txt",
    ".sql", ".graphql", ".proto",
}

_MAX_TREE_DEPTH = 4
_MAX_TREE_ENTRIES_PER_DIR = 30


# ---------------------------------------------------------------------------
# Directory tree builder
# ---------------------------------------------------------------------------

def build_tree(root: Path, max_depth: int = _MAX_TREE_DEPTH) -> str:
    """Build a compact directory tree string for the given root."""
    lines: list[str] = [f"{root.name}/"]
    _walk_tree(root, lines, depth=0, max_depth=max_depth, prefix="")
    return "\n".join(lines)


def _walk_tree(
    directory: Path,
    lines: list[str],
    depth: int,
    max_depth: int,
    prefix: str,
) -> None:
    if depth >= max_depth:
        lines.append(f"{prefix}  ... (depth limit)")
        return

    try:
        entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return

    # Filter out skipped dirs
    entries = [
        e for e in entries
        if not (e.is_dir() and (e.name in _SKIP_DIRS or e.name.startswith(".")))
        and not (e.is_file() and e.name.startswith(".") and e.suffix not in _CODE_EXTENSIONS)
    ]

    # Cap per-directory entries
    shown = entries[:_MAX_TREE_ENTRIES_PER_DIR]
    hidden = len(entries) - len(shown)

    for i, entry in enumerate(shown):
        is_last = i == len(shown) - 1 and hidden == 0
        connector = "└── " if is_last else "├── "
        child_prefix = prefix + ("    " if is_last else "│   ")

        if entry.is_dir():
            lines.append(f"{prefix}{connector}{entry.name}/")
            _walk_tree(entry, lines, depth + 1, max_depth, child_prefix)
        else:
            size_hint = ""
            try:
                size = entry.stat().st_size
                if size > 100_000:
                    size_hint = f"  [{size // 1024}KB]"
            except OSError:
                pass
            lines.append(f"{prefix}{connector}{entry.name}{size_hint}")

    if hidden > 0:
        lines.append(f"{prefix}  ... ({hidden} more)")


# ---------------------------------------------------------------------------
# Key file reader
# ---------------------------------------------------------------------------

def read_key_files(root: Path) -> str:
    """Read priority files and return a combined block for the agent."""
    sections: list[str] = []
    total_chars = 0

    for rel_path in _PRIORITY_FILES:
        candidate = root / rel_path
        if not candidate.exists() or not candidate.is_file():
            continue

        try:
            content = candidate.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue

        if not content:
            continue

        # Truncate if too large
        if len(content) > _FILE_MAX_CHARS:
            content = content[:_FILE_MAX_CHARS] + f"\n... [truncated, {len(content)} chars total]"

        header = f"### {rel_path}"
        section = f"{header}\n\n```\n{content}\n```"
        sections.append(section)
        total_chars += len(section)

        if total_chars >= _CONTEXT_MAX_CHARS:
            sections.append("### [Context limit reached — remaining files omitted]")
            break

    return "\n\n".join(sections) if sections else "(no standard config/readme files found)"


# ---------------------------------------------------------------------------
# Entry point detection
# ---------------------------------------------------------------------------

def detect_entry_points(root: Path) -> list[str]:
    """Detect likely main entry point files."""
    candidates = [
        "main.py", "app.py", "server.py", "cli.py", "run.py",
        "index.ts", "index.js", "main.ts", "main.js", "server.ts",
        "main.go", "main.rs", "main.java",
        "src/main.py", "src/app.py", "src/index.ts", "src/index.js",
    ]
    found = []
    for rel in candidates:
        p = root / rel
        if p.exists():
            # Read a snippet
            try:
                snippet = p.read_text(encoding="utf-8", errors="replace")[:1500]
                found.append(f"**{rel}** (first 1500 chars):\n```\n{snippet}\n```")
            except OSError:
                found.append(f"**{rel}** (unreadable)")
    return found


# ---------------------------------------------------------------------------
# Dependency extractor
# ---------------------------------------------------------------------------

def extract_dependencies(root: Path) -> dict[str, list[str]]:
    """Extract runtime and dev dependencies from known manifests."""
    deps: dict[str, list[str]] = {}

    # Python
    req = root / "requirements.txt"
    if req.exists():
        try:
            lines = req.read_text(encoding="utf-8").splitlines()
            deps["python"] = [l.strip() for l in lines if l.strip() and not l.startswith("#")][:30]
        except OSError:
            pass

    pyproject = root / "pyproject.toml"
    if pyproject.exists() and "python" not in deps:
        try:
            content = pyproject.read_text(encoding="utf-8")
            matches = re.findall(r'"([a-zA-Z0-9_-]+(?:>=|==|~=)[^"]+)"', content)
            if matches:
                deps["python"] = matches[:30]
        except OSError:
            pass

    # Node
    pkg = root / "package.json"
    if pkg.exists():
        try:
            import json
            data = json.loads(pkg.read_text(encoding="utf-8"))
            runtime = list(data.get("dependencies", {}).keys())[:20]
            dev = list(data.get("devDependencies", {}).keys())[:10]
            if runtime:
                deps["node_runtime"] = runtime
            if dev:
                deps["node_dev"] = dev
        except Exception:
            pass

    return deps


# ---------------------------------------------------------------------------
# Language + framework detection
# ---------------------------------------------------------------------------

def detect_tech_stack(root: Path) -> list[str]:
    """Heuristically detect the tech stack from file extensions and config files."""
    stack: list[str] = []

    # Language by extension frequency
    ext_counts: dict[str, int] = {}
    try:
        for p in root.rglob("*"):
            if p.is_file() and p.suffix in _CODE_EXTENSIONS:
                # Skip build/vendor dirs
                parts = set(p.parts)
                if parts & _SKIP_DIRS:
                    continue
                ext_counts[p.suffix] = ext_counts.get(p.suffix, 0) + 1
    except PermissionError:
        pass

    lang_map = {
        ".py": "python", ".ts": "typescript", ".tsx": "typescript",
        ".js": "javascript", ".jsx": "javascript", ".go": "go",
        ".rs": "rust", ".java": "java", ".rb": "ruby", ".php": "php",
        ".swift": "swift", ".kt": "kotlin", ".cs": "csharp",
        ".cpp": "cpp", ".c": "c",
    }
    seen_langs: set[str] = set()
    for ext, lang in lang_map.items():
        if ext_counts.get(ext, 0) > 0 and lang not in seen_langs:
            stack.append(lang)
            seen_langs.add(lang)

    # Frameworks by known config files
    framework_signals = {
        "next.config.js": "nextjs", "next.config.ts": "nextjs",
        "nuxt.config.ts": "nuxtjs",
        "angular.json": "angular",
        "svelte.config.js": "svelte",
        "remix.config.js": "remix",
        "fastapi": "fastapi",  # detected below by import
        "django": "django",
        "flask": "flask",
        "express": "express",
        "Cargo.toml": "rust/cargo",
        "go.mod": "go/modules",
        "docker-compose.yml": "docker",
        "docker-compose.yaml": "docker",
        "Dockerfile": "docker",
        "kubernetes": "kubernetes",
        ".github/workflows": "github-actions",
    }

    for signal, framework in framework_signals.items():
        if (root / signal).exists() and framework not in stack:
            stack.append(framework)

    # Check requirements.txt / pyproject.toml for common Python frameworks
    if "python" in stack:
        req_text = ""
        for rf in ["requirements.txt", "pyproject.toml", "setup.py"]:
            try:
                req_text += (root / rf).read_text(encoding="utf-8", errors="replace").lower()
            except OSError:
                pass
        for fw in ["fastapi", "django", "flask", "starlette", "tornado", "aiohttp"]:
            if fw in req_text and fw not in stack:
                stack.append(fw)

    # Storage signals
    storage_signals = {
        "sqlite": ["*.db", "*.sqlite", "*.sqlite3"],
        "postgres": ["postgres", "postgresql", "psycopg"],
        "mysql": ["mysql", "mariadb"],
        "redis": ["redis"],
        "mongodb": ["mongo", "pymongo"],
    }
    all_text = ""
    for rf in ["requirements.txt", "package.json", "go.mod", "Cargo.toml"]:
        try:
            all_text += (root / rf).read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            pass

    for db, signals in storage_signals.items():
        if any(s in all_text for s in signals) and db not in stack:
            stack.append(db)

    return stack[:10]  # cap at 10


# ---------------------------------------------------------------------------
# GitHub URL clone helper
# ---------------------------------------------------------------------------

def clone_if_url(path_or_url: str, clone_dir: Path) -> Path:
    """If path_or_url looks like a GitHub URL, clone it to clone_dir and return the path."""
    url = path_or_url.strip()
    if url.startswith("https://github.com/") or url.startswith("git@github.com:"):
        # Extract repo name
        name = url.rstrip("/").split("/")[-1].replace(".git", "")
        dest = clone_dir / name
        if not dest.exists():
            subprocess.run(
                ["git", "clone", "--depth=1", url, str(dest)],
                check=True,
                capture_output=True,
            )
        return dest
    return Path(url).expanduser().resolve()


# ---------------------------------------------------------------------------
# Main context builder
# ---------------------------------------------------------------------------

def build_revengineer_context(path_or_url: str) -> tuple[Path, str]:
    """
    Scan the codebase and build a rich context string for the reverse-engineer agent.

    Returns:
        (resolved_path, context_string)
    """
    clone_dir = Path("/tmp/hermes_revengineer_clones")
    clone_dir.mkdir(exist_ok=True)

    root = clone_if_url(path_or_url, clone_dir)

    if not root.exists():
        raise FileNotFoundError(f"Path not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    repo_name = get_repo_name(root)
    tree = build_tree(root)
    key_files = read_key_files(root)
    entry_points = detect_entry_points(root)
    tech_stack = detect_tech_stack(root)
    deps = extract_dependencies(root)

    deps_text = ""
    for category, pkgs in deps.items():
        deps_text += f"\n- **{category}**: {', '.join(pkgs[:15])}"

    entry_text = "\n\n".join(entry_points[:3]) if entry_points else "(none detected)"

    context = f"""# Codebase Scan: {repo_name}

**Path:** {root}
**Detected stack:** {', '.join(tech_stack) if tech_stack else 'unknown'}

## Directory Structure

```
{tree}
```

## Dependencies
{deps_text if deps_text else "- (none detected)"}

## Entry Points

{entry_text}

## Key Configuration & Documentation Files

{key_files}
"""
    return root, context


def get_repo_name(root: Path) -> str:
    """Extract repo name from git config or directory name."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            return url.rstrip("/").split("/")[-1].replace(".git", "")
    except Exception:
        pass
    return root.name
