# Home Assistant

Connect Hermes to a Home Assistant instance to control smart home devices via conversation.

---

## Prerequisites

- A running Home Assistant instance
- A Long-Lived Access Token

---

## Setup

### 1. Create a Long-Lived Access Token

1. Open Home Assistant → click your profile icon (bottom left)
2. Scroll to **Long-Lived Access Tokens**
3. Click **Create Token**, give it a name, copy it

### 2. Add credentials

```bash
# ~/.hermes/.env
HASS_TOKEN=eyJ0eXAiOiJKV1QiLCJhbGci...
HASS_URL=http://homeassistant.local:8123    # or your HA URL
```

### 3. Start the gateway or CLI

The Home Assistant tools are available in any toolset. Enable them:

```bash
hermes --toolset homeassistant
```

Or add to `cli-config.yaml`:

```yaml
toolsets:
  - homeassistant
```

---

## Available Tools

| Tool | Description |
|------|-------------|
| `ha_list_entities` | List entities (lights, switches, sensors, climate, etc.) |
| `ha_get_state` | Get detailed state of a single entity |
| `ha_list_services` | List available services/actions for a domain |
| `ha_call_service` | Call a service to control a device |

---

## Example Interactions

```
You: Turn off all the lights in the living room
Hermes: [calls ha_list_entities(domain="light"), ha_call_service("light.turn_off", ...)]
        Done — turned off 3 lights in the living room.

You: What's the temperature in the bedroom?
Hermes: [calls ha_get_state("sensor.bedroom_temperature")]
        The bedroom temperature is 21.5°C.

You: Set the thermostat to 72°F
Hermes: [calls ha_call_service("climate.set_temperature", ...)]
        Done — thermostat set to 72°F.
```

---

## Home Assistant as a Messaging Platform

Home Assistant can also function as a messaging channel — you can send and receive messages through Home Assistant's notification system:

```bash
HASS_TOKEN=...
HASS_URL=http://homeassistant.local:8123
```

---

## Troubleshooting

**"401 Unauthorized"**
- The token may have expired or been revoked. Create a new one.

**"Connection refused"**
- Check `HASS_URL` is reachable from the machine running Hermes
- If HA is on a different host, use its IP address instead of `homeassistant.local`
- Check HA is running: open a browser to the URL

**Entity not found**
- Run `ha_list_entities()` to see all available entity IDs
- Entity IDs are case-sensitive and include the domain: `light.living_room_ceiling`

**Service call fails**
- Run `ha_list_services(domain="light")` to see available service names and parameters
- Check HA logs for the specific error: **Settings → System → Logs**
