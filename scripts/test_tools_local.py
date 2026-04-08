#!/usr/bin/env python3
"""
Local tool smoke test — tests all new SMB tools against real APIs.
No Docker needed. Uses cloud free tiers or self-hosted endpoints.

Usage:
    # Set env vars first, then run:
    python scripts/test_tools_local.py

    # Test only specific tools:
    python scripts/test_tools_local.py --only booking
    python scripts/test_tools_local.py --only whatsapp invoicing
"""
import argparse
import os
import sys

# Add repo root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = "✅"
FAIL = "❌"
SKIP = "⏭ "


def section(title: str):
    print(f"\n{'─' * 50}")
    print(f"  {title}")
    print(f"{'─' * 50}")


def check(name: str, fn, *args, expect_contains: str = None, skip_if_missing: list = None):
    """Run a tool function and print pass/fail."""
    # Skip if env vars missing
    if skip_if_missing:
        missing = [v for v in skip_if_missing if not os.environ.get(v)]
        if missing:
            print(f"  {SKIP} {name} — skipped (missing: {', '.join(missing)})")
            return

    try:
        result = fn(*args)
        if result.startswith("Error"):
            print(f"  {FAIL} {name}")
            print(f"       {result[:120]}")
        elif expect_contains and expect_contains.lower() not in result.lower():
            print(f"  {FAIL} {name} — unexpected response")
            print(f"       {result[:120]}")
        else:
            print(f"  {PASS} {name}")
            # Show first line of result
            first_line = result.split("\n")[0]
            print(f"       {first_line[:100]}")
    except Exception as e:
        print(f"  {FAIL} {name} — exception: {e}")


def test_booking():
    section("📅 Booking — Cal.com")
    print("  Needs: CALCOM_API_KEY (free at cal.com/settings/developer/api-keys)")
    from tools.booking_tool import booking_list_upcoming, booking_list_slots
    import datetime
    today = datetime.date.today().isoformat()
    check("booking_list_upcoming", booking_list_upcoming,
          skip_if_missing=["CALCOM_API_KEY"])
    check("booking_list_slots (today)", booking_list_slots, today,
          skip_if_missing=["CALCOM_API_KEY"])


def test_easy_appointments():
    section("📅 Booking — Easy!Appointments (self-hosted)")
    print("  Needs: EASYAPP_URL, EASYAPP_USERNAME, EASYAPP_PASSWORD")
    from tools.easy_appointments_tool import easyapp_list_services, easyapp_list_providers, easyapp_list_appointments
    check("easyapp_list_services", easyapp_list_services,
          skip_if_missing=["EASYAPP_URL"])
    check("easyapp_list_providers", easyapp_list_providers,
          skip_if_missing=["EASYAPP_URL"])
    check("easyapp_list_appointments", easyapp_list_appointments,
          skip_if_missing=["EASYAPP_URL"])


def test_invoicing():
    section("🧾 Invoicing — Crater")
    print("  Needs: CRATER_BASE_URL, CRATER_API_TOKEN, CRATER_COMPANY_ID")
    print("  Free self-hosted: docker run -d -p 8080:80 crater-app/crater")
    print("  Or hosted trial: craterapp.com")
    from tools.invoicing_tool import invoice_list
    check("invoice_list (UNPAID)", invoice_list, "UNPAID",
          skip_if_missing=["CRATER_BASE_URL", "CRATER_API_TOKEN"])
    check("invoice_list (PAID)", invoice_list, "PAID",
          skip_if_missing=["CRATER_BASE_URL", "CRATER_API_TOKEN"])


def test_email_marketing():
    section("📧 Email Marketing — Mautic")
    print("  Needs: MAUTIC_BASE_URL, MAUTIC_USERNAME, MAUTIC_PASSWORD")
    print("  Free cloud: mautic.com (hosted trial)")
    from tools.email_marketing_tool import email_list_campaigns, email_list_emails
    check("email_list_campaigns", email_list_campaigns,
          skip_if_missing=["MAUTIC_BASE_URL"])
    check("email_list_emails", email_list_emails,
          skip_if_missing=["MAUTIC_BASE_URL"])


def test_whatsapp_evolution():
    section("💚 WhatsApp — Evolution API (self-hosted, no Twilio)")
    print("  Needs: EVOLUTION_API_URL, EVOLUTION_API_KEY, EVOLUTION_INSTANCE")
    print("  Cloud option: evolution-api.com (managed hosting)")
    from tools.whatsapp_evolution_tool import wa_instance_status, wa_get_chats
    check("wa_instance_status", wa_instance_status,
          skip_if_missing=["EVOLUTION_API_URL", "EVOLUTION_API_KEY"])
    check("wa_get_chats", wa_get_chats,
          skip_if_missing=["EVOLUTION_API_URL", "EVOLUTION_API_KEY"])


def test_whatsapp_twilio():
    section("💬 WhatsApp — Twilio (paid, but instant)")
    print("  Needs: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER")
    print("  Free trial: twilio.com ($15 credit, no card)")
    from tools.twilio_tool import whatsapp_send_tool
    test_number = os.environ.get("TEST_PHONE_NUMBER", "")
    if not test_number:
        print(f"  {SKIP} whatsapp_send — set TEST_PHONE_NUMBER to your number")
        return
    check("whatsapp_send (to yourself)", whatsapp_send_tool, test_number, "Hello from AI Employee test 👋",
          skip_if_missing=["TWILIO_ACCOUNT_SID", "TWILIO_WHATSAPP_NUMBER"])


def test_sms():
    section("💬 SMS — Twilio or Android Gateway")
    print("  Twilio: set TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN + TWILIO_PHONE_NUMBER")
    print("  Android: set ANDROID_SMS_GATEWAY_URL + ANDROID_SMS_GATEWAY_PASSWORD")
    from tools.twilio_tool import sms_send_tool
    from tools.sms_android_tool import android_sms_health
    test_number = os.environ.get("TEST_PHONE_NUMBER", "")
    if test_number:
        check("sms_send via Twilio (to yourself)", sms_send_tool, test_number, "AI Employee SMS test",
              skip_if_missing=["TWILIO_ACCOUNT_SID", "TWILIO_PHONE_NUMBER"])
    else:
        print(f"  {SKIP} sms_send — set TEST_PHONE_NUMBER to your number")
    check("android_sms_health", android_sms_health,
          skip_if_missing=["ANDROID_SMS_GATEWAY_URL"])


def test_voice():
    section("📞 Voice — Fonoster (self-hosted, replaces Vapi)")
    print("  Needs: FONOSTER_ACCESS_KEY_ID, FONOSTER_ACCESS_KEY_SECRET")
    print("  Free cloud: console.fonoster.com")
    from tools.fonoster_tool import fonoster_number_list, fonoster_app_list
    check("fonoster_number_list", fonoster_number_list,
          skip_if_missing=["FONOSTER_ACCESS_KEY_ID"])
    check("fonoster_app_list", fonoster_app_list,
          skip_if_missing=["FONOSTER_ACCESS_KEY_ID"])


SUITES = {
    "booking": test_booking,
    "easy-appointments": test_easy_appointments,
    "invoicing": test_invoicing,
    "email-marketing": test_email_marketing,
    "whatsapp": test_whatsapp_evolution,
    "whatsapp-twilio": test_whatsapp_twilio,
    "sms": test_sms,
    "voice": test_voice,
}

ALL_SUITES = list(SUITES.values())


def main():
    parser = argparse.ArgumentParser(description="Test SMB tools locally")
    parser.add_argument("--only", nargs="+", choices=list(SUITES.keys()),
                        help="Only run specific test suites")
    args = parser.parse_args()

    print("\n🤖 AI Employee — Local Tool Test")
    print("=" * 50)
    print("Skipped tests = env var not set (that's fine for now)")

    suites = [SUITES[s] for s in args.only] if args.only else ALL_SUITES
    for suite in suites:
        suite()

    print(f"\n{'=' * 50}")
    print("Done. Set missing env vars in ~/.hermes/.env to activate more tools.")
    print("Run with --only <suite> to test one area at a time.\n")


if __name__ == "__main__":
    main()
