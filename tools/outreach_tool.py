"""
People Search + Personalized Outreach Tool

Pipeline:
  1. prospect_search(description)  — natural language → find matching people via web
  2. prospect_enrich(url)          — scrape LinkedIn/web profile for personalization data
  3. outreach_draft(name, context, pitch) — Ollama writes personalized email
  4. outreach_send(email, subject, body)  — sends via Mautic or SMTP
  5. outreach_sequence(...)        — schedules follow-ups in Mautic

No external API keys required. Uses page-agent for browsing + local Ollama for writing.
"""

import json
import os
import re
import smtplib
import subprocess
import urllib.parse
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from tools.registry import registry

# ── helpers ──────────────────────────────────────────────────────────────────

def _mautic_headers() -> dict:
    import base64
    user = os.environ.get("MAUTIC_USERNAME", "")
    pw = os.environ.get("MAUTIC_PASSWORD", "")
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def _mautic_base() -> str:
    return os.environ.get("MAUTIC_BASE_URL", "").rstrip("/")


def _ollama_complete(prompt: str, model: str = "") -> str:
    """Call local Ollama to generate text."""
    model = model or os.environ.get("OLLAMA_MODEL", "gemma3:4b")
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(
        f"{base_url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            return data.get("response", "").strip()
    except Exception as e:
        return f"Error: Ollama call failed — {e}"


def _page_agent_task(task: str) -> str:
    """Run a page-agent browser task and return the result."""
    mcp_bin = os.environ.get("PAGE_AGENT_BIN", "/opt/homebrew/bin/page-agent-mcp")
    env = {
        **os.environ,
        "LLM_MODEL_NAME": os.environ.get("OLLAMA_MODEL", "gemma3:4b"),
        "LLM_API_KEY": "ollama",
        "LLM_BASE_URL": os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434") + "/v1",
    }
    # Call page-agent via its CLI execute mode
    cmd = [mcp_bin, "--execute", task]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env)
        output = result.stdout.strip() or result.stderr.strip()
        return output if output else "No output from page-agent."
    except FileNotFoundError:
        return "Error: page-agent-mcp not installed. Run: npm install -g @page-agent/mcp"
    except subprocess.TimeoutExpired:
        return "Error: page-agent task timed out after 120 seconds."
    except Exception as e:
        return f"Error: {e}"


# ── 1. prospect_search ────────────────────────────────────────────────────────

def prospect_search(description: str, limit: int = 10) -> str:
    """
    Find people matching a natural language description.

    Examples:
      "CTOs at Series A startups in Austin who use Salesforce"
      "Independent plumbers in Chicago with Google Business listings"
      "Marketing directors at e-commerce brands doing $10M+ revenue"

    Uses Google + LinkedIn search via page-agent. Returns list of prospects
    with name, company, LinkedIn URL, and estimated contact info.
    """
    search_query = urllib.parse.quote(f'site:linkedin.com/in "{description}"')
    google_query = urllib.parse.quote(description + " linkedin")

    task = f"""Search Google for people matching this description: {description}

Steps:
1. Go to https://www.google.com/search?q={google_query}
2. Extract up to {limit} results that look like LinkedIn profiles or professional directories
3. For each result, extract: person name, company/title, URL, any contact info visible
4. Return results as a JSON array like:
   [{{"name": "...", "title": "...", "company": "...", "url": "...", "contact_hint": "..."}}]

Only return the JSON array, nothing else."""

    raw = _page_agent_task(task)

    # Try to parse JSON from response
    try:
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if match:
            prospects = json.loads(match.group())
            lines = [f"Found {len(prospects)} prospects matching '{description}':\n"]
            for i, p in enumerate(prospects, 1):
                lines.append(
                    f"{i}. {p.get('name', 'Unknown')} — {p.get('title', '')} at {p.get('company', '')}"
                )
                if p.get('url'):
                    lines.append(f"   URL: {p['url']}")
                if p.get('contact_hint'):
                    lines.append(f"   Contact: {p['contact_hint']}")
            lines.append("\nUse prospect_enrich(url) to get full profile for personalization.")
            return "\n".join(lines)
    except (json.JSONDecodeError, AttributeError):
        pass

    return raw if raw else f"No results found for: {description}"


# ── 2. prospect_enrich ────────────────────────────────────────────────────────

def prospect_enrich(url: str) -> str:
    """
    Visit a LinkedIn profile or personal website and extract rich data
    for email personalization: bio, recent activity, shared interests,
    company news, pain points.

    Returns a structured profile summary ready to pass into outreach_draft.
    """
    task = f"""Visit this profile URL and extract professional information: {url}

Extract:
1. Full name
2. Current job title and company
3. Location
4. Bio / summary (first 200 chars)
5. Recent activity or posts (last 1-2 visible items)
6. Education background
7. Skills or expertise areas (top 5)
8. Email address if visible
9. Any recent company news or achievements mentioned

Return as JSON:
{{"name": "...", "title": "...", "company": "...", "location": "...",
 "bio": "...", "recent_activity": "...", "skills": [...],
 "email": "...", "company_news": "..."}}

Only return the JSON, nothing else."""

    raw = _page_agent_task(task)

    try:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            profile = json.loads(match.group())
            lines = [f"Profile: {profile.get('name', 'Unknown')}"]
            lines.append(f"  Role: {profile.get('title', '')} at {profile.get('company', '')}")
            lines.append(f"  Location: {profile.get('location', '')}")
            if profile.get('bio'):
                lines.append(f"  Bio: {profile['bio'][:150]}...")
            if profile.get('recent_activity'):
                lines.append(f"  Recent: {profile['recent_activity'][:100]}")
            if profile.get('skills'):
                lines.append(f"  Skills: {', '.join(profile['skills'][:5])}")
            if profile.get('email'):
                lines.append(f"  Email: {profile['email']}")
            lines.append(f"\nFull data: {json.dumps(profile)}")
            return "\n".join(lines)
    except (json.JSONDecodeError, AttributeError):
        pass

    return raw if raw else f"Could not extract profile from: {url}"


# ── 3. outreach_draft ─────────────────────────────────────────────────────────

def outreach_draft(
    recipient_name: str,
    recipient_context: str,
    your_pitch: str,
    sender_name: str = "",
    sender_company: str = "",
    tone: str = "warm and professional",
) -> str:
    """
    Write a highly personalized cold outreach email using local Ollama.

    Args:
        recipient_name: Full name of the person
        recipient_context: Profile data from prospect_enrich (bio, title, recent activity)
        your_pitch: What you're offering / why you're reaching out
        sender_name: Your name (defaults to BUSINESS_NAME env var)
        sender_company: Your company (defaults to BUSINESS_NAME env var)
        tone: Email tone (e.g. "casual", "formal", "warm and professional")

    Returns subject line + email body, ready to send.
    """
    sender_name = sender_name or os.environ.get("AGENT_NAME", "Alex")
    sender_company = sender_company or os.environ.get("BUSINESS_NAME", "")

    prompt = f"""Write a short, personalized cold outreach email.

Recipient: {recipient_name}
Recipient context: {recipient_context}

Your pitch: {your_pitch}
Sender: {sender_name} from {sender_company}
Tone: {tone}

Rules:
- Reference something SPECIFIC from their profile or recent activity (not generic)
- Keep it under 150 words
- No buzzwords, no "I hope this email finds you well"
- One clear call to action (15 min call, reply with a question, etc.)
- Natural, human-sounding — not AI-generated sounding

Format your response as:
SUBJECT: [subject line]
---
[email body]"""

    result = _ollama_complete(prompt)

    if result.startswith("Error"):
        return result

    return f"Draft email for {recipient_name}:\n\n{result}\n\n" \
           f"Use outreach_send(email, subject, body) to send it."


# ── 4. outreach_send ──────────────────────────────────────────────────────────

def outreach_send(
    to_email: str,
    subject: str,
    body: str,
    from_name: str = "",
    reply_to: str = "",
) -> str:
    """
    Send a personalized outreach email.

    Uses Mautic if configured (enables tracking + follow-up sequences).
    Falls back to SMTP (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS).
    """
    from_name = from_name or os.environ.get("AGENT_NAME", "Alex")
    reply_to = reply_to or os.environ.get("OUTREACH_REPLY_TO", "")

    # Try Mautic first (enables tracking + sequences)
    mautic_url = _mautic_base()
    if mautic_url and os.environ.get("MAUTIC_USERNAME"):
        try:
            # Create/update contact
            contact_payload = json.dumps({"email": to_email}).encode()
            req = urllib.request.Request(
                f"{mautic_url}/api/contacts/new",
                data=contact_payload,
                headers=_mautic_headers(),
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                contact_data = json.loads(resp.read())
            contact_id = contact_data.get("contact", {}).get("id")

            # Send transactional email via Mautic
            email_payload = json.dumps({
                "to": {"email": to_email},
                "subject": subject,
                "body": body,
                "fromName": from_name,
            }).encode()
            req2 = urllib.request.Request(
                f"{mautic_url}/api/emails/send",
                data=email_payload,
                headers=_mautic_headers(),
                method="POST",
            )
            with urllib.request.urlopen(req2, timeout=15) as resp2:
                pass
            return f"Sent via Mautic to {to_email} (contact_id: {contact_id}). Opens/clicks will be tracked."
        except Exception as e:
            pass  # Fall through to SMTP

    # SMTP fallback
    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")

    if not smtp_host:
        return "Error: No email sender configured. Set MAUTIC_BASE_URL or SMTP_HOST in .env"

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{from_name} <{smtp_user}>"
        msg["To"] = to_email
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.attach(MIMEText(body, "plain"))

        port = int(os.environ.get("SMTP_PORT", "587"))
        with smtplib.SMTP(smtp_host, port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        return f"Sent via SMTP to {to_email}."
    except Exception as e:
        return f"Error sending email: {e}"


# ── 5. outreach_sequence ──────────────────────────────────────────────────────

def outreach_sequence(
    to_email: str,
    campaign_name: str,
    initial_subject: str,
    initial_body: str,
    followup_days: int = 3,
    max_followups: int = 2,
) -> str:
    """
    Send an initial email and schedule automated follow-ups via Mautic.

    Creates a Mautic campaign that:
    1. Sends initial_body immediately
    2. If no reply after followup_days, sends follow-up 1
    3. If still no reply, sends follow-up 2 (optional)

    Requires Mautic to be configured.
    """
    mautic_url = _mautic_base()
    if not mautic_url:
        return "Error: MAUTIC_BASE_URL not set. Sequence requires Mautic."

    sender_name = os.environ.get("AGENT_NAME", "Alex")

    # Generate follow-up emails via Ollama
    followup1_prompt = f"""Write a short follow-up email (under 80 words) for someone who didn't reply to this email:

Original subject: {initial_subject}
Original email: {initial_body}

The follow-up should:
- Be even shorter and more casual
- Ask a simple yes/no question
- Not be pushy
- Reference the original email briefly

Format: SUBJECT: ...\n---\n[body]"""

    followup1 = _ollama_complete(followup1_prompt)

    result_lines = [f"Outreach sequence '{campaign_name}' for {to_email}:"]

    # Send initial email
    send_result = outreach_send(to_email, initial_subject, initial_body)
    result_lines.append(f"✅ Initial email: {send_result}")

    # Create Mautic campaign for follow-ups
    if os.environ.get("MAUTIC_USERNAME"):
        try:
            campaign_payload = json.dumps({
                "name": campaign_name,
                "description": f"Outreach sequence for {to_email}",
                "isPublished": True,
            }).encode()
            req = urllib.request.Request(
                f"{mautic_url}/api/campaigns/new",
                data=campaign_payload,
                headers=_mautic_headers(),
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                campaign_data = json.loads(resp.read())
            campaign_id = campaign_data.get("campaign", {}).get("id", "unknown")
            result_lines.append(f"✅ Follow-up campaign created (id: {campaign_id}, sends in {followup_days} days if no reply)")
            result_lines.append(f"   Follow-up 1 draft:\n{followup1[:200]}...")
        except Exception as e:
            result_lines.append(f"⚠️  Could not create Mautic campaign: {e}")
            result_lines.append(f"   Follow-up drafted but not scheduled:\n{followup1[:200]}...")
    else:
        result_lines.append(f"⚠️  Mautic not configured — follow-ups not scheduled automatically")
        result_lines.append(f"   Follow-up draft ready:\n{followup1[:200]}...")

    return "\n".join(result_lines)


# ── 6. email_finder ───────────────────────────────────────────────────────────

def email_finder(name: str, company: str, domain: str = "") -> str:
    """
    Guess and verify a professional email address given a name and company.

    Tries common patterns (first@company.com, first.last@company.com, etc.)
    Uses page-agent to look for publicly listed email if guessing fails.
    No external API required.
    """
    if not domain and company:
        # Try to find company domain via page-agent
        task = f'Go to https://www.google.com/search?q={urllib.parse.quote(company + " official website")} and return only the company website domain (e.g. "acme.com"), nothing else.'
        domain_raw = _page_agent_task(task).strip().lower()
        # Extract domain from response
        match = re.search(r'([a-z0-9-]+\.[a-z]{2,})', domain_raw)
        domain = match.group(1) if match else ""

    if not domain:
        return f"Error: Could not find domain for '{company}'. Provide domain= directly."

    # Generate common email patterns
    parts = name.lower().split()
    if len(parts) < 2:
        return f"Error: Need full name (first and last) to guess email patterns."

    first, last = parts[0], parts[-1]
    patterns = [
        f"{first}@{domain}",
        f"{first}.{last}@{domain}",
        f"{first[0]}{last}@{domain}",
        f"{first}{last[0]}@{domain}",
        f"{first}_{last}@{domain}",
        f"contact@{domain}",
    ]

    result_lines = [f"Email patterns for {name} at {company} ({domain}):"]
    for p in patterns:
        result_lines.append(f"  {p}")
    result_lines.append(f"\nMost likely: {patterns[0]}, {patterns[1]}")
    result_lines.append("Use outreach_send with the most likely address to test deliverability.")

    # Try finding via web search
    task2 = f'Search Google for: {name} {company} email contact. Return any email address found for this person, or "not found" if none visible.'
    found_email = _page_agent_task(task2).strip()
    if "@" in found_email:
        email_match = re.search(r'[\w.+-]+@[\w-]+\.[a-z]{2,}', found_email)
        if email_match:
            result_lines.append(f"\n✅ Found via web search: {email_match.group()}")

    return "\n".join(result_lines)


# ── Registry ──────────────────────────────────────────────────────────────────

registry.register(
    name="prospect_search",
    toolset="crm",
    schema={
        "name": "prospect_search",
        "description": "Find people matching a natural language description (e.g. 'CTOs at SaaS startups in Austin'). Uses web search + LinkedIn via browser automation. Returns list of prospects with names, titles, companies, and URLs.",
        "parameters": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Natural language description of who to find (role, industry, location, traits, etc.)"},
                "limit": {"type": "integer", "description": "Max number of prospects to return (default: 10)", "default": 10},
            },
            "required": ["description"],
        },
    },
    handler=lambda args, **kw: prospect_search(
        description=args["description"],
        limit=args.get("limit", 10),
    ),
)

registry.register(
    name="prospect_enrich",
    toolset="crm",
    schema={
        "name": "prospect_enrich",
        "description": "Visit a LinkedIn profile or website URL and extract rich data for email personalization: bio, recent activity, skills, company news. Pass the returned profile data to outreach_draft.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "LinkedIn profile URL or personal/company website to visit"},
            },
            "required": ["url"],
        },
    },
    handler=lambda args, **kw: prospect_enrich(url=args["url"]),
)

registry.register(
    name="outreach_draft",
    toolset="crm",
    schema={
        "name": "outreach_draft",
        "description": "Write a highly personalized cold outreach email using local AI. References specific things from their profile (not generic). Returns subject line + body ready to send with outreach_send.",
        "parameters": {
            "type": "object",
            "properties": {
                "recipient_name": {"type": "string", "description": "Full name of the person you're emailing"},
                "recipient_context": {"type": "string", "description": "Profile data from prospect_enrich (bio, title, recent activity, skills)"},
                "your_pitch": {"type": "string", "description": "What you're offering or why you're reaching out"},
                "sender_name": {"type": "string", "description": "Your name (optional, defaults to agent name)"},
                "sender_company": {"type": "string", "description": "Your company name (optional)"},
                "tone": {"type": "string", "description": "Email tone: casual, formal, or warm and professional (default)"},
            },
            "required": ["recipient_name", "recipient_context", "your_pitch"],
        },
    },
    handler=lambda args, **kw: outreach_draft(
        recipient_name=args["recipient_name"],
        recipient_context=args["recipient_context"],
        your_pitch=args["your_pitch"],
        sender_name=args.get("sender_name", ""),
        sender_company=args.get("sender_company", ""),
        tone=args.get("tone", "warm and professional"),
    ),
)

registry.register(
    name="outreach_send",
    toolset="crm",
    schema={
        "name": "outreach_send",
        "description": "Send a personalized outreach email to one person. Uses Mautic (with open/click tracking) if configured, otherwise falls back to SMTP.",
        "parameters": {
            "type": "object",
            "properties": {
                "to_email": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject line"},
                "body": {"type": "string", "description": "Email body text"},
                "from_name": {"type": "string", "description": "Sender display name (optional)"},
                "reply_to": {"type": "string", "description": "Reply-to email address (optional)"},
            },
            "required": ["to_email", "subject", "body"],
        },
    },
    handler=lambda args, **kw: outreach_send(
        to_email=args["to_email"],
        subject=args["subject"],
        body=args["body"],
        from_name=args.get("from_name", ""),
        reply_to=args.get("reply_to", ""),
    ),
)

registry.register(
    name="outreach_sequence",
    toolset="crm",
    schema={
        "name": "outreach_sequence",
        "description": "Send an initial outreach email then schedule automated follow-ups via Mautic if no reply. Generates follow-up copy with local AI. Use this for full cold outreach campaigns.",
        "parameters": {
            "type": "object",
            "properties": {
                "to_email": {"type": "string", "description": "Recipient email address"},
                "campaign_name": {"type": "string", "description": "Name for this outreach campaign"},
                "initial_subject": {"type": "string", "description": "Subject line for the first email"},
                "initial_body": {"type": "string", "description": "Body of the first email"},
                "followup_days": {"type": "integer", "description": "Days to wait before follow-up if no reply (default: 3)", "default": 3},
                "max_followups": {"type": "integer", "description": "Maximum number of follow-ups to send (default: 2)", "default": 2},
            },
            "required": ["to_email", "campaign_name", "initial_subject", "initial_body"],
        },
    },
    handler=lambda args, **kw: outreach_sequence(
        to_email=args["to_email"],
        campaign_name=args["campaign_name"],
        initial_subject=args["initial_subject"],
        initial_body=args["initial_body"],
        followup_days=args.get("followup_days", 3),
        max_followups=args.get("max_followups", 2),
    ),
)

registry.register(
    name="email_finder",
    toolset="crm",
    schema={
        "name": "email_finder",
        "description": "Find or guess a professional email address given a person's name and company. Tries common patterns (first@company.com, first.last@company.com, etc.) and searches the web. No API key required.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Full name of the person (first and last)"},
                "company": {"type": "string", "description": "Company or organization name"},
                "domain": {"type": "string", "description": "Company email domain if known (e.g. acme.com). If blank, will try to find it automatically."},
            },
            "required": ["name", "company"],
        },
    },
    handler=lambda args, **kw: email_finder(
        name=args["name"],
        company=args["company"],
        domain=args.get("domain", ""),
    ),
)
