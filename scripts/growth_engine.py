#!/usr/bin/env python3
"""
Growth Engine — "Do The Work First" sales engine.

For each new prospect, Hermes:
1. Researches their business (reads their Reddit post, searches for website/phone)
2. Does real work (review responses, leads, email templates)
3. Sends the deliverables as the pitch: "Here's what I built for you. $299/mo?"
"""
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.reach_tools import jina_read_tool, reddit_search_tool
from tools.web_tools import web_search_tool
from tools.twilio_tool import sms_send_tool
from tools.prospect_tool import prospect_update_fn

logger = logging.getLogger(__name__)

_HERMES_HOME = Path(os.environ.get("HOME", str(Path.home()))) / ".hermes"
_SKILLS_DIR = Path(__file__).parent.parent / "skills"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _notify_progress(step: str, detail: str) -> None:
    """Send real-time progress update to owner via Telegram."""
    _telegram_notify(f"{step}\n{detail}")
    logger.info("Progress: %s — %s", step, detail)


def _load_self_selling_skill() -> str:
    path = _SKILLS_DIR / "self-selling.md"
    return path.read_text() if path.exists() else ""


def _load_business_profile() -> dict:
    """Load the business identity from ~/.hermes/business_profile.json."""
    path = _HERMES_HOME / "business_profile.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _telegram_notify(text: str) -> None:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    owner_id = os.environ.get("TELEGRAM_OWNER_ID", "")
    if not bot_token or not owner_id:
        return
    try:
        import httpx
        httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": owner_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        logger.warning("Telegram notify failed: %s", e)


def _load_prospects() -> list:
    path = _HERMES_HOME / "prospects.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text())
        if isinstance(raw, dict):
            return list(raw.get("prospects", raw).values())
        return raw
    except Exception:
        return []


def _infer_industry(pain_point: str) -> str:
    pp = pain_point.lower()
    if any(w in pp for w in ["dentist", "dental", "patient", "clinic", "doctor", "medical"]):
        return "dental/medical"
    if any(w in pp for w in ["restaurant", "food", "dining", "menu", "reservation"]):
        return "restaurant"
    if any(w in pp for w in ["plumb", "hvac", "contractor", "handyman", "electrician", "repair"]):
        return "home services"
    if any(w in pp for w in ["saas", "software", "startup", "app", "tech"]):
        return "SaaS/tech"
    if any(w in pp for w in ["salon", "spa", "beauty", "hair", "nail"]):
        return "beauty/salon"
    return "small business"


# ---------------------------------------------------------------------------
# Step 1: Research
# ---------------------------------------------------------------------------

def research_prospect(prospect: dict) -> dict:
    """
    Research the prospect using their Reddit post URL.
    Returns: {business_name, phone, email, website, city, industry, post_context}
    """
    source_url = prospect.get("source_url", "")
    pain_point = prospect.get("pain_point", "")
    name = prospect.get("name", "")

    post_context = ""
    if source_url and source_url.startswith("http"):
        try:
            post_context = jina_read_tool(source_url)
            logger.info("Read source URL: %d chars", len(post_context))
        except Exception as e:
            logger.warning("jina_read failed for %s: %s", source_url, e)

    industry = _infer_industry(pain_point)
    phone = ""
    email = ""
    website = ""
    business_name = ""

    combined_text = post_context or pain_point

    # Extract email
    em = re.search(r"[\w.+-]+@[\w-]+\.\w+", combined_text)
    if em:
        email = em.group()

    # Extract phone
    ph = re.search(r"\+?1?\s*[\(]?\d{3}[\).\-\s]?\d{3}[\.\-\s]?\d{4}", combined_text)
    if ph:
        phone = re.sub(r"[^\d+]", "", ph.group())
        if len(phone) == 10:
            phone = "+1" + phone
        elif len(phone) == 11 and not phone.startswith("+"):
            phone = "+" + phone

    # Extract website (not reddit)
    url_m = re.search(r"https?://(?!(?:www\.)?reddit|redd\.it)[\w./%-]+", combined_text)
    if url_m:
        website = url_m.group().rstrip(")")

    # Web search for more info if we have key words from pain point
    words = [w for w in pain_point.split() if len(w) > 4 and w.isalpha()]
    if words:
        query = " ".join(words[:4]) + " phone contact website"
        try:
            raw = web_search_tool(query, limit=3)
            results = json.loads(raw) if raw else {}
            items = results.get("data", {}).get("web", [])
            if items and not website:
                website = items[0].get("url", "")
                business_name = items[0].get("title", "")[:80]
        except Exception as e:
            logger.warning("web_search for prospect failed: %s", e)

    # Scrape website for phone/email if missing
    if website and (not phone or not email):
        try:
            site = jina_read_tool(website)
            if not email:
                em2 = re.search(r"[\w.+-]+@[\w-]+\.\w+", site)
                if em2:
                    email = em2.group()
            if not phone:
                ph2 = re.search(r"\+?1?\s*[\(]?\d{3}[\).\-\s]?\d{3}[\.\-\s]?\d{4}", site)
                if ph2:
                    phone = re.sub(r"[^\d+]", "", ph2.group())
                    if len(phone) == 10:
                        phone = "+1" + phone
        except Exception as e:
            logger.warning("website scrape failed: %s", e)

    return {
        "business_name": business_name or name.replace("Reddit: ", "")[:60],
        "phone": phone,
        "email": email,
        "website": website,
        "industry": industry,
        "post_context": post_context[:2000] if post_context else "",
        "source_url": source_url,
    }


# ---------------------------------------------------------------------------
# Step 2: Do the work
# ---------------------------------------------------------------------------

def do_the_work(prospect: dict, research: dict) -> dict:
    """
    Invoke AIAgent to produce real deliverables:
    - 3 Google review responses
    - 5 new leads
    - 2 email templates
    Returns: {reviews, leads, templates, raw_response}
    """
    from run_agent import AIAgent

    business_name = research.get("business_name") or prospect.get("name", "this business")
    industry = research.get("industry", "small business")
    website = research.get("website", "")
    source_url = research.get("source_url", "")
    pain_point = prospect.get("pain_point", "")
    skill_ctx = _load_self_selling_skill()

    biz_profile = _load_business_profile()
    our_name = biz_profile.get("agent_name", "Hermes")
    our_biz = biz_profile.get("business_name", "Hermes")

    system_prompt = f"""You are {our_name} from {our_biz}, an AI employee doing a free demo for a prospect.
Produce real, copy-paste-ready deliverables — not examples or placeholders.
Search the actual web. Find their actual reviews. Find real leads.

{skill_ctx}

After all tasks, output ONLY a JSON block like this (nothing after it):
```json
{{
  "reviews": [{{"review_snippet": "short quote from real review", "response": "your written response"}}],
  "leads": [{{"name": "person or business name", "source": "where found", "url": "link", "contact": "any contact info"}}],
  "templates": [{{"subject": "email subject line", "body": "full email body"}}]
}}
```"""

    task_prompt = f"""Do real work for: {business_name} ({industry})

Context: {pain_point}
Website: {website or "unknown — search for it"}
Reddit post: {source_url}

TASK 1 — 3 Review Responses:
Search Google for "{business_name} reviews" to find their Google Maps page.
Read actual customer reviews. Pick 3 they haven't responded to.
Write a genuine, warm, professional response to each.

TASK 2 — 5 New Customer Leads:
Search Reddit and the web for people in need of {industry} services.
Find 5 real prospects with name/username, where found, and a URL.

TASK 3 — 2 Email Templates for {industry}:
- Appointment reminder / booking confirmation
- Lapsed customer re-engagement

Output the JSON block described above. Real content only — no placeholders."""

    try:
        # Load model/provider from ~/.hermes/config.yaml so standalone scripts
        # don't fall back to AIAgent's hardcoded default on the wrong provider.
        agent_model = "anthropic/claude-sonnet-4.6"
        agent_provider = "anthropic"
        try:
            import yaml
            cfg = yaml.safe_load((_HERMES_HOME / "config.yaml").read_text())
            agent_model = cfg.get("model", {}).get("default", agent_model)
            agent_provider = cfg.get("model", {}).get("provider", agent_provider)
        except Exception:
            pass

        agent = AIAgent(
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
            max_iterations=25,
            model=agent_model,
            provider=agent_provider,
        )
        result = agent.run_conversation(task_prompt, system_message=system_prompt)
        raw = result.get("final_response", "")
        logger.info("do_the_work response: %d chars", len(raw))

        # Extract the JSON block
        json_match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", raw)
        if json_match:
            work = json.loads(json_match.group(1))
        else:
            # Fallback: find raw JSON object
            json_match = re.search(r'\{\s*"reviews"[\s\S]*\}', raw)
            work = json.loads(json_match.group()) if json_match else {}

        work.setdefault("reviews", [])
        work.setdefault("leads", [])
        work.setdefault("templates", [])
        work["raw_response"] = raw
        return work

    except Exception as e:
        logger.warning("do_the_work failed: %s", e)
        return {
            "reviews": [],
            "leads": [],
            "templates": [],
            "raw_response": "",
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# Step 3: Format
# ---------------------------------------------------------------------------

def format_work_package(prospect: dict, research: dict, work: dict) -> str:
    """Format deliverables into a pitch message."""
    business_name = research.get("business_name") or prospect.get("name", "your business")
    industry = research.get("industry", "your business")
    biz_profile = _load_business_profile()
    our_name = biz_profile.get("agent_name", "Hermes")
    our_biz = biz_profile.get("business_name", "")

    reviews = work.get("reviews", [])
    leads = work.get("leads", [])
    templates = work.get("templates", [])

    intro = f"Hi, I'm {our_name}" + (f" from {our_biz}" if our_biz else "") + " — an AI employee."

    lines = [
        intro,
        "",
        f"I spent time working on {business_name} for free.",
        "Here's what I built:",
        "",
        f"✅ {len(reviews)} Google review response{'s' if len(reviews) != 1 else ''} (copy-paste ready)",
        f"✅ {len(leads)} new potential customer lead{'s' if len(leads) != 1 else ''} I found for you",
        f"✅ {len(templates)} email template{'s' if len(templates) != 1 else ''} for {industry}",
        "",
        "--- REVIEW RESPONSES ---",
    ]

    for i, r in enumerate(reviews[:3], 1):
        snippet = r.get("review_snippet", "")[:80]
        response = r.get("response", "")[:280]
        lines.append(f'\nReview {i}: "{snippet}"')
        lines.append(f"Response: {response}")

    lines.append("\n--- NEW CUSTOMER LEADS ---")
    for i, lead in enumerate(leads[:5], 1):
        name = lead.get("name", "")
        source = lead.get("source", "")
        url = lead.get("url", "")
        contact = lead.get("contact", "")
        detail = " — ".join(filter(None, [source, contact or url]))
        lines.append(f"{i}. {name} — {detail}")

    lines += ["", "--- EMAIL TEMPLATES ---"]
    for i, tmpl in enumerate(templates[:2], 1):
        subj = tmpl.get("subject", "")
        body = tmpl.get("body", "")[:280]
        lines.append(f"\nTemplate {i}: {subj}")
        lines.append(body)

    lines += [
        "",
        "---",
        "This took me 2 hours. I do this every day for $299/mo.",
        "Reply YES to get started. No contract.",
        f"— {our_name}" + (f", {our_biz}" if our_biz else ""),
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 4: Send
# ---------------------------------------------------------------------------

def _send_email(to_email: str, business_name: str, body: str) -> bool:
    """Send the work package via Resend (preferred) or SMTP fallback."""
    from tools.email_delivery import send_email

    biz_profile = _load_business_profile()
    our_name = biz_profile.get("agent_name", "Hermes")
    our_biz = biz_profile.get("business_name", "Hermes AI")

    result = send_email(
        to=to_email,
        subject=f"I did some free work for {business_name}",
        body=body,
        from_name=f"{our_name} at {our_biz}",
    )

    if result.get("success"):
        logger.info("Email sent to %s via %s", to_email, result.get("provider"))
        return True
    else:
        logger.warning("Email send failed for %s: %s", to_email, result.get("error"))
        return False


def _make_teaser(full_message: str) -> str:
    """First ~1200 chars — intro + bullet summary only, stops before deliverables."""
    lines = full_message.split("\n")
    teaser_lines = []
    for line in lines:
        if line.strip().startswith("---"):
            break
        teaser_lines.append(line)
    teaser = "\n".join(teaser_lines).strip()
    if len(teaser) > 1200:
        teaser = teaser[:1200] + "..."
    return teaser


def send_work_package(prospect: dict, research: dict, message: str) -> str:
    """
    Deliver the work package via SMS (if phone found) or Telegram alert to owner.
    Returns channel used: "sms", "telegram_owner", or "telegram_no_contact".
    """
    phone = research.get("phone", "")
    email = research.get("email", "")
    business_name = research.get("business_name") or prospect.get("name", "prospect")
    source_url = research.get("source_url", "") or prospect.get("source_url", "")
    prospect_id = prospect.get("id", "")

    # Also check contact_hint for phone
    if not phone:
        contact = prospect.get("contact_hint", "")
        ph = re.search(r"\+?1?\d{10,14}", contact.replace("-", "").replace(" ", ""))
        if ph:
            raw = ph.group()
            phone = ("+1" + raw.lstrip("1")) if not raw.startswith("+") else raw

    channel = "telegram_no_contact"

    if phone and re.match(r"^\+[1-9]\d{7,14}$", phone):
        teaser = _make_teaser(message)
        try:
            result = sms_send_tool(phone, teaser)
            logger.info("SMS teaser sent to %s: %s", phone, result)
            # Second SMS: first review response as proof of work
            reviews = []
            detail_start = message.find("--- REVIEW RESPONSES ---")
            if detail_start != -1:
                detail_preview = message[detail_start:detail_start + 1400]
                sms_send_tool(phone, detail_preview)
            channel = "sms"
        except Exception as e:
            logger.warning("SMS failed for %s: %s", business_name, e)
            channel = "sms_failed"

    elif email:
        # Try sending email directly via SMTP
        sent = _send_email(email, business_name, message)
        if sent:
            _telegram_notify(f"📧 Work package emailed to {email} ({business_name})")
            channel = "email"
        else:
            # Fallback: alert owner to forward manually
            alert = (
                f"📧 Work package ready to email (auto-send failed)\n"
                f"Business: {business_name}\n"
                f"Email: {email}\n"
                f"Source: {source_url}\n\n"
                f"Draft to forward:\n\n{message[:2000]}"
            )
            _telegram_notify(alert)
            channel = "telegram_owner"

    else:
        alert = (
            f"🔥 Hot prospect — no direct contact\n"
            f"Business: {business_name}\n"
            f"Source: {source_url}\n\n"
            f"Work drafted:\n\n{message[:1500]}"
        )
        _telegram_notify(alert)
        channel = "telegram_no_contact"

    if prospect_id:
        try:
            prospect_update_fn(prospect_id, status="contacted", notes=f"Growth engine: {channel}")
        except Exception as e:
            logger.warning("prospect_update_fn failed: %s", e)

    return channel


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------

def run_growth_pipeline(limit: int = 2) -> list:
    """
    Run the full growth pipeline for up to `limit` eligible new prospects.
    Returns list of action strings (caller handles logging).
    """
    cutoff_72h = datetime.now(timezone.utc) - timedelta(hours=72)
    actions = []

    eligible = []
    for p in _load_prospects():
        if p.get("status") not in ("new", None, ""):
            continue
        if (p.get("score") or 0) < 6:
            continue
        if not p.get("source_url"):
            continue
        # Skip recently touched
        last_str = p.get("last_contact") or p.get("updated_at", "")
        if last_str:
            try:
                last = datetime.fromisoformat(last_str.replace("Z", "+00:00"))
                if last > cutoff_72h:
                    continue
            except Exception:
                pass
        eligible.append(p)

    eligible.sort(key=lambda p: p.get("score") or 0, reverse=True)
    logger.info("Growth pipeline: %d eligible, running %d", len(eligible), min(limit, len(eligible)))

    for prospect in eligible[:limit]:
        name = prospect.get("name", "unknown")
        try:
            _notify_progress("📋 Reading prospect", name)
            research = research_prospect(prospect)
            _notify_progress("🔍 Research done", f"{name} — industry: {research.get('industry')}, phone: {'yes' if research.get('phone') else 'no'}, email: {'yes' if research.get('email') else 'no'}")
            _notify_progress("✍️ Doing the work", f"Writing reviews, finding leads, drafting templates for {name}...")
            work = do_the_work(prospect, research)
            n_reviews = len(work.get("reviews", []))
            n_leads = len(work.get("leads", []))
            n_templates = len(work.get("templates", []))
            _notify_progress("✅ Work complete", f"{n_reviews} reviews, {n_leads} leads, {n_templates} templates for {name}")
            message = format_work_package(prospect, research, work)
            channel = send_work_package(prospect, research, message)
            _notify_progress("📬 Delivered", f"Sent to {name} via {channel}")
            actions.append(f"Sent work package to {name} via {channel} ({research.get('industry', '')})")
        except Exception as e:
            logger.warning("Growth pipeline error for %s: %s", name, e)

    return actions


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Hermes growth engine")
    parser.add_argument("--dry-run", action="store_true", help="Print work package, skip sending")
    parser.add_argument("--limit", type=int, default=1, help="Max prospects to process")
    args = parser.parse_args()

    if args.dry_run:
        prospects = _load_prospects()
        test_p = next(
            (p for p in prospects if p.get("source_url") and p.get("status") == "new"),
            {
                "id": "test001",
                "name": "Reddit: small business overwhelmed with customer emails",
                "pain_point": "overwhelmed with customer emails small business",
                "source_url": "https://www.reddit.com/r/smallbusiness/comments/test",
                "contact_hint": "Reddit post",
                "score": 7,
                "status": "new",
            },
        )
        print(f"Prospect: {test_p.get('name')}")
        research = research_prospect(test_p)
        print("\n=== RESEARCH ===")
        for k, v in research.items():
            if k != "post_context":
                print(f"  {k}: {v}")
        work = do_the_work(test_p, research)
        msg = format_work_package(test_p, research, work)
        print("\n=== WORK PACKAGE ===")
        print(msg)
        print("\n[DRY RUN — not sent]")
    else:
        results = run_growth_pipeline(limit=args.limit)
        print(f"Completed {len(results)} actions:")
        for a in results:
            print(f"  • {a}")
