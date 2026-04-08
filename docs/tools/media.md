# Media & Voice Tools

## Text to Speech (`tts` toolset)

Convert text to audio using ElevenLabs:

```
text_to_speech(text="Hello! Your order is ready.", voice_id="rachel")
```

Requires `ELEVENLABS_API_KEY`.

The returned `MEDIA:` path is delivered as audio on messaging platforms that support it (Telegram, WhatsApp, Signal).

## Image Generation (`image_gen` toolset)

```
image_generate(prompt="A professional headshot of a friendly AI assistant")
```

Requires `FAL_API_KEY` (for FLUX 2 Pro via fal.ai).

```
google_image_generate(prompt="A minimalist logo for a tech company")
```

Requires `GOOGLE_API_KEY`.

## Vision Analysis (`vision` toolset)

Analyze images using AI vision:

```
vision_analyze(image_path="/tmp/chart.png", question="What does this chart show?")
```

Works with any LLM provider that supports vision (Claude, GPT-4o, Gemini).

## Voice Calls (`voice` toolset)

### Vapi (cloud AI voice)

```
vapi_call(phone_number="+1XXXXXXXXXX", message="Hello! Calling to confirm your appointment.")
vapi_calls()   # list recent calls
```

Requires `VAPI_API_KEY` and a Vapi assistant configured at [vapi.ai](https://vapi.ai).

### Fonoster (self-hosted)

```
fonoster_call_make(number="+1XXXXXXXXXX", app_id="my-app")
fonoster_call_list()
fonoster_number_list()
```

Requires Fonoster credentials.

## Avatar Video (`avatar` toolset)

Generate a talking-head video using HeyGen:

```
heygen_video(script="Hello! Welcome to our service.", avatar_id="my-avatar")
```

Requires `HEYGEN_API_KEY`.

## Voice Transcription (Automatic)

When the gateway receives a voice message, it automatically transcribes it using OpenAI Whisper if `OPENAI_API_KEY` is set and `stt.enabled: true` in `cli-config.yaml`.

Configure in `cli-config.yaml`:

```yaml
stt:
  enabled: true
  model: "whisper-1"   # or gpt-4o-transcribe for higher accuracy
```
