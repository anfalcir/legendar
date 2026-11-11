"""Portas (protocolos) que isolam o núcleo das fronteiras instáveis.

Cada porta existe porque há um consumidor real no pipeline ou um teste que a
usa como fake. Não criar abstração sem consumidor.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from legendar.application.job.context import JobContext
from legendar.application.pipeline.translation import (
    TranslationResult,
    TranslationUnit,
)
from legendar.domain.entities.media import (
    AudioAsset,
    AudioStreamInfo,
    MediaInfo,
    MediaSource,
)
from legendar.domain.entities.subtitle import SubtitleTrack
from legendar.domain.entities.transcript import AlignmentResult, Transcript
from legendar.domain.value_objects.language import Language


@runtime_checkable
class ProgressSink(Protocol):
    """Destino de progresso normalizado em ``[0, 1]``."""

    def report(self, fraction: float, message: str = "") -> None: ...


@runtime_checkable
class CancellationToken(Protocol):
    """Consulta de cancelamento cooperativo, sem bloqueio."""

    @property
    def is_cancelled(self) -> bool: ...

    def raise_if_cancelled(self) -> None:
        """Levanta ``JobCancelledError`` quando o cancelamento foi solicitado."""
        ...


@runtime_checkable
class MediaInspector(Protocol):
    """Inspeção de mídia via ffprobe (ou dublê em testes)."""

    def inspect(
        self, source: MediaSource, *, token: CancellationToken | None = None
    ) -> MediaInfo: ...


@runtime_checkable
class MediaDownloader(Protocol):
    """Aquisição de mídia remota (YouTube), separada da UI."""

    def fetch(
        self,
        source: MediaSource,
        destination_dir: str,
        *,
        token: CancellationToken | None = None,
        progress: ProgressSink | None = None,
    ) -> str:
        """Baixa e retorna o caminho local; verifica o token em checkpoints."""
        ...


@runtime_checkable
class AudioPreparer(Protocol):
    """Normalização para WAV PCM mono 16 kHz preservando offset de origem."""

    def prepare(
        self,
        media_path: str,
        *,
        stream: AudioStreamInfo,
        destination_path: str,
        token: CancellationToken | None = None,
        progress: ProgressSink | None = None,
    ) -> AudioAsset: ...


@runtime_checkable
class Transcriber(Protocol):
    """Reconhecimento de fala (Whisper) no idioma detectado/solicitado."""

    def transcribe(
        self,
        audio: AudioAsset,
        *,
        language: Language | None,
        progress: ProgressSink,
        token: CancellationToken | None = None,
    ) -> Transcript: ...


@runtime_checkable
class Aligner(Protocol):
    """Alinhamento por palavra (WhisperX) na linha do tempo global."""

    def align(
        self,
        audio: AudioAsset,
        transcript: Transcript,
        *,
        progress: ProgressSink,
        token: CancellationToken | None = None,
    ) -> AlignmentResult: ...


@runtime_checkable
class Translator(Protocol):
    """Tradução local por unidade de legenda, preservando 1:1 com as cues."""

    def translate(
        self,
        units: tuple[TranslationUnit, ...],
        *,
        source_language: Language,
        target_language: Language,
        progress: ProgressSink,
        token: CancellationToken | None = None,
    ) -> TranslationResult:
        """Traduz cada unidade e devolve exatamente um texto por unidade."""
        ...


@runtime_checkable
class SubtitlePublisher(Protocol):
    """Publicação atômica do SRT no destino final."""

    def publish(self, track: SubtitleTrack, destination_path: str) -> str:
        """Escreve em temporário e troca atomicamente; retorna o caminho final."""
        ...


@runtime_checkable
class WorkspaceFactory(Protocol):
    """Criação e limpeza do diretório de trabalho exclusivo de um job.

    A apresentação depende apenas deste contrato; a implementação concreta
    (diretório temporário seguro) fica na infraestrutura.
    """

    def create(
        self,
        *,
        job_id: str,
        source_label: str,
        output_path: Path,
        cache_dir: Path,
    ) -> JobContext: ...

    def cleanup(self, context: JobContext) -> None: ...
