"""Team Factory — Dynamic LLM-powered team generation from business profiles.

This module replaces static templates with an LLM-powered system that:
1. Takes a business profile from website_analyzer
2. Calls the z.ai LLM (glm-4.5-flash, OpenAI-compatible) to design the perfect team
3. Generates roles, goals, KPIs, schedules, and tool assignments dynamically
4. Falls back to lightweight rule-based generation if LLM is unavailable

This means Hermes works for ANY business, not just hardcoded industries.

Usage
-----
    from harness.team_factory import create_team_from_profile, provision_team

    # Create employees from profile (now uses LLM)
    employees = await create_team_from_profile(Path("~/.hermes/business_profile.json"))

    # Full provisioning (includes Henry PM)
    summary = await provision_team(
        profile_path=Path("~/.hermes/business_profile.json"),
        project_dir=Path("./my_project")
    )
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

from harness.employee import Employee

logger = logging.getLogger(__name__)


async def generate_team_with_llm(business_profile: dict) -> list[dict]:
    """Generate team specs using z.ai LLM.

    Calls glm-4.5-flash (OpenAI-compatible) with the business profile and
    available tools list. Returns a JSON array of employee specs that can
    be converted to Employee instances.

    Parameters
    ----------
    business_profile : dict
        Business profile from website_analyzer containing:
        - business_name, industry, description, services, pain_points, etc.

    Returns
    -------
    list[dict]
        List of employee specs: [{name, role, goal, kpis, schedule, tools}]
        Each employee is designed for THIS business, not generic.

    Raises
    ------
    Exception
        If LLM call fails. Caller should fall back to _fallback_generate_team.
    """
    try:
        from openai import AsyncOpenAI
    except ImportError:
        logger.warning("openai package not available. Falling back to rule-based generation.")
        return _fallback_generate_team(business_profile)

    # Get LLM config from env
    base_url = os.getenv("GLM_BASE_URL", "https://api.z.ai/api/paas/v4")
    api_key = os.getenv("GLM_API_KEY")

    if not api_key:
        logger.warning("GLM_API_KEY not set. Falling back to rule-based generation.")
        return _fallback_generate_team(business_profile)

    try:
        # Initialize OpenAI-compatible client for z.ai
        client = AsyncOpenAI(base_url=base_url, api_key=api_key)

        # Get list of available tools
        available_tools = _get_available_tools()

        # Build a smart prompt
        prompt = _build_llm_prompt(business_profile, available_tools)

        # Call the LLM
        response = await client.chat.completions.create(
            model="glm-4.5-flash",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert workforce architect designing AI agents. "
                        "Each employee is an autonomous agent that will work independently. "
                        "Return ONLY valid JSON, no markdown or extra text."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=2000,
        )

        # Parse the response
        response_text = response.choices[0].message.content
        logger.info(f"LLM response: {response_text[:200]}...")

        # Extract JSON from response
        json_match = re.search(r"\[\s*\{.*\}\s*\]", response_text, re.DOTALL)
        if not json_match:
            logger.warning("Could not find JSON in LLM response. Using fallback.")
            return _fallback_generate_team(business_profile)

        employee_specs = json.loads(json_match.group(0))
        logger.info(f"Generated {len(employee_specs)} employee specs via LLM")

        return employee_specs

    except Exception as exc:
        logger.warning(f"LLM generation failed: {exc}. Falling back to rule-based generation.")
        return _fallback_generate_team(business_profile)


def _build_llm_prompt(business_profile: dict, available_tools: list[str]) -> str:
    """Build a smart prompt for the LLM to design the team."""
    business_name = business_profile.get("business_name", "the business")
    industry = business_profile.get("industry", "unknown")
    description = business_profile.get("description", "")
    services = business_profile.get("services", [])
    pain_points = business_profile.get("pain_points", [])
    team_size = business_profile.get("team_size_estimate", "small")

    services_str = ", ".join(services[:5]) if services else "N/A"
    pain_points_str = ", ".join(pain_points[:4]) if pain_points else "N/A"
    tools_str = ", ".join(available_tools[:30])  # List first 30 tools to keep prompt concise

    prompt = f"""Design an AI workforce for this business:

BUSINESS PROFILE:
- Name: {business_name}
- Industry: {industry}
- Description: {description}
- Services/Products: {services_str}
- Key Pain Points: {pain_points_str}
- Estimated Team Size: {team_size}

AVAILABLE TOOLS (pick 2-4 per employee):
{tools_str}

YOUR TASK:
Create 3-6 specialized AI employees for this business. For each, design:
1. **name** (memorable slug, not generic): e.g. "alex_outreach", "jordan_support"
2. **role** (job title): e.g. "Customer Support Specialist"
3. **goal** (specific to THIS business): What they work toward daily
4. **kpis** (3-4 measurable success criteria)
5. **schedule** (cron expression): When they work (e.g. "0 9 * * *" for 9am daily)
6. **tools** (2-4 tool names from AVAILABLE TOOLS): What they use

Make the roles complementary and cover the pain points. Each employee should be autonomous
and have a clear, specific goal tied to THIS business.

RETURN ONLY THIS JSON FORMAT (no markdown, no extra text):
[
  {{"name": "...", "role": "...", "goal": "...", "kpis": [...], "schedule": "...", "tools": [...]}},
  ...
]
"""
    return prompt


def _get_available_tools() -> list[str]:
    """Read tool names from the tools/ directory."""
    tools_dir = Path(__file__).parent.parent / "tools"
    tool_names = []

    if tools_dir.exists():
        for py_file in sorted(tools_dir.glob("*.py")):
            # Skip internal files
            if py_file.name.startswith("_"):
                continue
            # Convert booking_tool.py -> booking_tool
            tool_name = py_file.stem
            tool_names.append(tool_name)

    # Hardcoded list if directory doesn't exist
    if not tool_names:
        tool_names = [
            "booking_tool",
            "browser_tool",
            "crm_tool",
            "cron_tool",
            "database_tool",
            "email_delivery",
            "email_marketing_tool",
            "google_workspace_tool",
            "image_generation_tool",
            "invoicing_tool",
            "memory_tool",
            "outreach_tool",
            "prospect_tool",
            "send_message_tool",
            "social_media_tool",
            "sms_android_tool",
            "vapi_tool",
            "web_tools",
            "whatsapp_evolution_tool",
            "wiki_tool",
        ]

    return tool_names


def _fallback_generate_team(business_profile: dict) -> list[dict]:
    """Lightweight rule-based team generation when LLM is unavailable.

    Creates 3-4 generic employees based on business pain points.
    This is NOT the same as the old static templates — much simpler fallback.
    """
    business_name = business_profile.get("business_name", "the business")
    industry = business_profile.get("industry", "general")
    pain_points = business_profile.get("pain_points", [])

    employees = []

    # Determine roles based on pain points (very basic heuristic)
    role_keywords = {
        "support": ("Customer Support Agent", "Respond to customer inquiries and resolve issues", "support_agent"),
        "marketing": ("Marketing Specialist", "Drive customer engagement and growth", "marketing_agent"),
        "sales": ("Sales Agent", "Qualify leads and close deals", "sales_agent"),
        "operations": ("Operations Manager", "Optimize business processes", "ops_agent"),
    }

    # Pick 2-3 roles based on pain points
    selected_roles = ["support", "marketing"]  # Default
    if any(word in " ".join(pain_points).lower() for word in ["lead", "sales"]):
        selected_roles.append("sales")
    if any(word in " ".join(pain_points).lower() for word in ["schedule", "booking", "appointment"]):
        selected_roles = ["support", "sales", "operations"]

    for role_key in selected_roles[:3]:
        if role_key not in role_keywords:
            continue

        role_title, goal_template, name_slug = role_keywords[role_key]
        goal = f"{goal_template} for {business_name}."

        employees.append({
            "name": f"{name_slug}_{business_name[:5].lower()}",
            "role": role_title,
            "goal": goal,
            "kpis": ["Task completion rate", "Customer satisfaction", "Response time"],
            "schedule": "0 9 * * *",  # 9 AM daily
            "tools": ["browser_tool", "send_message_tool"],  # Generic tools
        })

    logger.info(f"Fallback generated {len(employees)} employees for {business_name}")
    return employees


async def create_team_from_profile(
    profile_path: Path,
    employees_dir: Optional[Path] = None,
) -> list[Employee]:
    """Create Employee instances from a business profile JSON using LLM.

    Reads the business_profile.json file, calls generate_team_with_llm to
    design the team, and creates Employee instances from the LLM output.

    Parameters
    ----------
    profile_path : Path
        Path to business_profile.json (typically ~/.hermes/business_profile.json).
    employees_dir : Optional[Path]
        Directory where Employee YAML configs are saved.
        Defaults to ~/.hermes/employees.

    Returns
    -------
    list[Employee]
        List of created and saved Employee instances.

    Raises
    ------
    FileNotFoundError
        If profile_path does not exist.
    ValueError
        If profile JSON is malformed.
    """
    profile_path = Path(profile_path).expanduser()

    if not profile_path.exists():
        raise FileNotFoundError(f"Business profile not found: {profile_path}")

    try:
        profile_data = json.loads(profile_path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in business profile: {exc}") from exc

    business_name = profile_data.get("business_name", "Unknown Business")
    logger.info(f"Creating team for {business_name} using LLM...")

    # Generate team specs using LLM
    employee_specs = await generate_team_with_llm(profile_data)

    if not employee_specs:
        logger.warning(f"No employee specs generated for {business_name}")
        return []

    created_employees = []

    for spec in employee_specs:
        try:
            # Create Employee from spec
            employee = Employee(
                name=spec.get("name", f"agent_{len(created_employees)}"),
                role=spec.get("role", "AI Agent"),
                goal=spec.get("goal", f"Support {business_name}"),
                kpis=spec.get("kpis", []),
                schedule=spec.get("schedule"),
                memory_scope=spec.get("name"),
                employees_dir=employees_dir,
            )

            # Save to YAML
            employee.save()
            created_employees.append(employee)
            logger.info(f"Created employee: {employee.name} ({employee.role})")

        except Exception as exc:
            logger.warning(f"Could not create employee from spec {spec}: {exc}")
            continue

    return created_employees


async def provision_team(
    profile_path: Path,
    project_dir: Path,
    employees_dir: Optional[Path] = None,
    user_contact: Optional[str] = None,
    auto_start: bool = False,
) -> dict:
    """Full team provisioning: create employees from profile + add Henry PM.

    Creates a complete team for a business project using LLM-powered design.
    Includes all generated employees plus the Henry project manager.

    Parameters
    ----------
    profile_path : Path
        Path to business_profile.json.
    project_dir : Path
        Project working directory.
    employees_dir : Optional[Path]
        Directory for Employee YAML configs.
    user_contact : Optional[str]
        Owner's contact info (phone, email, or handle) for Henry's communications.
        Defaults to "owner" if not provided.
    auto_start : bool
        If True, register employee schedules in cron after creation.
        Defaults to False.

    Returns
    -------
    dict
        Summary dict with keys:
        - business_name: str
        - employee_count: int
        - employees: list of {name, role, status}
        - henry_included: bool
        - schedules_registered: bool (only if auto_start=True)
        - summary: human-readable summary
    """
    profile_path = Path(profile_path).expanduser()
    project_dir = Path(project_dir).expanduser()

    profile_data = json.loads(profile_path.read_text())
    business_name = profile_data.get("business_name", "Unknown Business")

    # Create employees from profile (now using LLM)
    employees = await create_team_from_profile(profile_path, employees_dir=employees_dir)

    # Add Henry PM (lazy import to avoid circular dependencies)
    try:
        from harness.henry import create_henry  # lazy import

        contact = user_contact or "owner"
        henry = create_henry(business_name=business_name, user_contact=contact)
        employees.append(henry)
        henry_included = True
        logger.info(f"Henry PM provisioned for {business_name} with contact: {contact}")
    except (ImportError, Exception) as exc:
        logger.warning(f"Could not provision Henry PM: {exc}")
        henry_included = False

    # Build summary
    employee_summaries = [
        {"name": emp.name, "role": emp.role, "status": emp.status} for emp in employees
    ]

    summary_text = (
        f"Provisioned {len(employees)} employees for {business_name}. "
        f"Team includes: {', '.join(emp['role'] for emp in employee_summaries)}."
    )

    result = {
        "business_name": business_name,
        "employee_count": len(employees),
        "employees": employee_summaries,
        "henry_included": henry_included,
        "summary": summary_text,
    }

    # Optionally register cron schedules for all employees
    if auto_start:
        try:
            from harness.team_scheduler import register_team_schedules

            schedule_summary = register_team_schedules(
                employees_dir=employees_dir or Path.home() / ".hermes" / "employees",
                project_dir=project_dir,
            )
            result["schedules_registered"] = True
            result["schedule_summary"] = schedule_summary
            logger.info(f"Team schedules registered: {schedule_summary}")
        except Exception as exc:
            logger.warning(f"Could not register team schedules: {exc}")
            result["schedules_registered"] = False

    return result
