"""Employee — persistent goal-driven agent persona.

An Employee encapsulates a named role + goal and delegates execution to
SessionOrchestrator.  Employee configs are stored as YAML in
~/.hermes/employees/{name}.yaml so they survive across CLI sessions.

Usage
-----
    emp = Employee.load("ada", employees_dir=Path("~/.hermes/employees"))
    emp.start_shift(project_dir=Path("/path/to/project"))

Or create a new one:
    emp = Employee(name="ada", role="backend engineer", goal="Build auth API")
    emp.save()
    emp.start_shift(project_dir=Path("."))
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from harness.config import HarnessConfig

logger = logging.getLogger(__name__)

_DEFAULT_EMPLOYEES_DIR = Path.home() / ".hermes" / "employees"


@dataclass
class Employee:
    """A persistent, goal-driven agent persona.

    Attributes
    ----------
    name          : Unique slug used as the config filename key.
    role          : Job title / function (e.g. "backend engineer").
    goal          : One-paragraph description of what this employee works toward.
    kpis          : Measurable success criteria (bullet strings).
    schedule      : Cron expression for proactive work cycles (optional).
    memory_scope  : Isolated memory namespace key for this employee.
    status        : Current state — idle | working | blocked | completed.
    employees_dir : Where YAML files are stored; defaults to ~/.hermes/employees.
    """

    name: str
    role: str
    goal: str
    kpis: list[str] = field(default_factory=list)
    schedule: Optional[str] = None
    memory_scope: Optional[str] = None
    status: str = "idle"
    employees_dir: Optional[Path] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.employees_dir is None:
            self.employees_dir = _DEFAULT_EMPLOYEES_DIR
        self.employees_dir = Path(self.employees_dir)
        if self.memory_scope is None:
            self.memory_scope = self.name

    # ── Persistence ───────────────────────────────────────────────────

    @property
    def _config_path(self) -> Path:
        return self.employees_dir / f"{self.name}.yaml"

    def save(self) -> None:
        """Write employee config to YAML file."""
        import yaml  # lazy import

        self.employees_dir.mkdir(parents=True, exist_ok=True)
        # Build serializable dict, excluding employees_dir (it's runtime context)
        data = {}
        for k, v in asdict(self).items():
            if k == "employees_dir":
                continue
            if v is None:
                continue
            data[k] = v
        self._config_path.write_text(yaml.dump(data, default_flow_style=False))
        logger.debug("Saved employee config: %s", self._config_path)

    @classmethod
    def load(cls, name: str, employees_dir: Optional[Path] = None) -> "Employee":
        """Load an employee config from YAML.  Raises FileNotFoundError if missing."""
        import yaml

        dir_ = Path(employees_dir) if employees_dir else _DEFAULT_EMPLOYEES_DIR
        path = dir_ / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"No employee config found: {path}")
        data = yaml.safe_load(path.read_text()) or {}
        data["employees_dir"] = dir_
        # Only pass known fields to avoid TypeError on extra YAML keys
        known = {k for k in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    @classmethod
    def list_all(cls, employees_dir: Optional[Path] = None) -> list["Employee"]:
        """Return all employees found in the employees directory."""
        dir_ = Path(employees_dir) if employees_dir else _DEFAULT_EMPLOYEES_DIR
        if not dir_.exists():
            return []
        result = []
        for yaml_file in sorted(dir_.glob("*.yaml")):
            try:
                result.append(cls.load(yaml_file.stem, employees_dir=dir_))
            except Exception as exc:
                logger.warning("Could not load employee %s: %s", yaml_file.stem, exc)
        return result

    # ── Harness integration ───────────────────────────────────────────

    def to_harness_config(self, project_dir: Path, **overrides) -> HarnessConfig:
        """Build a HarnessConfig from this employee's goal and KPIs."""
        task_spec = self.goal
        if self.kpis:
            kpi_block = "\n".join(f"- {k}" for k in self.kpis)
            task_spec = f"{self.goal}\n\nSuccess criteria:\n{kpi_block}"

        return HarnessConfig(
            project_dir=Path(project_dir),
            task_spec=task_spec,
            **overrides,
        )

    def start_shift(self, project_dir: Path, **harness_overrides) -> dict:
        """Begin a harness-orchestrated work session toward this employee's goal.

        Parameters
        ----------
        project_dir      : Working directory for the agent.
        harness_overrides: Extra kwargs forwarded to HarnessConfig.

        Returns
        -------
        The SessionOrchestrator.run_harness() result dict.
        """
        from harness.session_orchestrator import SessionOrchestrator  # lazy import

        self.status = "working"
        self.save()

        cfg = self.to_harness_config(project_dir, **harness_overrides)
        orch = SessionOrchestrator(cfg)

        try:
            result = orch.run_harness()
            self.status = "completed" if result["status"] == "completed" else "idle"
        except Exception as exc:
            self.status = "blocked"
            logger.exception("Employee %s shift failed: %s", self.name, exc)
            result = {
                "status": "error",
                "message": str(exc),
                "sessions_run": 0,
                "total_cost_usd": 0.0,
            }
        finally:
            self.save()

        return result

    def decompose_goal(self, project_dir: Path) -> list[dict]:
        """Use task_graph to break the employee's goal into feature dicts.

        Returns a list of feature dicts that can be written to features.json.
        Requires an AI API key to be set in environment.
        """
        from run_agent import AIAgent
        from agent.task_graph import _decompose_goal

        agent = AIAgent(model="anthropic/claude-haiku-4-5")
        subtasks, _ = _decompose_goal(
            goal=self.goal,
            parent_agent=agent,
            max_subtasks=10,
        )

        return [
            {
                "id": f"feat-{i+1:03d}",
                "description": subtask,
                "file_path": "",
                "test_cases": [],
                "dependencies": [],
                "passes": False,
            }
            for i, subtask in enumerate(subtasks)
        ]
