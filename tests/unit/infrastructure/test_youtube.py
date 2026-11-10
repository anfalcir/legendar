from __future__ import annotations

from pathlib import Path

import pytest

from legendar.application.job.context import CancellationTokenImpl
from legendar.domain.entities.media import MediaKind, MediaSource
from legendar.domain.errors.catalog import DownloadError, InvalidInputError, JobCancelledError
from legendar.infrastructure.media.youtube import YtDlpDownloader


class RecordingProgress:
    def __init__(self) -> None:
        self.values = []

    def report(self, fraction: float, message: str = "") -> None:
        self.values.append((fraction, message))


class FakeYDL:
    def __init__(self, options: dict, *, root: Path, playlist: bool = False) -> None:
        self.options = options
        self.root = root
        self.playlist = playlist
        self.output_path = root / "legendar-youtube-video123.webm"
        self.output_path.write_bytes(b"audio bytes")

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def extract_info(self, url: str, *, download: bool):
        assert download is True
        assert url == "https://www.youtube.com/watch?v=video123"
        hook = self.options["progress_hooks"][0]
        hook(
            {
                "status": "downloading",
                "downloaded_bytes": 50,
                "total_bytes": 100,
            }
        )
        hook(
            {
                "status": "finished",
                "filename": str(self.output_path),
                "info_dict": {"filepath": str(self.output_path)},
            }
        )
        if self.playlist:
            return {
                "_type": "playlist",
                "entries": [{"id": "one"}],
                "filepath": str(self.output_path),
            }
        return {"id": "video123", "filepath": str(self.output_path)}

    def prepare_filename(self, _info):
        return str(self.output_path)


def _source(url: str = "https://www.youtube.com/watch?v=video123") -> MediaSource:
    return MediaSource(kind=MediaKind.YOUTUBE, location=url)


def test_youtube_download_is_confined_to_workspace_and_reports_measured_progress(
    tmp_path: Path,
) -> None:
    progress = RecordingProgress()
    captured = {}

    def factory(options):
        captured.update(options)
        return FakeYDL(options, root=tmp_path)

    downloader = YtDlpDownloader(ydl_factory=factory)

    path = downloader.fetch(
        _source(),
        str(tmp_path),
        progress=progress,
    )

    assert Path(path).is_file()
    assert Path(path).parent == tmp_path
    assert captured["noplaylist"] is True
    assert captured["format"] == "bestaudio/best"
    assert captured["socket_timeout"] > 0
    assert progress.values[0][0] == pytest.approx(0.5)
    assert progress.values[-1][0] == 1.0


@pytest.mark.parametrize(
    "url",
    [
        "https://youtube.com.evil.example/watch?v=x",
        "https://notyoutube.example/watch?v=x",
        "file:///etc/passwd",
        "https://user:password@youtube.com/watch?v=x",
    ],
)
def test_youtube_downloader_rejects_untrusted_or_non_http_urls(url: str) -> None:
    downloader = YtDlpDownloader(ydl_factory=lambda _options: pytest.fail("not called"))

    with pytest.raises(InvalidInputError):
        downloader.fetch(_source(url), "/tmp/legendar-test")


def test_youtube_downloader_rejects_non_youtube_sources(tmp_path: Path) -> None:
    downloader = YtDlpDownloader(ydl_factory=lambda _options: pytest.fail("not called"))
    source = MediaSource(kind=MediaKind.LOCAL_FILE, location=str(tmp_path / "file.mp4"))

    with pytest.raises(InvalidInputError, match="somente fontes do YouTube"):
        downloader.fetch(source, str(tmp_path))


def test_youtube_downloader_rejects_playlist_and_removes_partial_artifacts(
    tmp_path: Path,
) -> None:
    downloader = YtDlpDownloader(
        ydl_factory=lambda options: FakeYDL(options, root=tmp_path, playlist=True)
    )

    with pytest.raises(DownloadError, match="Playlists"):
        downloader.fetch(_source(), str(tmp_path))

    assert list(tmp_path.glob("legendar-youtube-*")) == []


def test_youtube_downloader_cleans_files_when_cancelled_from_progress_hook(
    tmp_path: Path,
) -> None:
    token = CancellationTokenImpl()

    class CancellingProgress:
        def report(self, fraction: float, message: str = "") -> None:
            token.cancel("cancelamento do download")

    downloader = YtDlpDownloader(
        ydl_factory=lambda options: FakeYDL(options, root=tmp_path)
    )

    with pytest.raises(JobCancelledError, match="cancelamento do download"):
        downloader.fetch(
            _source(),
            str(tmp_path),
            token=token,
            progress=CancellingProgress(),
        )

    assert list(tmp_path.glob("legendar-youtube-*")) == []


def test_youtube_downloader_rejects_output_outside_workspace(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.webm"

    class OutsideYDL(FakeYDL):
        def __init__(self, options: dict, *, root: Path) -> None:
            super().__init__(options, root=root)
            self.output_path = outside
            outside.write_bytes(b"external")

        def extract_info(self, _url: str, *, download: bool):
            return {"id": "video123", "filepath": str(self.output_path)}

    downloader = YtDlpDownloader(
        ydl_factory=lambda options: OutsideYDL(options, root=tmp_path)
    )

    with pytest.raises(DownloadError, match="fora do workspace"):
        downloader.fetch(_source(), str(tmp_path))

    assert outside.exists()
    outside.unlink()
