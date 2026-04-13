#!/usr/bin/env python3
"""
Onboarding bot — runs on the control plane.
Interviews new customers over Telegram and provisions their VM.

Env vars:
    ONBOARDING_BOT_TOKEN  — Telegram bot token for onboarding
    DO_API_TOKEN          — DigitalOcean API token
"""
import logging
import os
import sys
import uuid
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states
(BUSINESS_NAME, INDUSTRY, PRODUCT, TARGET_CUSTOMER,
 TONE, AGENT_NAME, HOURS, GOALS, WEBSITE_URL, CONFIRM) = range(10)

QUESTIONS = [
    (BUSINESS_NAME, "What's your business name?"),
    (INDUSTRY, "What industry are you in? (e.g. coaching, e-commerce, real estate, consulting)"),
    (PRODUCT, "What do you sell? Describe it in 1-2 sentences."),
    (TARGET_CUSTOMER, "Who is your ideal customer? (e.g. small business owners, homeowners in NYC)"),
    (TONE, "What tone should your AI employee use? (professional / friendly / casual)"),
    (AGENT_NAME, "What would you like to name your AI employee? (e.g. Alex, Jordan, Sam)"),
    (HOURS, "What are your business hours? (e.g. Mon-Fri 9am-5pm EST, or 24/7)"),
    (GOALS, "Main goal: more leads, better customer support, or both?"),
    (WEBSITE_URL, "What's your website URL? (e.g. https://example.com, or skip if you don't have one)"),
]

STATE_KEYS = {
    BUSINESS_NAME: "business_name",
    INDUSTRY: "industry",
    PRODUCT: "product",
    TARGET_CUSTOMER: "target_customer",
    TONE: "tone",
    AGENT_NAME: "agent_name",
    HOURS: "hours",
    GOALS: "goals",
    WEBSITE_URL: "website_url",
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    context.user_data["_state"] = BUSINESS_NAME
    await update.message.reply_text(
        "👋 Welcome! I'm setting up your AI employee.\n\n"
        "I'll ask you 8 quick questions — takes about 2 minutes.\n\n"
        + QUESTIONS[0][1]
    )
    return BUSINESS_NAME


async def collect_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    current_state = context.user_data.get("_state", BUSINESS_NAME)
    key = STATE_KEYS.get(current_state)
    if key:
        context.user_data[key] = update.message.text.strip()

    next_state = current_state + 1
    if next_state < len(QUESTIONS):
        context.user_data["_state"] = next_state
        await update.message.reply_text(QUESTIONS[next_state][1])
        return next_state

    return await show_confirm(update, context)


async def show_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    d = context.user_data
    website_info = f"Website: {d.get('website_url')}\n" if d.get('website_url') else ""
    summary = (
        "✅ Here's your AI employee setup:\n\n"
        f"Business: {d.get('business_name')}\n"
        f"Industry: {d.get('industry')}\n"
        f"Product: {d.get('product')}\n"
        f"Target customer: {d.get('target_customer')}\n"
        f"Tone: {d.get('tone')}\n"
        f"Agent name: {d.get('agent_name')}\n"
        f"Hours: {d.get('hours')}\n"
        f"Goal: {d.get('goals')}\n"
        f"{website_info}\n"
        "Type yes to confirm and launch, or no to start over."
    )
    await update.message.reply_text(summary)
    return CONFIRM


async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().lower()
    if text != "yes":
        await update.message.reply_text("No problem! Let's start over.")
        return await start(update, context)

    agent_name = context.user_data.get("agent_name", "Alex")

    # Write business profile for the AI employee identity
    profile_path = _write_business_profile(context.user_data)
    website_url = context.user_data.get("website_url", "").strip()

    await update.message.reply_text(
        f"🚀 Launching {agent_name}... takes 3-5 minutes. I'll message you when ready!"
    )
    customer_id = str(uuid.uuid4())[:8]
    await _provision(update, context, customer_id, profile_path, website_url)
    return ConversationHandler.END


def _write_business_profile(user_data: dict) -> Path:
    """Write the business profile to ~/.hermes/business_profile.json and return the path."""
    import json
    from pathlib import Path
    profile = {
        "business_name": user_data.get("business_name", ""),
        "industry": user_data.get("industry", ""),
        "agent_name": user_data.get("agent_name", "Alex"),
        "tone": user_data.get("tone", "friendly"),
        "product": user_data.get("product", ""),
        "target_customer": user_data.get("target_customer", ""),
        "hours": user_data.get("hours", ""),
        "goal": user_data.get("goals", ""),
    }
    profile_path = Path.home() / ".hermes" / "business_profile.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(profile, indent=2))
    logger.info("Business profile written to %s", profile_path)
    return profile_path


async def _provision(
    update: Update, context: ContextTypes.DEFAULT_TYPE, customer_id: str,
    profile_path: Path, website_url: str
) -> None:
    from pathlib import Path as PathlibPath
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from scripts.provision_vm import provision_vm

    await update.message.reply_text("⏳ Setting up your AI employee... this takes about 2 minutes.")
    try:
        result = provision_vm(customer_id, dict(context.user_data))
        ip = result.get("ip", "unknown")
        phone = result.get("vapi_phone_number", "being set up")
        await update.message.reply_text(
            f"✅ Your AI employee is live!\n\n"
            f"📞 Phone: {phone}\n"
            f"💬 Telegram: @hermes114bot\n\n"
            f"It will start working within 5 minutes."
        )

        # Set up team and enrich profile with website analysis
        await update.message.reply_text("🤖 Setting up your team...")
        try:
            project_dir = PathlibPath.home() / ".hermes" / f"project_{customer_id}"
            team_summary = await setup_team_from_onboarding(
                website_url=website_url,
                business_profile_path=profile_path,
                project_dir=project_dir
            )
            await update.message.reply_text(
                f"✅ Team setup complete!\n\n{team_summary['summary']}"
            )
            logger.info("Team setup completed: %s", team_summary)
        except Exception as team_error:
            logger.warning("Team setup failed: %s. Continuing with VM provisioning.", team_error)
            await update.message.reply_text(
                "⚠️ Team setup encountered an issue, but your AI employee is still running. "
                "We'll set it up manually."
            )

        # Notify owner
        owner_id = os.environ.get("TELEGRAM_OWNER_ID", "")
        if owner_id:
            await context.bot.send_message(
                chat_id=owner_id,
                text=f"🎉 New customer live!\nID: {customer_id}\nIP: {ip}\nPhone: {phone}\nBusiness: {context.user_data.get('business_name', '?')}",
            )
        # Notify control plane
        control_plane_url = os.environ.get("CONTROL_PLANE_URL", "")
        if control_plane_url:
            import urllib.request as _ureq, json as _json
            payload = _json.dumps({
                "customer_id": customer_id,
                "ip": ip,
                "phone": phone,
                "telegram_chat_id": str(update.effective_chat.id),
            }).encode()
            req = _ureq.Request(
                f"{control_plane_url}/internal/customer-ready",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                _ureq.urlopen(req, timeout=10)
            except Exception:
                pass  # Non-fatal
    except Exception as e:
        logger.error("Provisioning failed for %s: %s", customer_id, e)
        await update.message.reply_text(
            "⚠️ Setup hit a snag. Our team has been notified and will fix it within 1 hour. "
            "You will not be charged if we cannot deliver."
        )
        owner_id = os.environ.get("TELEGRAM_OWNER_ID", "")
        if owner_id:
            await context.bot.send_message(
                chat_id=owner_id,
                text=f"🚨 Provisioning FAILED\nCustomer: {customer_id}\nError: {e}\nData: {dict(context.user_data)}",
            )


async def setup_team_from_onboarding(
    website_url: str, business_profile_path: Path, project_dir: Path = None
) -> dict:
    """Set up team from onboarding data.

    Chains together:
    1. Website analysis (if URL provided) to enrich the profile
    2. Team provisioning (employee creation)
    3. Henry PM creation

    Parameters
    ----------
    website_url : str
        Business website URL for analysis (may be empty string).
    business_profile_path : Path
        Path to business_profile.json.
    project_dir : Path
        Project working directory. Defaults to ~/.hermes/project.

    Returns
    -------
    dict
        Summary of team provisioning with keys:
        - enriched: bool (True if website analysis was performed)
        - business_name: str
        - employee_count: int
        - employees: list
        - henry_included: bool
        - summary: str
    """
    import json
    from pathlib import Path as PathlibPath

    business_profile_path = PathlibPath(business_profile_path).expanduser()
    if project_dir is None:
        project_dir = PathlibPath.home() / ".hermes" / "project"
    else:
        project_dir = PathlibPath(project_dir).expanduser()

    project_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Analyze website to enrich profile (if URL provided)
    enriched = False
    if website_url and website_url.strip():
        try:
            from scripts.website_analyzer import analyze_website, _save_profile_to_json
            logger.info("Analyzing website: %s", website_url)
            enriched_profile = await analyze_website(website_url)
            # Merge with existing profile
            existing_profile = json.loads(business_profile_path.read_text())
            existing_profile.update({
                "industry": enriched_profile.industry,
                "description": enriched_profile.description,
                "services": enriched_profile.services,
                "competitors": enriched_profile.competitors,
                "team_size_estimate": enriched_profile.team_size_estimate,
                "social_media": enriched_profile.social_media,
                "contact_info": enriched_profile.contact_info,
                "pain_points": enriched_profile.pain_points,
                "recommended_employees": enriched_profile.recommended_employees,
            })
            business_profile_path.write_text(json.dumps(existing_profile, indent=2))
            enriched = True
            logger.info("Profile enriched with website analysis")
        except Exception as e:
            logger.warning("Website analysis failed: %s. Proceeding without enrichment.", e)

    # Step 2: Provision team from profile
    try:
        from harness.team_factory import provision_team
        logger.info("Provisioning team from profile")
        provision_result = provision_team(
            profile_path=business_profile_path,
            project_dir=project_dir
        )
        provision_result["enriched"] = enriched
        return provision_result
    except Exception as e:
        logger.error("Team provisioning failed: %s", e)
        raise


def main() -> None:
    token = os.environ["ONBOARDING_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            state: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_answer)]
            for state in range(WEBSITE_URL + 1)
        } | {CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_confirm)]},
        fallbacks=[CommandHandler("start", start)],
    )
    app.add_handler(conv)
    app.run_polling()


if __name__ == "__main__":
    main()
