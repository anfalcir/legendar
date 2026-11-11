from __future__ import annotations

import io
import wave
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from scripts.phase5_alignment_smoke import _write_audio


def _float_wav(samples: np.ndarray) -> bytes:
    stream = io.BytesIO()
    sf.write(
        stream,
        samples.astype(np.float32),
        samplerate=16_000,
        format="WAV",
        subtype="FLOAT",
    )
    return stream.getvalue()


def test_write_audio_normalizes_ieee_float_wav_to_pcm_s16le(tmp_path: Path) -> None:
    payload = _float_wav(np.array([-1.0, -0.5, 0.0, 0.5, 0.999], dtype=np.float32))
    destination = tmp_path / "normalized.wav"

    asset = _write_audio(payload, destination)

    with wave.open(str(destination), "rb") as source:
        assert source.getnchannels() == 1
        assert source.getsampwidth() == 2
        assert source.getframerate() == 16_000
        assert source.getcomptype() == "NONE"
        pcm = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2")

    assert asset.sample_format == "pcm_s16le"
    assert asset.channels == 1
    assert asset.sample_rate_hz == 16_000
    assert asset.duration_seconds == len(pcm) / 16_000
    assert pcm.tolist() == pytest.approx([-32768, -16384, 0, 16384, 32735], abs=1)


def test_write_audio_downmixes_float_stereo_to_mono(tmp_path: Path) -> None:
    stereo = np.array([[0.5, -0.5], [1.0, 1.0], [-1.0, -1.0]], dtype=np.float32)
    destination = tmp_path / "mono.wav"

    asset = _write_audio(_float_wav(stereo), destination)

    with wave.open(str(destination), "rb") as source:
        assert source.getnchannels() == 1
        pcm = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2")

    assert asset.channels == 1
    assert pcm.tolist() == pytest.approx([0, 32767, -32768], abs=1)


def test_write_audio_rejects_wrong_sample_rate(tmp_path: Path) -> None:
    stream = io.BytesIO()
    sf.write(
        stream,
        np.zeros(800, dtype=np.float32),
        samplerate=8_000,
        format="WAV",
        subtype="FLOAT",
    )

    with pytest.raises(RuntimeError, match="16 kHz"):
        _write_audio(stream.getvalue(), tmp_path / "wrong-rate.wav")
