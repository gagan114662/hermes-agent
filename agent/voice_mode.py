"""
Voice mode: local microphone push-to-talk with Whisper transcription.

Records from mic until 2 seconds of silence, then transcribes via
OpenAI Whisper API. 16kHz mono PCM audio.

For Telegram voice messages, see gateway/platforms/telegram.py.

Dependencies: sounddevice, numpy (optional — fails gracefully if absent)
"""
from __future__ import annotations
import io
import logging
import os
import struct
import wave
from typing import Optional

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000       # 16kHz (Whisper optimal)
CHANNELS = 1              # Mono
SILENCE_THRESHOLD = 0.03  # RMS amplitude threshold for silence
SILENCE_DURATION = 2.0    # Seconds of silence to stop recording
CHUNK_DURATION = 0.1      # Seconds per audio chunk


def is_available() -> bool:
    """Return True if local voice recording is available (sounddevice installed + mic found)."""
    try:
        import sounddevice as sd
        import numpy as np
        devices = sd.query_devices()
        # Check for any input device
        for d in devices:
            if d.get('max_input_channels', 0) > 0:
                return True
        return False
    except Exception:
        return False


def record_until_silence(max_duration: float = 60.0) -> Optional[bytes]:
    """Record from mic until silence detected or max_duration reached.

    Returns WAV bytes ready for Whisper API, or None on failure.
    """
    try:
        import sounddevice as sd
        import numpy as np
    except ImportError:
        logger.error("[voice] sounddevice not installed. Run: pip install sounddevice numpy")
        return None

    logger.info("[voice] Recording... (speak now, silence stops recording)")

    frames = []
    silence_frames = 0
    silence_limit = int(SILENCE_DURATION / CHUNK_DURATION)
    max_frames = int(max_duration / CHUNK_DURATION)
    chunk_samples = int(SAMPLE_RATE * CHUNK_DURATION)

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype='float32') as stream:
            while len(frames) < max_frames:
                chunk, _ = stream.read(chunk_samples)
                frames.append(chunk.copy())

                # Check for silence
                rms = float(np.sqrt(np.mean(chunk ** 2)))
                if rms < SILENCE_THRESHOLD:
                    silence_frames += 1
                    if silence_frames >= silence_limit:
                        logger.info("[voice] Silence detected, stopping recording")
                        break
                else:
                    silence_frames = 0

        if not frames:
            return None

        # Convert to WAV bytes
        audio_data = np.concatenate(frames, axis=0)
        audio_int16 = (audio_data * 32767).astype('int16')

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_int16.tobytes())

        wav_bytes = wav_buffer.getvalue()
        logger.info("[voice] Recorded %.1fs of audio (%d bytes)", len(frames) * CHUNK_DURATION, len(wav_bytes))
        return wav_bytes

    except Exception as e:
        logger.error("[voice] Recording error: %s", e)
        return None


def transcribe(audio_bytes: bytes, api_key: Optional[str] = None) -> Optional[str]:
    """Transcribe audio bytes via OpenAI Whisper API.

    Args:
        audio_bytes: WAV file bytes
        api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)

    Returns:
        Transcribed text, or None on failure.
    """
    if not audio_bytes:
        return None

    _api_key = api_key or os.environ.get('OPENAI_API_KEY') or os.environ.get('ANTHROPIC_API_KEY')
    if not _api_key:
        logger.error("[voice] No API key found for Whisper transcription")
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=_api_key)

        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "recording.wav"

        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="en",
        )
        text = response.text.strip()
        logger.info("[voice] Transcribed: %.80s", text)
        return text

    except Exception as e:
        logger.error("[voice] Transcription failed: %s", e)
        return None


def record_and_transcribe(api_key: Optional[str] = None, max_duration: float = 60.0) -> Optional[str]:
    """Convenience function: record until silence then transcribe.

    Returns transcribed text or None.
    """
    audio = record_until_silence(max_duration=max_duration)
    if not audio:
        return None
    return transcribe(audio, api_key=api_key)


async def transcribe_ogg_bytes(ogg_bytes: bytes, api_key: Optional[str] = None) -> Optional[str]:
    """Transcribe OGG audio bytes from Telegram voice messages.

    Telegram sends voice messages as OGG/Opus files.
    Whisper accepts OGG directly.
    """
    if not ogg_bytes:
        return None

    _api_key = api_key or os.environ.get('OPENAI_API_KEY')
    if not _api_key:
        logger.error("[voice] No OPENAI_API_KEY for Whisper transcription")
        return None

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=_api_key)

        audio_file = io.BytesIO(ogg_bytes)
        audio_file.name = "voice_message.ogg"

        response = await client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )
        text = response.text.strip()
        logger.info("[voice] Telegram voice transcribed: %.80s", text)
        return text

    except Exception as e:
        logger.error("[voice] Telegram voice transcription failed: %s", e)
        return None


if __name__ == "__main__":
    # Test mode: record and print transcription
    import sys
    print("Voice mode test — speak into your mic. Recording starts now.")
    print(f"Mic available: {is_available()}")

    if not is_available():
        print("No microphone found. Install sounddevice: pip install sounddevice numpy")
        sys.exit(1)

    result = record_and_transcribe()
    if result:
        print(f"\nTranscription: {result}")
    else:
        print("\nTranscription failed.")
