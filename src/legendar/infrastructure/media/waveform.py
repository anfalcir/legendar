"""Leitura validada do WAV normalizado compartilhada pelos adaptadores de IA."""

from __future__ import annotations

import math
import wave
from pathlib import Path
from typing import Any

from legendar.domain.entities.media import AudioAsset
from legendar.domain.errors.catalog import ModelError


def load_pcm_waveform(audio: AudioAsset) -> Any:
    """Lê WAV PCM signed 16-bit mono/16 kHz e retorna float32 em [-1, 1]."""
    if (
        audio.sample_rate_hz != 16_000
        or audio.channels != 1
        or audio.sample_format.lower() not in {"pcm_s16le", "s16"}
    ):
        raise ModelError(
            "O WhisperX recebeu áudio fora do contrato WAV PCM s16le mono/16 kHz."
        )

    try:
        with wave.open(str(Path(audio.path)), "rb") as source:
            if (
                source.getnchannels() != 1
                or source.getframerate() != 16_000
                or source.getsampwidth() != 2
                or source.getcomptype() != "NONE"
            ):
                raise ModelError(
                    "O arquivo de áudio não é WAV PCM signed 16-bit mono/16 kHz."
                )
            frame_count = source.getnframes()
            payload = source.readframes(frame_count)
    except (OSError, wave.Error) as exc:
        raise ModelError(f"Não foi possível ler o WAV normalizado: {exc}") from exc

    if frame_count < 1 or len(payload) != frame_count * 2:
        raise ModelError("O WAV normalizado está vazio ou truncado.")

    try:
        import numpy as np
    except ImportError as exc:
        raise ModelError("NumPy não está disponível no runtime de IA.") from exc

    waveform = np.frombuffer(payload, dtype="<i2").astype(np.float32) / 32768.0
    if (
        waveform.ndim != 1
        or waveform.size != frame_count
        or not math.isfinite(float(waveform.min()))
        or not math.isfinite(float(waveform.max()))
    ):
        raise ModelError("O WAV produziu uma forma de onda inválida.")
    return waveform
