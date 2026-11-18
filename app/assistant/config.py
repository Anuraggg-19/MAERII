from dataclasses import dataclass, field
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LANGUAGES = {"en-IN": "English", "hi-IN": "हिन्दी", "mr-IN": "मराठी"}
VERSION = "assistant-2-readable"

def flag(name, default=False):
    return os.getenv(name, str(default)).lower() in {"true", "1", "yes"}

def number(name, default):
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default

@dataclass
class Settings:
    enabled: bool = field(default_factory=lambda: flag("ASSISTANT_ENABLED"))
    trial_confirmed: bool = field(default_factory=lambda: flag("ASSISTANT_TRIAL_CONFIRMED"))
    gemini_key: str = field(default_factory=lambda: os.getenv("ASSISTANT_GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY", ""))
    sarvam_key: str = field(default_factory=lambda: os.getenv("SARVAM_API_KEY", ""))
    gemini_model: str = field(default_factory=lambda: os.getenv("ASSISTANT_GEMINI_MODEL", "gemini-3.5-flash-lite"))
    translation_model: str = "sarvam-translate:v1"
    speech_model: str = field(default_factory=lambda: os.getenv("ASSISTANT_SPEECH_MODEL", "bulbul:v3"))
    voice: str = field(default_factory=lambda: os.getenv("ASSISTANT_SPEECH_VOICE", "shubh"))
    secure_cookie: bool = field(default_factory=lambda: flag("ASSISTANT_SECURE_COOKIE"))
    daily_limit: int = field(default_factory=lambda: number("ASSISTANT_DAILY_GENERATIONS", 20))
    global_daily_calls: int = field(default_factory=lambda: number("ASSISTANT_TRIAL_DAILY_CALLS", 100))
    daily_sarvam_chars: int = field(default_factory=lambda: number("ASSISTANT_TRIAL_DAILY_CHARACTERS", 10000))
    audio_dir: Path = field(default_factory=lambda: ROOT / "data" / "assistant_audio")
    session_ttl: int = 86400
    answer_ttl: int = 86400
    output_tokens: int = 512
    timeout: int = 25

    def ready(self, provider):
        return self.enabled and self.trial_confirmed and bool(self.gemini_key if provider == "gemini" else self.sarvam_key)

    def speech_unavailable_reason(self):
        if not self.enabled:
            return "disabled"
        if not self.trial_confirmed:
            return "trial_not_confirmed"
        if not self.sarvam_key:
            return "key_missing"
        return None
