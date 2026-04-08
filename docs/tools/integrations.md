# Integrations

Third-party service integrations available as toolsets.

## Booking

### Cal.com (`booking` toolset)

Requires `CALCOM_API_KEY`.

```
booking_create_link(event_type_id=123)
booking_list_slots(date="2025-04-15", event_type_id=123)
booking_list_upcoming()
booking_reschedule(booking_id="abc", new_time="2025-04-16T10:00:00")
booking_cancel(booking_id="abc", reason="Client requested")
```

### Easy!Appointments (`easy-appointments` toolset)

Self-hosted booking system. Requires `EASYAPP_URL`, `EASYAPP_API_KEY`.

## Invoicing

### Invoice Ninja (`invoicing` toolset)

Requires `INVOICE_NINJA_URL`, `INVOICE_NINJA_API_KEY`.

```
estimate_create(client_id="abc", items=[{"name": "Consulting", "quantity": 10, "price": 150}])
invoice_create(client_id="abc", items=[...])
invoice_list(status="UNPAID")
invoice_send(invoice_id="abc")
payment_record(invoice_id="abc", amount=1500)
```

## Email Marketing

### Mautic (`email-marketing` toolset)

Requires `MAUTIC_URL`, `MAUTIC_USERNAME`, `MAUTIC_PASSWORD`.

```
email_contact_add(email="user@example.com", first_name="Alice")
email_campaign_send(campaign_id=5, contacts=["user@example.com"])
email_broadcast_send(email_id=3)
email_stats(email_id=3)
```

## Social Media

### Buffer (`social_media` toolset)

Requires `BUFFER_CLIENT_ID`, `BUFFER_CLIENT_SECRET`, `BUFFER_ACCESS_TOKEN`.

```
social_profiles()
social_post(text="Check out our latest update!", profile_ids=["abc"], schedule_at="2025-04-15T09:00:00")
social_queue()
social_analytics()
```

### Direct APIs (`social_media_direct` toolset)

Post directly without Buffer:

```
twitter_post(text="Hello world!", image_path="/tmp/image.png")    # requires TWITTER_API_KEY etc.
linkedin_post(text="Excited to announce...", visibility="PUBLIC") # requires LINKEDIN_ACCESS_TOKEN
social_content(topic="AI productivity tools", platforms=["twitter", "linkedin"])
social_post_auto(text="...", platforms=["twitter", "linkedin"])   # auto-routes
```

## Home Automation

### Home Assistant (`homeassistant` toolset)

See [Home Assistant platform guide](../platforms/homeassistant.md).

## Smart Home Devices

### Android SMS Gateway (`sms-android` toolset)

Use an Android phone as a zero-cost SMS gateway. Requires the [Android SMS Gateway](https://github.com/android-sms-gateway) app.

```
android_sms_health()
android_sms_send(phone_number="+1XXXXXXXXXX", message="Hello!")
android_sms_send_bulk(phone_numbers=["+1XXX", "+1YYY"], message="Update!")
android_sms_status(message_id="abc123")
```

## Honcho (Cross-Session Memory)

Requires `HONCHO_API_KEY` and `pip install honcho-ai`.

```
honcho_profile()            # get user's peer card
honcho_context(query="What does Alice prefer for meeting times?")
honcho_search(query="project deadlines")
honcho_conclude(content="User prefers async communication")
```

## Mixture of Agents (`moa` toolset)

Route hard problems through multiple frontier LLMs for consensus:

```
mixture_of_agents(prompt="What's the best way to architect a multi-tenant SaaS?")
```

Requires multiple LLM API keys.

## MCP AutoConfig (`mcp_autoconfig` toolset)

Auto-detect credentials from macOS Keychain and configure MCP servers:

```
mcp_autoconfig()
```

macOS only.

## RL Training (`rl` toolset)

Control local reinforcement learning training runs:

```
rl_list_environments()
rl_select_environment(name="my-env")
rl_start_training()
rl_check_status(run_id="abc")
rl_stop_training(run_id="abc")
```
