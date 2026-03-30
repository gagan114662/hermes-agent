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

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states
(BUSINESS_NAME, INDUSTRY, PRODUCT, TARGET_CUSTOMER,
 TONE, AGENT_NAME, HOURS, GOALS, CONFIRM) = range(9)

QUESTIONS = [
    (BUSINESS_NAME, "What's your business name?"),
    (INDUSTRY, "What industry are you in? (e.g. coaching, e-commerce, real estate, consulting)"),
    (PRODUCT, "What do you sell? Describe it in 1-2 sentences."),
    (TARGET_CUSTOMER, "Who is your ideal customer? (e.g. small business owners, homeowners in NYC)"),
    (TONE, "What tone should your AI employee use? (professional / friendly / casual)"),
    (AGENT_NAME, "What would you like to name your AI employee? (e.g. Alex, Jordan, Sam)"),
    (HOURS, "What are your business hours? (e.g. Mon-Fri 9am-5pm EST, or 24/7)"),
    (GOALS, "Main goal: more leads, better customer support, or both?"),
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
    summary = (
        "✅ Here's your AI employee setup:\n\n"
        f"Business: {d.get('business_name')}\n"
        f"Industry: {d.get('industry')}\n"
        f"Product: {d.get('product')}\n"
        f"Target customer: {d.get('target_customer')}\n"
        f"Tone: {d.get('tone')}\n"
        f"Agent name: {d.get('agent_name')}\n"
        f"Hours: {d.get('hours')}\n"
        f"Goal: {d.get('goals')}\n\n"
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
    await update.message.reply_text(
        f"🚀 Launching {agent_name}... takes 3-5 minutes. I'll message you when ready!"
    )
    customer_id = str(uuid.uuid4())[:8]
    await _provision(update, context, customer_id)
    return ConversationHandler.END


async def _provision(update: Update, context: ContextTypes.DEFAULT_TYPE, customer_id: str) -> None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from scripts.provision_vm import provision_vm

    try:
        result = provision_vm(customer_id, dict(context.user_data))
        await update.message.reply_text(
            f"✅ {context.user_data.get('agent_name')} is live!\n\n"
            f"VM IP: {result['ip']}\n"
            f"Customer ID: {customer_id}\n\n"
            "Phone number and Telegram bot credentials will arrive in ~5 minutes."
        )
    except Exception as e:
        logger.error("Provisioning failed for %s: %s", customer_id, e)
        await update.message.reply_text("❌ Provisioning failed. Please contact support.")


def main() -> None:
    token = os.environ["ONBOARDING_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            state: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_answer)]
            for state in range(GOALS + 1)
        } | {CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_confirm)]},
        fallbacks=[CommandHandler("start", start)],
    )
    app.add_handler(conv)
    app.run_polling()


if __name__ == "__main__":
    main()
