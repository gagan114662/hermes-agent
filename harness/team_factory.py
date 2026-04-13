"""Team Factory — Creates Employee instances from business profiles.

This module reads a business_profile.json and automatically instantiates the
right Employee instances for that business. It bridges website analysis and
the employee system.

Usage
-----
    from harness.team_factory import create_team_from_profile, provision_team

    # Create employees from profile
    employees = create_team_from_profile(Path("~/.hermes/business_profile.json"))

    # Full provisioning (includes Henry PM)
    summary = provision_team(
        profile_path=Path("~/.hermes/business_profile.json"),
        project_dir=Path("./my_project")
    )
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from harness.employee import Employee

logger = logging.getLogger(__name__)


# ── Employee Templates ─────────────────────────────────────────────────────
# Maps role slugs to full Employee configuration (with {business_name} placeholders)

EMPLOYEE_TEMPLATES = {
    "reservations_manager": {
        "role": "Reservations Manager",
        "goal": "Manage and optimize reservation bookings for {business_name}. Handle customer inquiries, confirm bookings, update availability calendars, and maintain organized reservation records.",
        "kpis": [
            "Confirmation rate of booking requests",
            "Average time to respond to inquiries",
            "Reservation accuracy and no-show rate",
            "Customer satisfaction score",
        ],
        "schedule": "0 9,14 * * *",  # 9 AM and 2 PM daily
    },
    "review_responder": {
        "role": "Review Response Manager",
        "goal": "Monitor and respond to customer reviews across platforms for {business_name}. Craft thoughtful replies to feedback, address concerns, and build positive reputation.",
        "kpis": [
            "Response rate to new reviews",
            "Average response time",
            "Sentiment improvement after responses",
            "Review platform engagement rate",
        ],
        "schedule": "0 */2 * * *",  # Every 2 hours
    },
    "social_media_manager": {
        "role": "Social Media Manager",
        "goal": "Develop and execute social media content strategy for {business_name}. Create engaging posts, manage community interactions, track metrics, and grow followers.",
        "kpis": [
            "Monthly post engagement rate",
            "Follower growth percentage",
            "Click-through rate on promotional posts",
            "Community sentiment and comment quality",
        ],
        "schedule": "0 9 * * *",  # 9 AM daily
    },
    "customer_support": {
        "role": "Customer Support Specialist",
        "goal": "Provide exceptional customer support for {business_name}. Respond to inquiries, resolve issues, handle complaints, and maintain customer satisfaction.",
        "kpis": [
            "First response time",
            "Issue resolution rate",
            "Customer satisfaction (CSAT) score",
            "Ticket volume handled per day",
        ],
        "schedule": "0 */4 * * *",  # Every 4 hours
    },
    "docs_writer": {
        "role": "Documentation Writer",
        "goal": "Create and maintain comprehensive documentation for {business_name}. Write guides, FAQs, knowledge base articles, and process documentation.",
        "kpis": [
            "Documentation completion percentage",
            "Avg time to document new processes",
            "Article clarity and helpfulness rating",
            "Documentation view/usage metrics",
        ],
        "schedule": "0 10 * * 1",  # 10 AM every Monday
    },
    "lead_qualifier": {
        "role": "Lead Qualification Specialist",
        "goal": "Identify and qualify sales leads for {business_name}. Analyze inbound prospects, assess fit, prioritize high-value opportunities, and route to sales.",
        "kpis": [
            "Leads qualified per week",
            "Qualification accuracy rate",
            "Average lead response time",
            "Sales conversion rate from qualified leads",
        ],
        "schedule": "0 8,12,16 * * *",  # 8 AM, 12 PM, 4 PM daily
    },
    "email_marketer": {
        "role": "Email Marketing Manager",
        "goal": "Execute email marketing campaigns for {business_name}. Design campaigns, manage lists, track opens/clicks, and optimize conversion rates.",
        "kpis": [
            "Email open rate",
            "Click-through rate",
            "Conversion rate per campaign",
            "List growth rate",
        ],
        "schedule": "0 11 * * *",  # 11 AM daily
    },
    "content_strategist": {
        "role": "Content Strategy Lead",
        "goal": "Develop comprehensive content strategy for {business_name}. Plan editorial calendars, research topics, optimize for SEO, and manage content publishing.",
        "kpis": [
            "Articles published per month",
            "Avg page views per article",
            "Organic search traffic growth",
            "Time on page / engagement metrics",
        ],
        "schedule": "0 10 * * 2",  # 10 AM every Tuesday
    },
    "appointment_scheduler": {
        "role": "Appointment Scheduler",
        "goal": "Manage appointment scheduling and calendar optimization for {business_name}. Book appointments, manage cancellations, send reminders, and optimize scheduling.",
        "kpis": [
            "Appointments booked per day",
            "Cancellation rate",
            "No-show rate",
            "Average booking lead time",
        ],
        "schedule": "0 */3 * * *",  # Every 3 hours
    },
    "seo_specialist": {
        "role": "SEO Specialist",
        "goal": "Improve search engine visibility for {business_name}. Conduct keyword research, optimize content, build backlinks, and track rankings.",
        "kpis": [
            "Keyword ranking improvements",
            "Organic traffic growth percentage",
            "Domain authority increase",
            "Click-through rate from search results",
        ],
        "schedule": "0 9 * * 1",  # 9 AM every Monday
    },
    "inventory_manager": {
        "role": "Inventory Manager",
        "goal": "Optimize inventory levels and stock management for {business_name}. Track stock, forecast demand, manage reorders, and prevent stockouts.",
        "kpis": [
            "Inventory turnover rate",
            "Stockout incidents per month",
            "Inventory accuracy percentage",
            "Days inventory outstanding",
        ],
        "schedule": "0 8 * * *",  # 8 AM daily
    },
    "quality_assurance": {
        "role": "Quality Assurance Manager",
        "goal": "Ensure product/service quality standards for {business_name}. Conduct audits, document issues, implement improvements, and track quality metrics.",
        "kpis": [
            "Defect identification rate",
            "Issue resolution time",
            "Quality score improvement",
            "Customer quality complaints per month",
        ],
        "schedule": "0 10 * * 3",  # 10 AM every Wednesday
    },
    "event_coordinator": {
        "role": "Event Coordinator",
        "goal": "Plan and execute events for {business_name}. Manage logistics, coordinate vendors, promote events, and ensure successful execution.",
        "kpis": [
            "Events planned per quarter",
            "Attendee count per event",
            "Event satisfaction rating",
            "Lead generation per event",
        ],
        "schedule": "0 9 * * 0",  # 9 AM every Sunday
    },
    "copywriter": {
        "role": "Copywriter",
        "goal": "Create compelling marketing copy for {business_name}. Write website content, ad copy, email subject lines, and promotional materials.",
        "kpis": [
            "Copy completion rate",
            "Click-through rate on copy",
            "Conversion rate improvement",
            "A/B test win rate",
        ],
        "schedule": "0 11 * * 2",  # 11 AM every Tuesday
    },
    "partnership_developer": {
        "role": "Partnership Developer",
        "goal": "Identify and develop strategic partnerships for {business_name}. Research potential partners, negotiate terms, manage relationships, and track outcomes.",
        "kpis": [
            "New partnerships established per quarter",
            "Partnership revenue contribution",
            "Partner satisfaction score",
            "Co-marketing campaign reach",
        ],
        "schedule": "0 10 * * 4",  # 10 AM every Thursday
    },
}


def create_team_from_profile(
    profile_path: Path,
    employees_dir: Optional[Path] = None,
) -> list[Employee]:
    """Create Employee instances from a business profile JSON.

    Reads the business_profile.json file, extracts the recommended_employees list,
    looks up each role in EMPLOYEE_TEMPLATES, and creates Employee instances with
    the business name substituted into the goal template.

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
        If profile JSON is malformed or missing required fields.
    """
    profile_path = Path(profile_path).expanduser()

    if not profile_path.exists():
        raise FileNotFoundError(f"Business profile not found: {profile_path}")

    try:
        profile_data = json.loads(profile_path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in business profile: {exc}") from exc

    business_name = profile_data.get("business_name", "Unknown Business")
    recommended_roles = profile_data.get("suggested_employees", [])

    if not recommended_roles:
        logger.warning(
            "No recommended employees found in profile for %s", business_name
        )
        return []

    created_employees = []

    for role_entry in recommended_roles:
        # role_entry can be a dict with "role" key or just a string
        if isinstance(role_entry, dict):
            role_slug = role_entry.get("role", "").lower().replace(" ", "_")
        else:
            role_slug = str(role_entry).lower().replace(" ", "_")

        if role_slug not in EMPLOYEE_TEMPLATES:
            logger.warning("No template found for role: %s", role_slug)
            continue

        template = EMPLOYEE_TEMPLATES[role_slug]

        # Substitute business_name into the goal template
        goal = template["goal"].format(business_name=business_name)

        # Create unique employee name from role slug and business
        employee_name = _create_employee_name(role_slug, business_name)

        # Create the Employee instance
        employee = Employee(
            name=employee_name,
            role=template["role"],
            goal=goal,
            kpis=template["kpis"],
            schedule=template.get("schedule"),
            memory_scope=employee_name,
            employees_dir=employees_dir,
        )

        # Save to YAML
        employee.save()
        created_employees.append(employee)
        logger.info(
            "Created employee: %s (%s) for %s",
            employee_name,
            template["role"],
            business_name,
        )

    return created_employees


def provision_team(
    profile_path: Path,
    project_dir: Path,
    employees_dir: Optional[Path] = None,
) -> dict:
    """Full team provisioning: create employees from profile + add Henry PM.

    Creates a complete team for a business project. Includes all recommended
    employees from the business profile plus the Henry project manager.

    Parameters
    ----------
    profile_path : Path
        Path to business_profile.json.
    project_dir : Path
        Project working directory.
    employees_dir : Optional[Path]
        Directory for Employee YAML configs.

    Returns
    -------
    dict
        Summary dict with keys:
        - business_name: str
        - employee_count: int
        - employees: list of {name, role, status}
        - henry_included: bool
        - summary: human-readable summary
    """
    profile_path = Path(profile_path).expanduser()
    project_dir = Path(project_dir).expanduser()

    profile_data = json.loads(profile_path.read_text())
    business_name = profile_data.get("business_name", "Unknown Business")

    # Create employees from profile
    employees = create_team_from_profile(profile_path, employees_dir=employees_dir)

    # Add Henry PM (lazy import to avoid circular dependencies)
    try:
        from harness.henry import create_henry  # lazy import

        henry = create_henry(
            business_name=business_name, user_contact="owner"
        )
        employees.append(henry)
        henry_included = True
        logger.info("Henry PM provisioned for %s", business_name)
    except (ImportError, Exception) as exc:
        logger.warning("Could not provision Henry PM: %s", exc)
        henry_included = False

    # Build summary
    employee_summaries = [
        {"name": emp.name, "role": emp.role, "status": emp.status} for emp in employees
    ]

    summary_text = (
        f"Provisioned {len(employees)} employees for {business_name}. "
        f"Team includes: {', '.join(emp['role'] for emp in employee_summaries)}."
    )

    return {
        "business_name": business_name,
        "employee_count": len(employees),
        "employees": employee_summaries,
        "henry_included": henry_included,
        "summary": summary_text,
    }


def _create_employee_name(role_slug: str, business_name: str) -> str:
    """Generate a unique, stable employee name from role slug and business.

    Combines the role slug with a shortened business identifier to create
    memorable, collision-resistant names like "reservations_acme" or "social_media_techco".

    Parameters
    ----------
    role_slug : str
        The role identifier (e.g., "review_responder").
    business_name : str
        The business name (e.g., "ACME Inc.").

    Returns
    -------
    str
        A clean employee name suitable for filesystem use.
    """
    # Extract first meaningful word from business name, lowercase, alphanumeric only
    business_part = business_name.split()[0].lower()
    business_part = "".join(c for c in business_part if c.isalnum())

    # Limit to reasonable length and avoid collisions
    if len(business_part) > 10:
        business_part = business_part[:10]

    return f"{role_slug}_{business_part}"
