"""Fakes de portas de aplicação para testes herméticos (sem rede, sem mídia).

Cada fake registra chamadas e oferece um "hook" simples para simular falhas,
cancelamento e progresso, sem depender de FFmpeg, WhisperX ou PyTorch.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from legendar.domain.entities.media import (
    AudioAsset,
    AudioStreamInfo,
    MediaInfo,
    MediaKind,
    MediaSourceType,
)
from legendar.domain.entities.transcript import (
    AlignmentDiagnostics,
    AlignmentResult,
    Transcript,
    TranscriptSegment,
    TranscriptWord,
)
from legendar.domain.errors.catalog import JobCancelledError
from legendar.domain.value_objects.language import Language
from legendar.domain.value_objects.time import TimeRange


def make_media_info(*, audio: bool = True, duration: float = 12.0) -> MediaInfo:
    streams = (
        (AudioStreamInfo(index=0, codec="aac", channels=2, sample_rate_hz=48_000),)
        if audio
        else ()
    )
    return MediaInfo(
        kind=MediaKind.LOCAL_FILE,
        source_type=MediaSourceType.VIDEO,
        container="mp4",
        duration_seconds=duration,
        audio_streams=streams,
        video_streams_count=1,
    )


def make_transcript(
    *,
    language: Language = Language.ENGLISH,
    text: str = "hello world",
    start: float = 0.0,
    word_duration: float = 0.4,
    gap: float = 0.1,
) -> Transcript:
    tokens = text.split()
    words = tuple(
        TranscriptWord(
            text=token,
            range=TimeRange(
                start=start + index * (word_duration + gap),
                end=start + index * (word_duration + gap) + word_duration,
            ),
        )
        for index, token in enumerate(tokens)
    )
    segment = TranscriptSegment(
        text=text,
        range=TimeRange(words[0].range.start, words[-1].range.end),
        words=words,
    )
    return Transcript(segments=(segment,), language=language, model_name="tiny")


def make_alignment(transcript: Transcript | None = None) -> AlignmentResult:
    transcript = transcript or make_transcript()
    aligned = sum(len(segment.words) for segment in transcript.segments)
    return AlignmentResult(
        transcript=transcript,
        diagnostics=AlignmentDiagnostics(aligned_words=aligned),
    )


@dataclass
class FakeInspector:
    info: MediaInfo = field(default_factory=make_media_info)
    calls: list = field(default_factory=list)

    def inspect(self, source, *, token=None) -> MediaInfo:
        self.calls.append(source)
        if token is not None:
            token.raise_if_cancelled()
        return self.info


@dataclass
class FakeAudioPreparer:
    asset: AudioAsset | None = None
    calls: list = field(default_factory=list)

    def prepare(
        self, media_path, *, stream, destination_path, token=None, progress=None
    ) -> AudioAsset:
        self.calls.append((media_path, stream, destination_path))
        if token is not None:
            token.raise_if_cancelled()
        if progress is not None:
            progress.report(0.5, "Preparando áudio")
        if progress is not None:
            progress.report(0.5, "Preparando áudio")
        if self.asset is not None:
            return self.asset
        return AudioAsset(
            path=destination_path,
            sample_rate_hz=16_000,
            channels=1,
            sample_format="pcm_s16le",
            duration_seconds=12.0,
        )



@dataclass
class FakeDownloader:
    path: str | None = None
    calls: list = field(default_factory=list)

    def fetch(self, source, destination_dir, *, token=None, progress=None) -> str:
        self.calls.append((source, destination_dir))
        if token is not None:
            token.raise_if_cancelled()
        if progress is not None:
            progress.report(0.5, "Baixando mídia")
        if self.path is None:
            raise FileNotFoundError("arquivo de teste não configurado")
        return self.path


@dataclass
class FakeTranscriber:
    transcript: Transcript = field(
        default_factory=lambda: make_transcript(language=Language.PORTUGUESE)
    )

    def transcribe(
        self, audio, *, language=None, progress=None, token=None
    ) -> Transcript:
        if progress is not None:
            progress.report(0.5, "Transcrevendo")
        if token is not None:
            token.raise_if_cancelled()
        if progress is not None:
            progress.report(1.0, "Fim")
        return self.transcript


@dataclass
class FakeAligner:
    alignment: AlignmentResult | None = None

    def align(self, audio, transcript, *, progress=None, token=None) -> AlignmentResult:
        if progress is not None:
            progress.report(0.5, "Alinhando")
        if token is not None:
            token.raise_if_cancelled()
        return self.alignment or make_alignment(transcript)


@dataclass
class FakeTranslator:
    language: Language = Language.PORTUGUESE
    keep_shape: bool = True

    def translate(
        self, transcript, *, target_language, progress=None, token=None
    ) -> Transcript:
        if token is not None:
            token.raise_if_cancelled()
        if not self.keep_shape:
            return Transcript(
                segments=(TranscriptSegment(text="texto único"),),
                language=target_language,
                model_name="fake-translator",
            )
        segments = tuple(
            TranscriptSegment(
                text=f"[{target_language.value}] {segment.text}",
                range=segment.range,
            )
            for segment in transcript.segments
        )
        return Transcript(
            segments=segments, language=target_language, model_name="fake-translator"
        )


@dataclass
class FakePublisher:
    fail: bool = False
    calls: list = field(default_factory=list)

    def publish(self, track, destination_path) -> str:
        self.calls.append((track, destination_path))
        if self.fail:
            raise JobCancelledError("Falha simulada na publicação.")
        return destination_path
