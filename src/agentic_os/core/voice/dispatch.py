"""
Phase 5 — Command Deck Audio/Haptic & Voice Dispatch Pipeline.

Spec §15/§16 remediation: this engine previously fabricated transcripts
(confidence 0.99), a fake "All systems responsive and healthy" spoken
response and invented 145ms latency. No audio processing exists. It now
records the request and reports honestly that nothing was transcribed or
dispatched.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VoiceTranscriptionResult:
    transcript_id: str
    transcribed_text: str
    confidence: float
    dispatched_action: str
    spoken_response: str
    latency_ms: float
    created_at: float = field(default_factory=time.time)


class VoiceDispatchEngine:
    """Records voice dispatch requests. Does NOT transcribe or dispatch."""

    def __init__(self) -> None:
        # No seeded transcript history — empty until real ASR is wired.
        self._transcripts: list[VoiceTranscriptionResult] = []

    def process_voice_audio(self, custom_prompt: str = "") -> VoiceTranscriptionResult:
        tid = f"voice-{uuid.uuid4().hex[:6]}"
        text = custom_prompt.strip()
        res = VoiceTranscriptionResult(
            transcript_id=tid,
            transcribed_text=text,
            confidence=0.0,
            dispatched_action="not_executed",
            spoken_response=(
                "Voice input recorded but NOT processed: no speech-to-text "
                "engine is wired to this dispatcher. Nothing was transcribed "
                "or dispatched."
            ),
            latency_ms=0.0,
        )
        self._transcripts.insert(0, res)
        return res

    def get_transcripts(self) -> list[dict[str, Any]]:
        return [t.__dict__ for t in self._transcripts]


voice_engine = VoiceDispatchEngine()
