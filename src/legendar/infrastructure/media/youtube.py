"""Aquisição controlada de áudio do YouTube via biblioteca yt-dlp."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from urllib.parse import urlsplit

from legendar.application.ports.protocols import CancellationToken, ProgressSink
from legendar.domain.entities.media import MediaKind, MediaSource
from legendar.domain.errors.catalog import DownloadError, InvalidInputError

YdlFactory = Callable[[dict], object]
_ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}


def _validate_youtube_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError as exc:
        raise InvalidInputError("A URL do YouTube está malformada.") from exc
    if parsed.scheme not in {"http", "https"} or host not in _ALLOWED_HOSTS:
        raise InvalidInputError("Informe uma URL válida do YouTube.")
    if parsed.username or parsed.password:
        raise InvalidInputError("A URL do YouTube não pode conter credenciais.")
    if port is not None and port not in {80, 443}:
        raise InvalidInputError("A URL do YouTube usa uma porta não permitida.")
    return value.strip()


def _default_ydl_factory(options: dict) -> object:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise DownloadError(
            "O suporte ao YouTube exige o perfil runtime-cpu com yt-dlp instalado."
        ) from exc
    return YoutubeDL(options)


def _cleanup_download_artifacts(root: Path) -> None:
    """Remove apenas arquivos com o prefixo reservado ao download deste job."""

    for candidate in root.glob("legendar-youtube-*"):
        try:
            if candidate.is_file() and root in candidate.resolve().parents:
                candidate.unlink(missing_ok=True)
        except OSError:
            # A limpeza principal do workspace é a segunda barreira de segurança.
            continue


class YtDlpDownloader:
    """Baixa somente a melhor faixa de áudio, sem playlist ou shell.

    Os hooks consultam o token em cada atualização do yt-dlp. O timeout de
    socket limita a espera por uma chamada de rede sem callback. A saída fica
    no diretório descartável do job e nunca usa o diretório de downloads do
    usuário.
    """

    __slots__ = ("_ydl_factory", "_socket_timeout", "_retries")

    def __init__(
        self,
        *,
        ydl_factory: YdlFactory | None = None,
        socket_timeout: float = 10.0,
        retries: int = 2,
    ) -> None:
        if socket_timeout <= 0:
            raise ValueError("O timeout de rede deve ser positivo.")
        if retries < 0:
            raise ValueError("A quantidade de tentativas não pode ser negativa.")
        self._ydl_factory = ydl_factory or _default_ydl_factory
        self._socket_timeout = socket_timeout
        self._retries = retries

    def fetch(
        self,
        source: MediaSource,
        destination_dir: str,
        *,
        token: CancellationToken | None = None,
        progress: ProgressSink | None = None,
    ) -> str:
        if source.kind is not MediaKind.YOUTUBE:
            raise InvalidInputError("O downloader aceita somente fontes do YouTube.")
        url = _validate_youtube_url(source.location)
        if token is not None:
            token.raise_if_cancelled()

        root = Path(destination_dir).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        finished_path: str | None = None

        def progress_hook(status: Mapping[str, object]) -> None:
            nonlocal finished_path
            if token is not None:
                token.raise_if_cancelled()
            state = status.get("status")
            if state == "downloading" and progress is not None:
                downloaded = status.get("downloaded_bytes")
                total = status.get("total_bytes") or status.get("total_bytes_estimate")
                if isinstance(downloaded, (int, float)) and isinstance(
                    total, (int, float)
                ) and total > 0:
                    progress.report(
                        min(0.99, max(0.0, downloaded / total)),
                        "Baixando áudio do YouTube",
                    )
            elif state == "finished":
                candidate = status.get("info_dict")
                if isinstance(candidate, Mapping):
                    value = candidate.get("filepath") or status.get("filename")
                    if isinstance(value, str):
                        finished_path = value

        options = {
            "format": "bestaudio/best",
            "outtmpl": str(root / "legendar-youtube-%(id)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "restrictfilenames": True,
            "windowsfilenames": True,
            "continuedl": False,
            "overwrites": False,
            "ignoreerrors": False,
            "socket_timeout": self._socket_timeout,
            "retries": self._retries,
            "fragment_retries": self._retries,
            "progress_hooks": [progress_hook],
        }

        try:
            ydl = self._ydl_factory(options)
            with ydl:
                info = ydl.extract_info(url, download=True)
                if token is not None:
                    token.raise_if_cancelled()
                if not isinstance(info, Mapping):
                    raise DownloadError(
                        "O YouTube não retornou metadados de uma mídia."
                    )
                if info.get("_type") == "playlist" or info.get("entries"):
                    raise DownloadError(
                        "Playlists não são aceitas; informe a URL de um único vídeo."
                    )
                candidate = (
                    info.get("filepath")
                    or info.get("_filename")
                    or finished_path
                    or ydl.prepare_filename(info)
                )
                if not isinstance(candidate, str) or not candidate:
                    raise DownloadError(
                        "O yt-dlp não informou o caminho do arquivo baixado."
                    )
                downloaded_path = Path(candidate).expanduser().resolve()
                if root not in downloaded_path.parents:
                    raise DownloadError(
                        "O yt-dlp retornou um caminho fora do workspace do job."
                    )
                if not downloaded_path.is_file() or downloaded_path.stat().st_size == 0:
                    raise DownloadError(
                        "O download terminou sem produzir um arquivo de áudio."
                    )
        except DownloadError:
            _cleanup_download_artifacts(root)
            if token is not None and token.is_cancelled:
                token.raise_if_cancelled()
            raise
        except Exception as exc:  # noqa: BLE001 - fronteira não confiável yt-dlp
            _cleanup_download_artifacts(root)
            if token is not None:
                token.raise_if_cancelled()
            detail = str(exc).replace(url, "[URL omitida]")
            raise DownloadError(
                "Não foi possível obter o áudio do YouTube.",
                technical_detail=f"{type(exc).__name__}: {detail[:500]}",
            ) from exc

        if token is not None:
            token.raise_if_cancelled()
        if progress is not None:
            progress.report(1.0, "Áudio do YouTube baixado")
        return str(downloaded_path)
