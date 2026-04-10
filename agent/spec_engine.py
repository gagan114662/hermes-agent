"""HermesSpec engine — SuperSpec implementation for Hermes.

A HermesSpec is a structured, machine-readable YAML/Markdown document that
serves as the single source of truth for any build task. Code, tests, skills,
and cron jobs are generated FROM the spec — not the other way around.

Spec format
-----------
Each spec is a Markdown file with YAML frontmatter stored in ~/.hermes/specs/.

    ---
    hermes_spec: "1.0"
    name: my-feature
    slug: my-feature
    status: draft          # draft | approved | executing | complete
    created: 2026-01-01
    owner: gagan114662
    tech_stack: [python, sqlite]
    tags: [crm, sales]
    ---

    ## Overview
    ...

    ## Architecture
    ...

    ## Data Models
    ...

    ## Workflows
    ...

    ## Security
    ...

    ## Tasks

    ```yaml
    tasks:
      - id: t1
        title: "Create the main tool file"
        agent_type: general
        goal: "Create tools/my_tool.py implementing ..."
        files: ["tools/my_tool.py"]
        depends_on: []
        status: pending
    ```

Commands
--------
/specnew <description>   — generate a new spec via spec-writer agent
/speclist                — list all specs with status
/specexec <name>         — execute the pending tasks in a spec
/speccheck <name>        — verify what's been built against the spec
"""

from __future__ import annotations

import re
import textwrap
from datetime import date
from pathlib import Path
from typing import Optional

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

SPEC_VERSION = "1.0"
SPECS_SUBDIR = "specs"


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------

def get_specs_dir() -> Path:
    """Return ~/.hermes/specs/ (may not exist yet)."""
    from hermes_constants import get_hermes_home
    return get_hermes_home() / SPECS_SUBDIR


def ensure_specs_dir() -> Path:
    """Create ~/.hermes/specs/ if it doesn't exist. Returns the path."""
    d = get_specs_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Spec data class
# ---------------------------------------------------------------------------

class HermesSpec:
    """Parsed representation of a HermesSpec file."""

    def __init__(
        self,
        path: Path,
        frontmatter: dict,
        sections: dict[str, str],
        raw: str,
    ) -> None:
        self.path = path
        self.frontmatter = frontmatter
        self.sections = sections  # section_name.lower() → content
        self.raw = raw

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self.frontmatter.get("name", self.path.stem)

    @property
    def slug(self) -> str:
        return self.frontmatter.get("slug", self.name)

    @property
    def status(self) -> str:
        return self.frontmatter.get("status", "draft")

    @property
    def tech_stack(self) -> list[str]:
        return self.frontmatter.get("tech_stack", [])

    @property
    def tags(self) -> list[str]:
        return self.frontmatter.get("tags", [])

    @property
    def overview(self) -> str:
        return self.sections.get("overview", "")

    @property
    def tasks(self) -> list[dict]:
        """Extract structured tasks from the Tasks section."""
        return extract_tasks(self.raw)

    @property
    def pending_tasks(self) -> list[dict]:
        return [t for t in self.tasks if t.get("status", "pending") == "pending"]

    @property
    def completed_tasks(self) -> list[dict]:
        return [t for t in self.tasks if t.get("status") == "complete"]

    def summary(self) -> str:
        total = len(self.tasks)
        done = len(self.completed_tasks)
        bar = f"{done}/{total} tasks done" if total else "no tasks"
        stack = ", ".join(self.tech_stack) if self.tech_stack else "unspecified"
        return (
            f"[bold]{self.name}[/bold]  [{self.status}]  {bar}\n"
            f"  stack: {stack}  |  {self.path.name}"
        )

    def __repr__(self) -> str:  # pragma: no cover
        return f"HermesSpec(name={self.name!r}, status={self.status!r})"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\n(.*?\n)---\n", re.DOTALL)
_SECTION_RE = re.compile(r"^##\s+(\w[\w\s/-]*?)\s*$", re.MULTILINE)


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body_after_frontmatter)."""
    m = _FRONTMATTER_RE.match(content)
    if not m:
        return {}, content

    fm_raw = m.group(1)
    body = content[m.end():]

    if _YAML_AVAILABLE:
        try:
            data = yaml.safe_load(fm_raw) or {}
        except Exception:
            data = {}
    else:
        # Minimal key: value parser fallback
        data = {}
        for line in fm_raw.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                v = v.strip().strip('"').strip("'")
                if v.startswith("[") and v.endswith("]"):
                    v = [x.strip().strip('"').strip("'") for x in v[1:-1].split(",") if x.strip()]
                data[k.strip()] = v

    return data, body


def _parse_sections(body: str) -> dict[str, str]:
    """Split the body into a dict of section_name.lower() → content."""
    positions = [(m.start(), m.group(1).strip()) for m in _SECTION_RE.finditer(body)]
    if not positions:
        return {}

    sections: dict[str, str] = {}
    for i, (start, name) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(body)
        # Skip the header line itself
        section_body = body[start:end]
        section_body = re.sub(r"^##\s+.*\n", "", section_body, count=1)
        sections[name.lower()] = section_body.strip()

    return sections


def parse_spec(content: str, path: Optional[Path] = None) -> HermesSpec:
    """Parse a HermesSpec from raw Markdown+YAML content."""
    frontmatter, body = _parse_frontmatter(content)
    sections = _parse_sections(body)
    return HermesSpec(
        path=path or Path("unknown.md"),
        frontmatter=frontmatter,
        sections=sections,
        raw=content,
    )


# ---------------------------------------------------------------------------
# Task extraction
# ---------------------------------------------------------------------------

_TASKS_BLOCK_RE = re.compile(
    r"```ya?ml\s*\ntasks:\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)


def extract_tasks(content: str) -> list[dict]:
    """Extract the structured tasks list from a spec's Tasks section.

    Looks for a ```yaml tasks: ... ``` block anywhere in the spec.
    Returns a list of task dicts, each with at minimum: id, title, goal, status.
    """
    m = _TASKS_BLOCK_RE.search(content)
    if not m:
        return []

    tasks_yaml = "tasks:\n" + m.group(1)

    if _YAML_AVAILABLE:
        try:
            data = yaml.safe_load(tasks_yaml) or {}
            return data.get("tasks", [])
        except Exception:
            return []

    # Minimal fallback — just extract `- id: ...` items
    tasks = []
    current: dict = {}
    for line in tasks_yaml.splitlines():
        stripped = line.strip()
        if stripped.startswith("- id:"):
            if current:
                tasks.append(current)
            current = {"id": stripped[5:].strip(), "status": "pending"}
        elif ":" in stripped and current:
            k, _, v = stripped.partition(":")
            current[k.strip()] = v.strip().strip('"').strip("'")
    if current:
        tasks.append(current)
    return tasks


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def find_spec(name: str) -> Optional[Path]:
    """Find a spec file by name or slug. Returns Path or None."""
    specs_dir = get_specs_dir()
    if not specs_dir.exists():
        return None

    # Exact filename match
    exact = specs_dir / f"{name}.md"
    if exact.exists():
        return exact

    # Slug match (normalize dashes/underscores)
    slug = name.lower().replace(" ", "-").replace("_", "-")
    for p in specs_dir.glob("*.md"):
        if p.stem.lower().replace("_", "-") == slug:
            return p

    return None


def load_spec(name_or_path: str | Path) -> Optional[HermesSpec]:
    """Load and parse a spec by name or file path."""
    if isinstance(name_or_path, Path):
        path = name_or_path
    else:
        path = find_spec(str(name_or_path))
        if not path:
            return None

    try:
        content = path.read_text(encoding="utf-8")
        return parse_spec(content, path=path)
    except Exception:
        return None


def list_specs() -> list[HermesSpec]:
    """Return all parsed specs in ~/.hermes/specs/, sorted by name."""
    specs_dir = get_specs_dir()
    if not specs_dir.exists():
        return []

    results = []
    for p in sorted(specs_dir.glob("*.md")):
        spec = load_spec(p)
        if spec:
            results.append(spec)
    return results


def save_spec(content: str, name: str) -> Path:
    """Write spec content to ~/.hermes/specs/<name>.md. Returns the path."""
    specs_dir = ensure_specs_dir()
    slug = name.lower().replace(" ", "-").replace("_", "-")
    path = specs_dir / f"{slug}.md"
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Spec template generator (used by spec-writer agent as output scaffold)
# ---------------------------------------------------------------------------

SPEC_TEMPLATE = textwrap.dedent("""\
    ---
    hermes_spec: "1.0"
    name: {name}
    slug: {slug}
    status: draft
    created: {today}
    owner: ""
    tech_stack: []
    tags: []
    ---

    ## Overview

    ### What
    _What exactly are we building?_

    ### Why
    _What problem does this solve? Why now?_

    ### Success Metrics
    - _How do we know this is done and working?_

    ## Architecture

    ### Components
    _List the key files/modules and what each does._

    ### Data Flow
    _How does data move through the system?_

    ## Data Models

    _Key entities and their schemas._

    ## Workflows

    _Step-by-step descriptions of each major user journey._

    ## Security

    _Threat model, auth, permissions, what stays local._

    ## Tasks

    ```yaml
    tasks:
      - id: t1
        title: "First implementation task"
        agent_type: general
        goal: "Detailed goal for the agent..."
        files: []
        depends_on: []
        status: pending
    ```
""")


def make_blank_spec(name: str) -> str:
    """Return a blank spec template for the given name."""
    slug = name.lower().replace(" ", "-").replace("_", "-")
    return SPEC_TEMPLATE.format(
        name=name,
        slug=slug,
        today=str(date.today()),
    )


# ---------------------------------------------------------------------------
# Update task status in a spec file
# ---------------------------------------------------------------------------

def mark_task_complete(spec_path: Path, task_id: str) -> bool:
    """Update a task's status to 'complete' in the spec file. Returns True on success."""
    try:
        content = spec_path.read_text(encoding="utf-8")
        # Find the task block and update its status field.
        # \b prevents t1 from matching t10/t11 etc.
        # (?:(?!- id:).)* prevents the match from crossing into the next task block.
        pattern = re.compile(
            r"(- id:\s*" + re.escape(task_id) + r"\b(?:(?!- id:).)*?status:\s*)pending",
            re.DOTALL,
        )
        new_content, count = pattern.subn(r"\1complete", content, count=1)
        if count:
            spec_path.write_text(new_content, encoding="utf-8")
            return True
        return False
    except Exception:
        return False


def update_spec_status(spec_path: Path, status: str) -> bool:
    """Update the top-level status field in the spec frontmatter."""
    try:
        content = spec_path.read_text(encoding="utf-8")
        new_content = re.sub(
            r"(^status:\s*)[\w]+",
            f"\\g<1>{status}",
            content,
            count=1,
            flags=re.MULTILINE,
        )
        spec_path.write_text(new_content, encoding="utf-8")
        return True
    except Exception:
        return False
