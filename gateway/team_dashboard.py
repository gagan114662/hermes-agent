"""Team Dashboard — Real-time view of AI employee team status.

FastAPI router providing:
- GET /api/team/status (JSON) - Employee statuses and recent activity
- GET /team/dashboard (HTML) - WhatsApp-style team view

Usage
-----
    from gateway.team_dashboard import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router, prefix="/team")
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from fastapi import APIRouter, Response
except ImportError:
    # Fallback if FastAPI not available
    APIRouter = None
    Response = None

logger = logging.getLogger(__name__)


def create_router():
    """Create and return the FastAPI router for team dashboard."""
    if APIRouter is None:
        logger.warning("FastAPI not available. Team dashboard will not be available.")
        return None

    router = APIRouter()

    @router.get("/status")
    async def get_team_status():
        """Get JSON status of all team members."""
        try:
            from harness.employee import Employee

            employees = Employee.list_all()

            team_status = {
                "timestamp": datetime.now().isoformat(),
                "employee_count": len(employees),
                "employees": [
                    {
                        "name": emp.name,
                        "role": emp.role,
                        "status": emp.status,
                        "schedule": emp.schedule,
                        "goal": emp.goal[:100],  # Truncate for brevity
                    }
                    for emp in employees
                ],
                "recent_activity": _load_recent_activity(),
            }
            return team_status
        except Exception as exc:
            logger.error(f"Error getting team status: {exc}")
            return {"error": str(exc), "timestamp": datetime.now().isoformat()}

    @router.get("/dashboard")
    async def get_dashboard():
        """Get HTML dashboard (WhatsApp-style team view)."""
        try:
            from harness.employee import Employee

            employees = Employee.list_all()

            # Build HTML
            html = _build_dashboard_html(employees)
            return Response(content=html, media_type="text/html")
        except Exception as exc:
            logger.error(f"Error building dashboard: {exc}")
            return Response(
                content=f"<h1>Error</h1><p>{str(exc)}</p>",
                media_type="text/html",
            )

    return router


def _load_recent_activity(limit: int = 10) -> list[dict]:
    """Load recent activity from action_log.jsonl."""
    try:
        log_path = Path.home() / ".hermes" / "action_log.jsonl"
        if not log_path.exists():
            return []

        activities = []
        with open(log_path, "r") as f:
            for line in f:
                try:
                    activities.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        # Return last N activities
        return activities[-limit:]
    except Exception as exc:
        logger.warning(f"Could not load activity log: {exc}")
        return []


def _build_dashboard_html(employees: list) -> str:
    """Build WhatsApp-style HTML dashboard with live team chat and experiments."""
    employee_rows = ""

    for emp in employees:
        status_color = {
            "idle": "#95a5a6",
            "working": "#3498db",
            "completed": "#2ecc71",
            "blocked": "#e74c3c",
        }.get(emp.status, "#95a5a6")

        status_emoji = {
            "idle": "⏸", "working": "🔄", "completed": "✅", "blocked": "🚨"
        }.get(emp.status, "❓")

        # Get experiment stats for this employee
        exp_html = ""
        try:
            from harness.experiment_loop import ExperimentLoop
            loop = ExperimentLoop(emp.name)
            stats = loop.get_win_rate()
            if stats["total_experiments"] > 0:
                exp_html = (
                    f'<div class="experiments">'
                    f'<span class="exp-badge">'
                    f'{stats["total_experiments"]} experiments · '
                    f'{stats["win_rate"]:.0%} win rate</span></div>'
                )
        except Exception:
            pass

        employee_rows += f"""
        <div class="employee-card">
            <div class="card-header">
                <div class="status-dot" style="background:{status_color}"></div>
                <div>
                    <h3>{emp.name.replace('_', ' ').title()}</h3>
                    <span class="role">{emp.role}</span>
                </div>
                <span class="status-badge" style="background:{status_color}20;color:{status_color}">
                    {status_emoji} {emp.status}
                </span>
            </div>
            <p class="goal">{emp.goal[:100]}</p>
            {exp_html}
            <div class="schedule">
                <code>{emp.schedule or 'Ad-hoc'}</code>
            </div>
        </div>
        """

    # Team chat feed
    chat_html = ""
    try:
        from gateway.team_chat import format_chat_html
        chat_html = format_chat_html(hours=24)
    except Exception:
        chat_html = '<div style="padding:20px;color:#8696a0;">Team chat loading...</div>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hermes Team Dashboard</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:#0b141a; color:#e9edef; }}
.layout {{ display:grid; grid-template-columns:1fr 400px; gap:0; min-height:100vh; }}
.main {{ padding:24px; overflow-y:auto; }}
.sidebar {{ background:#111b21; border-left:1px solid #222d34; overflow-y:auto; }}
.header {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:24px; }}
.header h1 {{ font-size:24px; color:#e9edef; }}
.header .live {{ display:flex; align-items:center; gap:6px; font-size:13px; color:#00a884; }}
.header .live::before {{ content:''; width:8px; height:8px; background:#00a884; border-radius:50%; animation:pulse 2s infinite; }}
@keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:0.4}} }}
.stats {{ display:flex; gap:12px; margin-bottom:24px; }}
.stat {{ background:#202c33; border-radius:8px; padding:12px 16px; flex:1; }}
.stat .num {{ font-size:24px; font-weight:700; color:#00a884; }}
.stat .label {{ font-size:12px; color:#8696a0; margin-top:2px; }}
.employee-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:12px; }}
.employee-card {{ background:#202c33; border-radius:10px; padding:14px; transition:transform .15s; }}
.employee-card:hover {{ transform:translateY(-2px); }}
.card-header {{ display:flex; align-items:center; gap:10px; margin-bottom:10px; }}
.status-dot {{ width:10px; height:10px; border-radius:50%; flex-shrink:0; }}
.card-header h3 {{ font-size:15px; color:#e9edef; }}
.role {{ font-size:12px; color:#8696a0; }}
.status-badge {{ font-size:11px; padding:2px 8px; border-radius:12px; margin-left:auto; font-weight:600; }}
.goal {{ font-size:13px; color:#8696a0; margin-bottom:8px; line-height:1.4; }}
.experiments {{ margin-bottom:8px; }}
.exp-badge {{ font-size:11px; background:#00a88420; color:#00a884; padding:3px 8px; border-radius:6px; }}
.schedule code {{ font-size:11px; color:#8696a0; background:#111b21; padding:3px 6px; border-radius:4px; }}
.sidebar-header {{ padding:16px; border-bottom:1px solid #222d34; font-size:15px; font-weight:600; }}
.refresh-note {{ text-align:center; padding:8px; font-size:11px; color:#8696a0; }}
@media (max-width:900px) {{ .layout {{ grid-template-columns:1fr; }} .sidebar {{ border-left:none; border-top:1px solid #222d34; }} }}
</style>
<script>setTimeout(()=>location.reload(), 15000);</script>
</head>
<body>
<div class="layout">
  <div class="main">
    <div class="header">
      <h1>Hermes Team</h1>
      <div class="live">Live · {datetime.now().strftime('%I:%M %p')}</div>
    </div>
    <div class="stats">
      <div class="stat"><div class="num">{len(employees)}</div><div class="label">Employees</div></div>
      <div class="stat"><div class="num">{len([e for e in employees if e.status == 'working'])}</div><div class="label">Working</div></div>
      <div class="stat"><div class="num">{len([e for e in employees if e.status == 'blocked'])}</div><div class="label">Blocked</div></div>
      <div class="stat"><div class="num">{len([e for e in employees if e.status == 'completed'])}</div><div class="label">Done Today</div></div>
    </div>
    <div class="employee-grid">{employee_rows}</div>
  </div>
  <div class="sidebar">
    <div class="sidebar-header">Team Chat</div>
    {chat_html}
    <div class="refresh-note">Auto-refreshes every 15s</div>
  </div>
</div>
</body></html>"""

    return html


# Export router if FastAPI available
if APIRouter:
    router = create_router()
else:
    router = None
