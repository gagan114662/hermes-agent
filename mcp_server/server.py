"""
Hermes AI MCP Server — Free AI employee tools for small businesses.

Provides 5 standalone tools that work without API keys or external services.
Each tool delivers genuinely useful output using heuristics and rules.

Distribution/marketing channel for Hermes AI ($299/mo AI employees).

Run with: python -m mcp_server.server
"""

from __future__ import annotations

import math
from typing import Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("hermes-ai", instructions="Free AI employee tools for small businesses")

CTA = "\n\n---\nPowered by Hermes AI — get a full AI employee at hermesai.co"

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

SPAM_KEYWORDS = {
    "unsubscribe", "viagra", "casino", "lottery", "winner", "free money",
    "click here", "act now", "limited time", "no obligation", "risk free",
    "congratulations", "million dollars", "nigerian", "prince", "crypto airdrop",
    "double your", "make money fast", "work from home guarantee",
}

NEWSLETTER_KEYWORDS = {
    "newsletter", "digest", "weekly update", "monthly update", "roundup",
    "bulletin", "recap", "edition", "issue #", "vol.", "curated",
}

URGENT_KEYWORDS = {
    "urgent", "asap", "immediately", "deadline", "overdue", "final notice",
    "action required", "time sensitive", "critical", "emergency", "past due",
    "expiring", "last chance", "respond by", "eod", "end of day",
}

LEAD_KEYWORDS = {
    "interested", "pricing", "demo", "quote", "proposal", "partnership",
    "inquiry", "consultation", "meeting", "schedule", "call", "services",
    "rates", "availability", "hire", "contract", "project", "budget",
    "referral", "recommendation", "introduction",
}

SUPPORT_KEYWORDS = {
    "help", "issue", "problem", "bug", "error", "broken", "not working",
    "complaint", "refund", "cancel", "return", "disappointed", "trouble",
    "support", "ticket", "fix", "resolve", "escalate",
}


def _classify_email(subject: str, sender: str) -> tuple[str, int]:
    """Return (category, priority_score 1-10) for an email."""
    text = f"{subject} {sender}".lower()

    # Spam check first
    spam_hits = sum(1 for kw in SPAM_KEYWORDS if kw in text)
    if spam_hits >= 2 or any(kw in text for kw in {"viagra", "casino", "lottery", "nigerian prince"}):
        return "spam", 1

    # Newsletter
    newsletter_hits = sum(1 for kw in NEWSLETTER_KEYWORDS if kw in text)
    if newsletter_hits >= 1 and spam_hits == 0:
        urgent_hits = sum(1 for kw in URGENT_KEYWORDS if kw in text)
        if urgent_hits == 0:
            return "newsletter", 2

    # Urgent
    urgent_hits = sum(1 for kw in URGENT_KEYWORDS if kw in text)
    if urgent_hits >= 1:
        return "urgent", 9 + min(urgent_hits - 1, 1)

    # Lead
    lead_hits = sum(1 for kw in LEAD_KEYWORDS if kw in text)
    if lead_hits >= 1:
        return "lead", 7 + min(lead_hits - 1, 2)

    # Support
    support_hits = sum(1 for kw in SUPPORT_KEYWORDS if kw in text)
    if support_hits >= 1:
        return "support", 6 + min(support_hits - 1, 2)

    # Default: general
    return "general", 4


# ---------------------------------------------------------------------------
# Tool 1: analyze_inbox
# ---------------------------------------------------------------------------

@mcp.tool()
def analyze_inbox(
    emails: list[dict],
) -> str:
    """Analyze and prioritize an inbox of emails.

    Takes a list of emails, each with 'subject' and 'sender' keys.
    Categorizes each as urgent, lead, support, spam, newsletter, or general.
    Returns a prioritized action list.

    Example input:
        [
            {"subject": "URGENT: Invoice overdue", "sender": "billing@vendor.com"},
            {"subject": "Interested in your services", "sender": "jane@prospect.com"},
            {"subject": "Weekly Tech Digest", "sender": "news@techdigest.com"}
        ]
    """
    if not emails:
        return "No emails provided. Pass a list of dicts with 'subject' and 'sender' keys." + CTA

    classified: list[dict] = []
    for i, email in enumerate(emails):
        subject = email.get("subject", "(no subject)")
        sender = email.get("sender", "(unknown)")
        category, priority = _classify_email(subject, sender)
        classified.append({
            "index": i + 1,
            "subject": subject,
            "sender": sender,
            "category": category,
            "priority": priority,
        })

    # Sort by priority descending
    classified.sort(key=lambda x: x["priority"], reverse=True)

    # Build summary counts
    cats: dict[str, int] = {}
    for item in classified:
        cats[item["category"]] = cats.get(item["category"], 0) + 1

    lines: list[str] = []
    lines.append(f"INBOX ANALYSIS — {len(emails)} emails scanned")
    lines.append("=" * 50)

    # Summary
    lines.append("\nBREAKDOWN:")
    tag_map = {"urgent": "!!", "lead": "$$", "support": "??", "spam": "XX", "newsletter": ">>", "general": "--"}
    for cat in ["urgent", "lead", "support", "general", "newsletter", "spam"]:
        count = cats.get(cat, 0)
        if count > 0:
            lines.append(f"  [{tag_map.get(cat, '--')}] {cat.upper()}: {count}")

    # Prioritized action list
    lines.append("\nPRIORITIZED ACTION LIST:")
    lines.append("-" * 50)

    action_map = {
        "urgent": "RESPOND NOW",
        "lead": "FOLLOW UP TODAY — potential revenue",
        "support": "RESOLVE — customer satisfaction at stake",
        "general": "Review when time permits",
        "newsletter": "Batch read or skip",
        "spam": "Delete / mark as spam",
    }

    for item in classified:
        cat = item["category"]
        action = action_map.get(cat, "Review")
        priority_bar = "*" * item["priority"]
        lines.append(
            f"\n  #{item['index']} [{cat.upper()}] Priority: {priority_bar} ({item['priority']}/10)"
            f"\n      From: {item['sender']}"
            f"\n      Subj: {item['subject']}"
            f"\n      Action: {action}"
        )

    # Recommendations
    urgent_count = cats.get("urgent", 0)
    lead_count = cats.get("lead", 0)
    spam_count = cats.get("spam", 0)

    lines.append("\n" + "=" * 50)
    lines.append("RECOMMENDATIONS:")
    if urgent_count > 0:
        lines.append(f"  - You have {urgent_count} urgent email(s). Handle these first.")
    if lead_count > 0:
        lines.append(f"  - {lead_count} potential lead(s) detected. Responding within 1 hour increases conversion by 7x.")
    if spam_count > 2:
        lines.append(f"  - {spam_count} spam emails. Consider tightening your spam filters.")
    if len(emails) > 20:
        lines.append("  - Heavy inbox. A Hermes AI employee can auto-triage and draft responses for you 24/7.")
    lines.append(f"  - Estimated manual processing time: ~{len(emails) * 3} minutes.")
    lines.append(f"  - With Hermes AI employee: ~{max(len(emails) // 3, 1)} minutes (auto-drafted responses + auto-triage).")

    return "\n".join(lines) + CTA


# ---------------------------------------------------------------------------
# Tool 2: score_leads
# ---------------------------------------------------------------------------

BUSINESS_TYPE_SCORES = {
    "saas": 15, "software": 15, "ecommerce": 14, "e-commerce": 14,
    "agency": 13, "consulting": 13, "professional services": 12,
    "real estate": 12, "insurance": 11, "financial services": 11,
    "healthcare": 10, "dental": 10, "legal": 10, "law firm": 10,
    "restaurant": 7, "retail": 7, "construction": 6,
    "nonprofit": 5, "non-profit": 5, "education": 5,
}

SOURCE_SCORES = {
    "referral": 20, "word of mouth": 18, "organic search": 14, "seo": 14,
    "google ads": 12, "paid search": 12, "linkedin": 11,
    "content marketing": 10, "blog": 10, "webinar": 10,
    "facebook": 8, "instagram": 7, "cold email": 6, "cold call": 5,
    "purchased list": 3, "trade show": 9, "conference": 9,
    "partner": 16, "integration": 15,
}


@mcp.tool()
def score_leads(
    prospects: list[dict],
) -> str:
    """Score one or more sales leads and rank them by potential.

    Each prospect dict should have:
        - name (str): Contact or company name
        - business_type (str): e.g. "SaaS", "ecommerce", "consulting"
        - size (int or str): Number of employees
        - source (str): How they found you, e.g. "referral", "cold email", "organic search"
        - budget (str, optional): "low", "medium", "high", or a dollar amount
        - timeline (str, optional): "immediate", "this quarter", "exploring"
        - notes (str, optional): Any extra context

    Example:
        [{"name": "Jane Smith", "business_type": "SaaS", "size": 15, "source": "referral"}]
    """
    if not prospects:
        return "No prospects provided. Pass a list of prospect dicts." + CTA

    scored: list[dict] = []

    for prospect in prospects:
        name = prospect.get("name", "Unknown")
        btype = prospect.get("business_type", "").lower().strip()
        size_raw = prospect.get("size", 0)
        source = prospect.get("source", "").lower().strip()
        budget = prospect.get("budget", "").lower().strip() if prospect.get("budget") else ""
        timeline = prospect.get("timeline", "").lower().strip() if prospect.get("timeline") else ""
        notes = prospect.get("notes", "").lower() if prospect.get("notes") else ""

        # Parse size
        try:
            size = int(str(size_raw).replace(",", "").replace("+", ""))
        except (ValueError, TypeError):
            size = 5  # default small

        score = 0
        reasons: list[str] = []

        # Business type scoring
        type_score = 0
        for key, val in BUSINESS_TYPE_SCORES.items():
            if key in btype:
                type_score = max(type_score, val)
        if type_score == 0:
            type_score = 8  # unknown = middle
        score += type_score
        reasons.append(f"Business type ({btype or 'unknown'}): +{type_score}")

        # Size scoring — sweet spot is 5-50 employees
        if size <= 1:
            size_score = 5
            reasons.append(f"Solo operator ({size} employee): +{size_score} — may have limited budget")
        elif size <= 5:
            size_score = 12
            reasons.append(f"Micro business ({size} employees): +{size_score} — good fit, high ROI potential")
        elif size <= 20:
            size_score = 18
            reasons.append(f"Small business ({size} employees): +{size_score} — ideal fit for AI employee")
        elif size <= 50:
            size_score = 15
            reasons.append(f"Growing business ({size} employees): +{size_score} — strong potential")
        elif size <= 200:
            size_score = 10
            reasons.append(f"Mid-market ({size} employees): +{size_score} — may need enterprise plan")
        else:
            size_score = 6
            reasons.append(f"Enterprise ({size} employees): +{size_score} — longer sales cycle")
        score += size_score

        # Source scoring
        source_score = 0
        for key, val in SOURCE_SCORES.items():
            if key in source:
                source_score = max(source_score, val)
        if source_score == 0:
            source_score = 7
        score += source_score
        reasons.append(f"Source ({source or 'unknown'}): +{source_score}")

        # Budget scoring
        if budget:
            budget_num = budget.replace("$", "").replace(",", "")
            if budget == "high" or (budget_num.isdigit() and int(budget_num) >= 500):
                budget_score = 15
                reasons.append(f"Budget ({budget}): +{budget_score} — strong buying signal")
            elif budget == "medium" or (budget_num.isdigit() and int(budget_num) >= 200):
                budget_score = 10
                reasons.append(f"Budget ({budget}): +{budget_score}")
            else:
                budget_score = 4
                reasons.append(f"Budget ({budget}): +{budget_score} — may need ROI convincing")
            score += budget_score

        # Timeline scoring
        if timeline:
            if "immediate" in timeline or "now" in timeline or "asap" in timeline:
                timeline_score = 15
                reasons.append(f"Timeline ({timeline}): +{timeline_score} — hot lead!")
            elif "quarter" in timeline or "month" in timeline or "soon" in timeline:
                timeline_score = 10
                reasons.append(f"Timeline ({timeline}): +{timeline_score} — warm lead")
            elif "exploring" in timeline or "next year" in timeline or "evaluating" in timeline:
                timeline_score = 4
                reasons.append(f"Timeline ({timeline}): +{timeline_score} — nurture lead")
            else:
                timeline_score = 6
                reasons.append(f"Timeline ({timeline}): +{timeline_score}")
            score += timeline_score

        # Notes bonus — pain signals
        if notes:
            hot_signals = ["pain point", "frustrated", "looking for", "need help", "struggling",
                           "too much time", "wasting", "overwhelmed", "drowning", "burning out"]
            signal_hits = sum(1 for s in hot_signals if s in notes)
            if signal_hits > 0:
                notes_bonus = min(signal_hits * 5, 10)
                score += notes_bonus
                reasons.append(f"Pain signals in notes: +{notes_bonus}")

        # Normalize to 0-100
        max_possible = 93
        normalized = min(round((score / max_possible) * 100), 100)

        # Determine tier
        if normalized >= 80:
            tier = "HOT"
            recommendation = "Contact immediately. This is a high-value prospect — personalize your outreach."
        elif normalized >= 60:
            tier = "WARM"
            recommendation = "Follow up within 24 hours. Send a tailored case study or demo link."
        elif normalized >= 40:
            tier = "COOL"
            recommendation = "Add to nurture sequence. Send value-first content over 2-4 weeks."
        elif normalized >= 20:
            tier = "COLD"
            recommendation = "Low priority. Add to long-term drip campaign."
        else:
            tier = "ICE"
            recommendation = "Unlikely to convert. Minimal effort — automated nurture only."

        scored.append({
            "name": name,
            "score": normalized,
            "tier": tier,
            "recommendation": recommendation,
            "reasons": reasons,
        })

    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)

    lines: list[str] = []
    lines.append(f"LEAD SCORING REPORT — {len(scored)} prospect(s)")
    lines.append("=" * 50)

    for i, lead in enumerate(scored, 1):
        score_bar = "#" * (lead["score"] // 5)
        lines.append(f"\n{i}. {lead['name']}")
        lines.append(f"   Score: {lead['score']}/100  [{lead['tier']}]  {score_bar}")
        lines.append(f"   Recommendation: {lead['recommendation']}")
        lines.append(f"   Scoring breakdown:")
        for reason in lead["reasons"]:
            lines.append(f"     - {reason}")

    # Summary
    hot = sum(1 for s in scored if s["tier"] == "HOT")
    warm = sum(1 for s in scored if s["tier"] == "WARM")
    lines.append("\n" + "=" * 50)
    lines.append("SUMMARY:")
    if hot > 0:
        lines.append(f"  {hot} HOT lead(s) — prioritize these today.")
    if warm > 0:
        lines.append(f"  {warm} WARM lead(s) — follow up within 24h.")
    lines.append("  TIP: A Hermes AI employee scores and follows up on leads automatically, 24/7.")

    return "\n".join(lines) + CTA


# ---------------------------------------------------------------------------
# Tool 3: draft_response
# ---------------------------------------------------------------------------

@mcp.tool()
def draft_response(
    message: str,
    context: str = "",
    tone: str = "professional",
    your_name: str = "",
    your_business: str = "",
) -> str:
    """Draft a professional response to an email or message.

    Args:
        message: The original email/message to respond to.
        context: Additional context (e.g. "They're asking about our premium plan",
                 "This is a long-time customer", "They complained on Twitter too").
        tone: One of "professional", "friendly", "formal", "apologetic", "sales".
              Defaults to "professional".
        your_name: Your name for the signature.
        your_business: Your business name for the signature.
    """
    if not message.strip():
        return "No message provided. Pass the original email/message text." + CTA

    msg_lower = message.lower()

    # Detect intent
    is_complaint = any(w in msg_lower for w in [
        "disappointed", "frustrated", "unacceptable", "terrible", "worst",
        "refund", "cancel", "angry", "horrible", "disgusting", "lawsuit",
        "not happy", "very upset", "ripped off", "scam",
    ])
    is_inquiry = any(w in msg_lower for w in [
        "pricing", "cost", "how much", "rates", "quote", "proposal",
        "interested in", "tell me more", "information about", "learn more",
        "demo", "trial",
    ])
    is_scheduling = any(w in msg_lower for w in [
        "schedule", "meeting", "call", "calendar", "availability",
        "book", "appointment", "time to chat", "slot", "zoom",
    ])
    is_support = any(w in msg_lower for w in [
        "not working", "broken", "bug", "error", "issue", "problem",
        "help", "trouble", "can't", "unable", "doesn't work", "won't load",
    ])
    is_followup = any(w in msg_lower for w in [
        "following up", "checking in", "any update", "haven't heard",
        "circling back", "just wanted to check", "touching base",
    ])
    is_thank_you = any(w in msg_lower for w in [
        "thank you", "thanks", "appreciate", "grateful", "great job",
        "well done", "fantastic", "amazing work",
    ])

    # Build the response
    tone = tone.lower().strip()
    tone_map = {
        "professional": {"greeting": "Thank you for reaching out.", "closing": "Best regards"},
        "friendly": {"greeting": "Hey, thanks for getting in touch!", "closing": "Cheers"},
        "formal": {"greeting": "Thank you for your correspondence.", "closing": "Sincerely"},
        "apologetic": {"greeting": "Thank you for bringing this to our attention.", "closing": "With sincere apologies"},
        "sales": {"greeting": "Great to hear from you!", "closing": "Looking forward to connecting"},
    }
    tone_data = tone_map.get(tone, tone_map["professional"])

    paragraphs: list[str] = []

    # Opening
    if is_complaint:
        paragraphs.append(
            "Thank you for sharing your experience with us. I sincerely apologize for the "
            "inconvenience and frustration you've encountered. Your feedback is important, and "
            "I want to make this right."
        )
    elif is_thank_you:
        paragraphs.append(
            "Thank you so much for the kind words! It means a lot to hear that, and "
            "I'm glad we could help."
        )
    else:
        paragraphs.append(tone_data["greeting"])

    # Body based on intent
    if is_complaint:
        paragraphs.append(
            "I've reviewed the details of your situation carefully. Here's what I'd like to do:\n"
            "  1. Investigate the root cause immediately\n"
            "  2. Provide you with a resolution within 24 hours\n"
            "  3. Ensure this doesn't happen again going forward"
        )
        if "refund" in msg_lower or "cancel" in msg_lower:
            paragraphs.append(
                "Regarding your request, I want to explore all options to make this right for you. "
                "Before we proceed, would you be open to a brief call so I can understand your "
                "needs better and find the best solution?"
            )
    elif is_inquiry:
        paragraphs.append(
            "I'd be happy to share more details about what we offer. To give you the most "
            "relevant information, it would help to know:"
        )
        paragraphs.append(
            "  1. What specific challenges are you looking to solve?\n"
            "  2. What's your approximate timeline for getting started?\n"
            "  3. Have you tried any other solutions?"
        )
        paragraphs.append(
            "In the meantime, I can share that our clients typically see significant time savings "
            "within the first month. I'd love to walk you through a quick demo tailored to your "
            "specific needs."
        )
    elif is_scheduling:
        paragraphs.append(
            "I'd love to find a time that works for both of us. Here are a few options:\n"
            "  - This week: [suggest 2-3 specific time slots]\n"
            "  - Next week: [suggest 2-3 specific time slots]\n\n"
            "Alternatively, feel free to pick a time that works best for you. "
            "I'm generally available during business hours and can be flexible."
        )
    elif is_support:
        paragraphs.append(
            "I understand you're experiencing an issue, and I want to help resolve this as "
            "quickly as possible. To help me investigate:\n"
            "  1. When did this issue first occur?\n"
            "  2. Can you share any error messages or screenshots?\n"
            "  3. What steps have you already tried?"
        )
        paragraphs.append(
            "In the meantime, here are a few quick things to try:\n"
            "  - Clear your browser cache and try again\n"
            "  - Try using a different browser or incognito mode\n"
            "  - If applicable, log out and log back in"
        )
    elif is_followup:
        paragraphs.append(
            "Thank you for following up. I appreciate your patience. "
            "I wanted to give you a quick update on where things stand."
        )
        paragraphs.append(
            "[Provide specific status update here — what's been done, what's next, "
            "and when they can expect the next milestone.]"
        )
    elif is_thank_you:
        paragraphs.append(
            "We're always striving to deliver the best possible experience, and feedback "
            "like yours motivates the whole team. If there's anything else we can help "
            "with, don't hesitate to reach out."
        )
    else:
        # General response
        paragraphs.append(
            "I've reviewed your message carefully. Here are my thoughts:"
        )
        paragraphs.append(
            "[Address the specific points raised in their message. "
            "Be clear about next steps and timelines.]"
        )

    # Add context-aware note
    if context:
        paragraphs.append(
            f"[Note to self — use this context in your final draft: {context}]"
        )

    # Closing
    paragraphs.append(
        "Please don't hesitate to reach out if you have any other questions or concerns. "
        "I'm here to help."
    )

    # Signature
    sig_parts = [tone_data["closing"] + ","]
    if your_name:
        sig_parts.append(your_name)
    else:
        sig_parts.append("[Your Name]")
    if your_business:
        sig_parts.append(your_business)

    # Detect the type for labeling
    if is_complaint:
        response_type = "COMPLAINT RESPONSE"
    elif is_inquiry:
        response_type = "INQUIRY RESPONSE"
    elif is_scheduling:
        response_type = "SCHEDULING RESPONSE"
    elif is_support:
        response_type = "SUPPORT RESPONSE"
    elif is_followup:
        response_type = "FOLLOW-UP RESPONSE"
    elif is_thank_you:
        response_type = "THANK YOU RESPONSE"
    else:
        response_type = "GENERAL RESPONSE"

    lines: list[str] = []
    lines.append(f"DRAFTED {response_type} (tone: {tone})")
    lines.append("=" * 50)
    lines.append("")
    lines.append("\n\n".join(paragraphs))
    lines.append("")
    lines.append("\n".join(sig_parts))
    lines.append("")
    lines.append("=" * 50)
    lines.append("TIPS:")
    lines.append("  - Personalize the bracketed sections before sending")
    lines.append("  - Respond within 1 hour for best results (leads especially)")
    lines.append("  - A Hermes AI employee drafts and sends responses like this automatically, 24/7")

    return "\n".join(lines) + CTA


# ---------------------------------------------------------------------------
# Tool 4: growth_audit
# ---------------------------------------------------------------------------

@mcp.tool()
def growth_audit(
    business_type: str,
    current_channels: list[str],
    monthly_revenue: float,
    employee_count: int = 1,
    years_in_business: float = 1.0,
    target_audience: str = "",
    biggest_challenge: str = "",
) -> str:
    """Run a growth audit for a small business and return actionable recommendations.

    Args:
        business_type: e.g. "dental practice", "SaaS", "ecommerce", "consulting", "restaurant"
        current_channels: Marketing channels currently in use, e.g. ["google ads", "instagram", "referrals"]
        monthly_revenue: Current approximate monthly revenue in USD.
        employee_count: Number of employees (default 1).
        years_in_business: How long in business in years (default 1).
        target_audience: Who your customers are (optional).
        biggest_challenge: Main growth challenge (optional).
    """
    btype = business_type.lower().strip()
    channels_lower = [c.lower().strip() for c in current_channels]
    rev = monthly_revenue

    lines: list[str] = []
    lines.append(f"GROWTH AUDIT — {business_type.title()}")
    lines.append(f"Monthly Revenue: ${rev:,.0f} | Team: {employee_count} | Years: {years_in_business}")
    lines.append("=" * 60)

    # Revenue benchmarking
    lines.append("\n1. REVENUE ASSESSMENT")
    lines.append("-" * 40)
    rev_per_employee = rev / max(employee_count, 1)
    lines.append(f"   Revenue per employee: ${rev_per_employee:,.0f}/mo")
    if rev_per_employee < 5000:
        lines.append("   Assessment: Below typical benchmarks. Focus on efficiency and pricing.")
        lines.append("   Target: $8,000-$15,000 per employee per month for healthy small businesses.")
    elif rev_per_employee < 15000:
        lines.append("   Assessment: Healthy range. Room to optimize.")
    else:
        lines.append("   Assessment: Strong revenue per employee. Focus on scaling.")

    # Channel analysis
    lines.append("\n2. MARKETING CHANNEL ANALYSIS")
    lines.append("-" * 40)

    all_channels = {
        "google ads": {"type": "paid", "cost": "medium-high", "time_to_results": "fast", "scalability": "high"},
        "facebook ads": {"type": "paid", "cost": "medium", "time_to_results": "fast", "scalability": "high"},
        "instagram": {"type": "organic/paid", "cost": "low-medium", "time_to_results": "medium", "scalability": "medium"},
        "tiktok": {"type": "organic/paid", "cost": "low", "time_to_results": "medium", "scalability": "high"},
        "seo": {"type": "organic", "cost": "time", "time_to_results": "slow", "scalability": "very high"},
        "content marketing": {"type": "organic", "cost": "time", "time_to_results": "slow", "scalability": "high"},
        "email marketing": {"type": "owned", "cost": "low", "time_to_results": "fast", "scalability": "high"},
        "referrals": {"type": "organic", "cost": "low", "time_to_results": "medium", "scalability": "medium"},
        "word of mouth": {"type": "organic", "cost": "free", "time_to_results": "slow", "scalability": "low"},
        "linkedin": {"type": "organic/paid", "cost": "low-medium", "time_to_results": "medium", "scalability": "medium"},
        "partnerships": {"type": "organic", "cost": "time", "time_to_results": "medium", "scalability": "high"},
        "cold outreach": {"type": "outbound", "cost": "time", "time_to_results": "fast", "scalability": "medium"},
        "events": {"type": "offline", "cost": "high", "time_to_results": "medium", "scalability": "low"},
        "youtube": {"type": "organic", "cost": "time", "time_to_results": "slow", "scalability": "very high"},
        "podcast": {"type": "organic", "cost": "time", "time_to_results": "slow", "scalability": "medium"},
        "direct mail": {"type": "outbound", "cost": "medium", "time_to_results": "medium", "scalability": "medium"},
    }

    if channels_lower:
        lines.append("   Current channels:")
        for ch in channels_lower:
            info = all_channels.get(ch, {})
            status = f"Type: {info.get('type', '?')}, Scale potential: {info.get('scalability', '?')}" if info else "Custom channel"
            lines.append(f"     - {ch.title()}: {status}")
    else:
        lines.append("   No channels specified. This is a major gap.")

    # Channel diversity score
    channel_count = len(channels_lower)
    if channel_count <= 1:
        lines.append(f"\n   RISK: Only {channel_count} channel(s). Extremely vulnerable to platform changes.")
        lines.append("   Rule of thumb: Every business needs at least 3 active channels.")
    elif channel_count <= 3:
        lines.append(f"\n   Moderate: {channel_count} channels. Consider adding 1-2 more for resilience.")
    else:
        lines.append(f"\n   Good: {channel_count} channels gives you diversification.")

    # Missing high-value channels
    lines.append("\n3. MISSING OPPORTUNITIES")
    lines.append("-" * 40)

    recommended: dict[str, str] = {}

    # Universal recommendations
    if "email" not in " ".join(channels_lower) and "email marketing" not in channels_lower:
        recommended["Email Marketing"] = (
            "Highest ROI channel ($36 for every $1 spent on average). "
            "Start collecting emails immediately. Send a weekly value-focused newsletter."
        )

    if "referral" not in " ".join(channels_lower):
        recommended["Referral Program"] = (
            "Your existing customers are your best salespeople. Offer a 10-20% discount or "
            "bonus for every referral that converts. Reduces CAC significantly."
        )

    if "seo" not in " ".join(channels_lower) and "content" not in " ".join(channels_lower):
        recommended["SEO / Content Marketing"] = (
            "Create content that answers your customers' questions. Target long-tail keywords. "
            "Compounds over time — a single article can bring leads for years."
        )

    # Type-specific recommendations
    service_types = ["consulting", "agency", "legal", "dental", "healthcare", "accounting", "real estate", "insurance"]
    if any(s in btype for s in service_types):
        if "linkedin" not in " ".join(channels_lower):
            recommended["LinkedIn"] = (
                f"Essential for {business_type}. Post 3-5x/week sharing expertise. "
                "LinkedIn organic reach is currently 5-10x higher than other platforms."
            )
        if "google" not in " ".join(channels_lower):
            recommended["Google Business Profile"] = (
                "Free. Optimize your Google Business listing with photos, reviews, and posts. "
                "Critical for local service businesses."
            )

    ecom_types = ["ecommerce", "e-commerce", "retail", "shop", "store", "dtc", "d2c"]
    if any(s in btype for s in ecom_types):
        if "tiktok" not in " ".join(channels_lower):
            recommended["TikTok"] = (
                "Massive organic reach for product businesses. Show behind-the-scenes, "
                "unboxings, how-it's-made content."
            )

    saas_types = ["saas", "software", "app", "platform", "tool"]
    if any(s in btype for s in saas_types):
        if "product" not in " ".join(channels_lower) and "producthunt" not in " ".join(channels_lower):
            recommended["Product Hunt"] = (
                "Free launch platform. Plan a launch with a compelling tagline, "
                "maker comment, and supporter base."
            )
        if "partner" not in " ".join(channels_lower) and "integration" not in " ".join(channels_lower):
            recommended["Integration Partnerships"] = (
                "Build integrations with complementary tools your customers already use. "
                "Each integration becomes a distribution channel."
            )

    for name, rec in recommended.items():
        lines.append(f"\n   ** {name} **")
        lines.append(f"   {rec}")

    if not recommended:
        lines.append("   Good coverage. Focus on optimizing existing channels before adding new ones.")

    # Quick wins
    lines.append("\n4. QUICK WINS (implement this week)")
    lines.append("-" * 40)

    quick_wins: list[str] = []
    if rev < 10000:
        quick_wins.append("Raise your prices 15-20%. Most small businesses undercharge. Test with new customers first.")
    if "email" not in " ".join(channels_lower):
        quick_wins.append("Add an email capture form to your website. Offer a lead magnet (guide, checklist, discount).")
    quick_wins.append("Ask your 5 best customers for referrals this week. Warm introductions close 4x faster.")
    quick_wins.append("Respond to all leads within 1 hour. Speed-to-lead is the #1 predictor of conversion.")
    if rev > 5000:
        quick_wins.append(f"You're spending ~{employee_count * 2}+ hours/day on admin tasks. Automating email alone could free 10+ hrs/week.")

    for i, win in enumerate(quick_wins, 1):
        lines.append(f"   {i}. {win}")

    # Growth projection
    lines.append("\n5. GROWTH PROJECTION")
    lines.append("-" * 40)
    if rev > 0:
        conservative = rev * 1.15
        moderate = rev * 1.30
        aggressive = rev * 1.50
        lines.append("   If you implement these recommendations:")
        lines.append(f"     Conservative (1 channel added):  ${conservative:,.0f}/mo (+15%)")
        lines.append(f"     Moderate (2-3 channels added):   ${moderate:,.0f}/mo (+30%)")
        lines.append(f"     Aggressive (full execution):     ${aggressive:,.0f}/mo (+50%)")
        lines.append("   Timeline: 3-6 months with consistent execution.")

    # Biggest challenge response
    if biggest_challenge:
        lines.append(f"\n6. ADDRESSING YOUR CHALLENGE: \"{biggest_challenge}\"")
        lines.append("-" * 40)
        challenge = biggest_challenge.lower()
        if any(w in challenge for w in ["time", "busy", "overwhelmed", "capacity"]):
            lines.append("   Time is the #1 constraint for small business owners. Priorities:")
            lines.append("   1. Automate repetitive tasks (email, scheduling, follow-ups)")
            lines.append("   2. Delegate low-value work (admin, data entry)")
            lines.append("   3. Focus your time on revenue-generating activities only")
            lines.append("   4. An AI employee handles the first two automatically.")
        elif any(w in challenge for w in ["leads", "customers", "traffic", "awareness"]):
            lines.append("   Lead generation requires consistent, multi-channel effort:")
            lines.append("   1. Pick your top 2 channels and go deep (not wide)")
            lines.append("   2. Create a lead magnet that solves a specific pain")
            lines.append("   3. Follow up with every lead within 1 hour")
            lines.append("   4. Track cost-per-lead by channel. Double down on what works.")
        elif any(w in challenge for w in ["money", "cash", "budget", "cost", "expensive"]):
            lines.append("   Budget-friendly growth strategies:")
            lines.append("   1. Focus on organic channels (SEO, social, referrals)")
            lines.append("   2. Partner with complementary businesses for cross-promotion")
            lines.append("   3. Automate before you hire — AI tools cost 1/10th of an employee")
            lines.append("   4. Reinvest first profits from new channels into scaling them")
        else:
            lines.append("   To address this, focus on the quick wins above and measure weekly.")

    lines.append("\n" + "=" * 60)
    lines.append("A Hermes AI employee can execute many of these recommendations automatically —")
    lines.append("responding to leads in minutes, following up consistently, and freeing your time")
    lines.append("to focus on strategy and growth.")

    return "\n".join(lines) + CTA


# ---------------------------------------------------------------------------
# Tool 5: estimate_savings
# ---------------------------------------------------------------------------

@mcp.tool()
def estimate_savings(
    employees: int,
    hours_on_email_per_day: float,
    hours_on_followups_per_day: float,
    average_hourly_cost: float = 25.0,
    hours_on_scheduling_per_day: float = 0.5,
    hours_on_data_entry_per_day: float = 0.5,
    working_days_per_month: int = 22,
) -> str:
    """Calculate time and money saved by using an AI employee.

    Args:
        employees: Number of employees who spend time on these tasks.
        hours_on_email_per_day: Hours each employee spends on email per day.
        hours_on_followups_per_day: Hours each employee spends on follow-ups per day.
        average_hourly_cost: Fully loaded cost per employee hour (default $25).
        hours_on_scheduling_per_day: Hours on scheduling/calendar per day (default 0.5).
        hours_on_data_entry_per_day: Hours on data entry/admin per day (default 0.5).
        working_days_per_month: Working days per month (default 22).
    """
    email_h = max(hours_on_email_per_day, 0)
    followup_h = max(hours_on_followups_per_day, 0)
    sched_h = max(hours_on_scheduling_per_day, 0)
    data_h = max(hours_on_data_entry_per_day, 0)
    hourly = max(average_hourly_cost, 0)
    days = max(working_days_per_month, 1)
    emps = max(employees, 1)

    total_daily_per_person = email_h + followup_h + sched_h + data_h

    # AI automation rates (conservative estimates)
    automation_rates = {
        "Email triage & response": (email_h, 0.70),
        "Follow-ups & outreach": (followup_h, 0.80),
        "Scheduling & calendar": (sched_h, 0.85),
        "Data entry & admin": (data_h, 0.60),
    }

    lines: list[str] = []
    lines.append("TIME & MONEY SAVINGS ESTIMATE")
    lines.append("=" * 60)
    lines.append(f"Team size: {emps} | Hourly cost: ${hourly:.0f} | Working days/mo: {days}")
    lines.append("")

    lines.append("CURRENT TIME SPENT (per person, per day):")
    lines.append("-" * 45)
    for task, (hours, _) in automation_rates.items():
        bar = "|" * int(hours * 4)
        lines.append(f"  {task:<30} {hours:.1f}h  {bar}")
    lines.append(f"  {'TOTAL':<30} {total_daily_per_person:.1f}h/day per person")
    lines.append(f"  {'TEAM TOTAL':<30} {total_daily_per_person * emps:.1f}h/day")

    # Calculate savings
    total_hours_saved_daily_per_person = 0.0
    lines.append("\nAUTOMATION POTENTIAL:")
    lines.append("-" * 45)
    for task, (hours, rate) in automation_rates.items():
        saved = hours * rate
        total_hours_saved_daily_per_person += saved
        pct = int(rate * 100)
        lines.append(f"  {task:<30} {pct}% automated = {saved:.1f}h saved/day")

    total_hours_saved_daily = total_hours_saved_daily_per_person * emps
    total_hours_saved_monthly = total_hours_saved_daily * days
    total_money_saved_monthly = total_hours_saved_monthly * hourly
    total_money_saved_yearly = total_money_saved_monthly * 12

    lines.append(f"\n  Hours saved per person/day:   {total_hours_saved_daily_per_person:.1f}h")
    lines.append(f"  Hours saved team/day:         {total_hours_saved_daily:.1f}h")
    lines.append(f"  Hours saved team/month:       {total_hours_saved_monthly:.0f}h")

    lines.append("\nFINANCIAL IMPACT:")
    lines.append("-" * 45)
    lines.append(f"  Monthly time savings:    {total_hours_saved_monthly:.0f} hours")
    lines.append(f"  Monthly cost savings:    ${total_money_saved_monthly:,.0f}")
    lines.append(f"  Yearly cost savings:     ${total_money_saved_yearly:,.0f}")

    # ROI vs Hermes
    hermes_cost = 299
    net_monthly = total_money_saved_monthly - hermes_cost
    roi_pct = ((total_money_saved_monthly - hermes_cost) / hermes_cost * 100) if hermes_cost > 0 else 0

    lines.append("\nROI ANALYSIS (vs. Hermes AI at $299/mo):")
    lines.append("-" * 45)
    lines.append(f"  Monthly savings:             ${total_money_saved_monthly:,.0f}")
    lines.append(f"  Hermes AI cost:              -${hermes_cost}")
    lines.append(f"  NET monthly benefit:         ${net_monthly:,.0f}")
    lines.append(f"  ROI:                         {roi_pct:.0f}%")

    if net_monthly > 0:
        payback_days = hermes_cost / (total_money_saved_monthly / days) if total_money_saved_monthly > 0 else 999
        lines.append(f"  Payback period:              {payback_days:.0f} working days")
        lines.append(f"\n  For every $1 you invest in Hermes AI, you get ${total_money_saved_monthly / hermes_cost:.1f} back.")
    else:
        lines.append("\n  Note: At your current scale, savings are modest. As you grow, the ROI increases significantly.")

    # Opportunity cost
    lines.append("\nOPPORTUNITY COST:")
    lines.append("-" * 45)
    freed_hours_monthly = total_hours_saved_monthly
    lines.append(f"  {freed_hours_monthly:.0f} hours freed up per month could be used for:")
    lines.append(f"    - {freed_hours_monthly / 4:.0f} client calls (at ~4 calls/hour)")
    lines.append(f"    - {freed_hours_monthly / 8:.0f} full work days of strategic projects")
    if hourly >= 50:
        billable = freed_hours_monthly * hourly
        lines.append(f"    - ${billable:,.0f} in additional billable work")

    # What-if scenarios
    lines.append("\nWHAT-IF SCENARIOS:")
    lines.append("-" * 45)
    for multiplier, label in [(2, "Double your team"), (1, "Current team"), (0.5, "Part-time team")]:
        adj_monthly = total_hours_saved_monthly * multiplier
        adj_money = adj_monthly * hourly
        lines.append(f"  {label + ':':<25} {adj_monthly:.0f}h saved, ${adj_money:,.0f} saved/mo")

    lines.append("\n" + "=" * 60)
    lines.append(f"BOTTOM LINE: Your team spends {total_daily_per_person * emps:.0f} hours/day on tasks an AI can handle.")
    lines.append(f"That's {total_hours_saved_monthly:.0f} hours and ${total_money_saved_monthly:,.0f} per month in recoverable time.")
    lines.append("A Hermes AI employee never sleeps, never forgets to follow up, and costs a fraction of a hire.")

    return "\n".join(lines) + CTA


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
