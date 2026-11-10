from __future__ import annotations

import json

import pytest

from legendar.domain.entities.media import MediaKind, MediaSourceType
from legendar.domain.errors.catalog import MediaToolError, UnsupportedMediaError
from legendar.infrastructure.media.ffprobe import (
    parse_ffprobe_document,
    parse_ffprobe_payload,
)

PAYLOAD = {
    "streams": [
        {"index": 0, "codec_type": "video", "codec_name": "h264"},
        {
            "index": 1,
            "codec_type": "audio",
            "codec_name": "aac",
            "channels": 2,
            "sample_rate": "48000",
            "start_time": "0.021333",
            "tags": {"language": "por", "title": "Principal"},
        },
        {"index": 2, "codec_type": "subtitle", "codec_name": "mov_text"},
    ],
    "format": {
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "duration": "12.345",
    },
}


def test_parses_video_with_audio_and_ignores_subtitles() -> None:
    info = parse_ffprobe_payload(PAYLOAD)

    assert info.kind is MediaKind.LOCAL_FILE
    assert info.source_type is MediaSourceType.VIDEO
    assert info.container == "mov"
    assert info.duration_seconds == pytest.approx(12.345)
    assert info.video_streams_count == 1
    assert len(info.audio_streams) == 1
    stream = info.audio_streams[0]
    assert stream.index == 1
    assert stream.codec == "aac"
    assert stream.channels == 2
    assert stream.sample_rate_hz == 48_000
    assert stream.start_time_seconds == pytest.approx(0.021333)
    assert stream.language == "por"
    assert stream.title == "Principal"


def test_audio_only_source_is_classified_as_audio() -> None:
    payload = {
        "streams": [
            {
                "index": 0,
                "codec_type": "audio",
                "codec_name": "mp3",
                "channels": 1,
                "sample_rate": "44100",
            }
        ],
        "format": {"format_name": "mp3", "duration": "5.0"},
    }

    info = parse_ffprobe_payload(payload)

    assert info.source_type is MediaSourceType.AUDIO
    assert info.video_streams_count == 0


def test_missing_duration_is_preserved_as_none() -> None:
    payload = {
        "streams": PAYLOAD["streams"],
        "format": {"format_name": "matroska,webm"},
    }

    info = parse_ffprobe_payload(payload)

    assert info.duration_seconds is None
    assert info.container == "matroska"


def test_missing_format_is_tolerated() -> None:
    payload = {"streams": PAYLOAD["streams"]}

    info = parse_ffprobe_payload(payload)

    assert info.container == "desconhecido"
    assert info.duration_seconds is None


@pytest.mark.parametrize("start_time", ["N/A", "", None])
def test_missing_start_time_defaults_to_zero(start_time: str | None) -> None:
    payload = {
        "streams": [
            {
                "index": 0,
                "codec_type": "audio",
                "codec_name": "aac",
                "channels": 2,
                "sample_rate": "48000",
                "start_time": start_time,
            }
        ],
        "format": {"duration": "10.0"},
    }

    info = parse_ffprobe_payload(payload)

    assert info.audio_streams[0].start_time_seconds == 0.0


def test_empty_stream_list_is_rejected() -> None:
    with pytest.raises(UnsupportedMediaError):
        parse_ffprobe_payload({"streams": [], "format": {}})


def test_invalid_streams_field_is_rejected() -> None:
    with pytest.raises(UnsupportedMediaError):
        parse_ffprobe_payload({"streams": "nada"})


def test_audio_without_channels_is_rejected() -> None:
    payload = {
        "streams": [
            {"index": 0, "codec_type": "audio", "codec_name": "aac", "channels": 0}
        ]
    }

    with pytest.raises(UnsupportedMediaError):
        parse_ffprobe_payload(payload)


def test_start_time_after_duration_is_rejected() -> None:
    payload = {
        "streams": [
            {
                "index": 0,
                "codec_type": "audio",
                "codec_name": "aac",
                "channels": 2,
                "sample_rate": "48000",
                "start_time": "30.0",
            }
        ],
        "format": {"duration": "10.0"},
    }

    with pytest.raises(UnsupportedMediaError):
        parse_ffprobe_payload(payload)


def test_invalid_json_produces_tool_error() -> None:
    with pytest.raises(MediaToolError) as excinfo:
        parse_ffprobe_document("<html>erro</html>")

    assert "saída inválida" in excinfo.value.message


def test_document_roundtrip() -> None:
    info = parse_ffprobe_document(json.dumps(PAYLOAD))

    assert info.container == "mov"
