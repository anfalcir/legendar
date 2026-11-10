"""Caracterização da aplicação legada preservada durante a remodelagem.

Os doubles isolam dependências pesadas e efeitos externos: estes testes registram
os contratos observáveis da baseline sem baixar mídia, carregar modelos ou usar rede.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

_LEGACY_MODULES = (
    "gui.ui_main",
    "gui.worker",
    "core.instagram",
    "core.youtube",
    "core.transcription",
)


@pytest.fixture()
def legacy_modules(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Importa os módulos antigos com doubles para dependências opcionais."""

    for module_name in _LEGACY_MODULES:
        sys.modules.pop(module_name, None)

    whisper = ModuleType("whisper")
    whisper.load_model = Mock()
    yt_dlp = ModuleType("yt_dlp")

    class FakeInstaloader:
        pass

    instaloader = ModuleType("instaloader")
    instaloader.Instaloader = FakeInstaloader

    monkeypatch.setitem(sys.modules, "whisper", whisper)
    monkeypatch.setitem(sys.modules, "yt_dlp", yt_dlp)
    monkeypatch.setitem(sys.modules, "instaloader", instaloader)

    modules = SimpleNamespace(
        whisper=whisper,
        yt_dlp=yt_dlp,
        transcription=importlib.import_module("core.transcription"),
        youtube=importlib.import_module("core.youtube"),
        instagram=importlib.import_module("core.instagram"),
        worker=importlib.import_module("gui.worker"),
        ui=importlib.import_module("gui.ui_main"),
    )
    yield modules

    for module_name in _LEGACY_MODULES:
        sys.modules.pop(module_name, None)


def test_legacy_transcription_loads_base_model_and_writes_utf8(
    legacy_modules: SimpleNamespace, tmp_path: Path
) -> None:
    class FakeModel:
        def __init__(self) -> None:
            self.audio_path: str | None = None

        def transcribe(self, audio_path: str) -> dict[str, str]:
            self.audio_path = audio_path
            return {"text": "  Olá, mundo!\n"}

    model = FakeModel()
    legacy_modules.whisper.load_model = Mock(return_value=model)
    audio_path = tmp_path / "entrada.mp4"
    output_path = tmp_path / "saida.txt"
    statuses: list[str] = []

    legacy_modules.transcription.transcribe_and_save_audio(
        audio_path, output_path, status_callback=statuses.append
    )

    legacy_modules.whisper.load_model.assert_called_once_with("base")
    assert model.audio_path == str(audio_path)
    assert output_path.read_text(encoding="utf-8") == "  Olá, mundo!\n"
    assert statuses == [
        "Carregando o modelo Whisper...",
        (
            "Modelo carregado. Analisando o áudio; o tempo depende da duração do "
            "vídeo e do desempenho do computador."
        ),
        "Análise concluída. Salvando o arquivo de texto...",
    ]


def test_legacy_transcription_prepends_bundled_ffmpeg_only_once(
    legacy_modules: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    project = tmp_path / "bundle"
    bundled_ffmpeg = project / "ffmpeg" / "bin"
    bundled_ffmpeg.mkdir(parents=True)
    module_file = project / "core" / "transcription.py"
    module_file.parent.mkdir()
    monkeypatch.setattr(legacy_modules.transcription, "__file__", str(module_file))
    monkeypatch.setenv("PATH", "/usr/bin")

    class FakeModel:
        def transcribe(self, _audio_path: str) -> dict[str, str]:
            return {"text": "teste"}

    legacy_modules.whisper.load_model = Mock(return_value=FakeModel())
    output_path = tmp_path / "saida.txt"

    legacy_modules.transcription.transcribe_and_save_audio(
        tmp_path / "entrada.wav", output_path
    )
    legacy_modules.transcription.transcribe_and_save_audio(
        tmp_path / "entrada.wav", output_path
    )

    entries = os.environ["PATH"].split(os.pathsep)
    assert entries[0] == str(bundled_ffmpeg)
    assert entries.count(str(bundled_ffmpeg)) == 1


def test_legacy_youtube_download_uses_audio_extraction_and_bundled_ffmpeg(
    legacy_modules: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle"
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    captured: dict[str, object] = {}

    class FakeYoutubeDL:
        def __init__(self, options: dict[str, object]) -> None:
            captured["options"] = options

        def __enter__(self) -> FakeYoutubeDL:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def download(self, urls: list[str]) -> None:
            captured["urls"] = urls

    legacy_modules.yt_dlp.YoutubeDL = FakeYoutubeDL
    output_path = str(tmp_path / "audio-base")

    legacy_modules.youtube.download_audio_youtube(
        "https://www.youtube.com/watch?v=example", output_path
    )

    options = captured["options"]
    assert isinstance(options, dict)
    assert options["format"] == "bestaudio/best"
    assert options["outtmpl"] == output_path
    assert options["ffmpeg_location"] == str(bundle / "ffmpeg" / "bin")
    assert options["postprocessors"] == [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }
    ]
    assert captured["urls"] == ["https://www.youtube.com/watch?v=example"]


def test_legacy_worker_allocates_non_colliding_text_output_paths(
    legacy_modules: SimpleNamespace, tmp_path: Path
) -> None:
    output_dir = tmp_path / "transcriptions"
    output_dir.mkdir()
    (output_dir / "sermao.txt").write_text("primeiro", encoding="utf-8")
    (output_dir / "sermao_1.txt").write_text("segundo", encoding="utf-8")

    actual = legacy_modules.worker.unique_transcription_path(output_dir, "sermao")

    assert actual == str(output_dir / "sermao_2.txt")


def test_legacy_local_worker_emits_the_text_file_path(
    legacy_modules: SimpleNamespace, tmp_path: Path
) -> None:
    class FakeModel:
        def transcribe(self, _audio_path: str) -> dict[str, str]:
            return {"text": "Transcrição de referência."}

    legacy_modules.whisper.load_model = Mock(return_value=FakeModel())
    output_dir = tmp_path / "output"
    worker = legacy_modules.worker.LocalFileTranscribeWorker(
        str(tmp_path / "entrada.mp4"), str(output_dir), "sermao"
    )
    finished: list[str] = []
    errors: list[str] = []
    worker.finished_signal.connect(finished.append)
    worker.error_signal.connect(errors.append)

    worker.run()

    expected_path = output_dir / "sermao.txt"
    assert expected_path.read_text(encoding="utf-8") == "Transcrição de referência."
    assert finished == [str(expected_path)]
    assert errors == []


@pytest.mark.gui
def test_legacy_window_exposes_youtube_and_mp4_tabs_and_rejects_other_formats(
    qtbot, legacy_modules: SimpleNamespace, tmp_path: Path
) -> None:
    window = legacy_modules.ui.MainWindow()
    qtbot.addWidget(window)
    messages: list[str] = []
    window.show_message = messages.append

    assert window.tabs.count() == 2
    assert window.tabs.tabText(0) == "YouTube"
    assert window.tabs.tabText(1) == "Arquivo MP4"

    audio_path = tmp_path / "entrada.wav"
    audio_path.write_bytes(b"fixture")
    window.local_file_input.setText(str(audio_path))
    window.local_output_dir.setText(str(tmp_path))

    window.transcribe_local_file()

    assert messages == ["O arquivo selecionado deve estar no formato MP4."]
    assert not hasattr(window, "worker")



def test_legacy_youtube_worker_updates_mp3_path_after_a_collision(
    legacy_modules: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    output_dir = tmp_path / "output"
    worker = legacy_modules.worker.DownloadTranscribeWorker(
        "https://www.youtube.com/watch?v=example", str(output_dir), "sermao"
    )
    monkeypatch.setattr(legacy_modules.worker, "CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(legacy_modules.worker.time, "sleep", lambda _seconds: None)

    original_exists = os.path.exists
    collided_mp3 = str(cache_dir / "temp_audio.mp3")
    alternate_mp3 = str(cache_dir / "temp_audio_1.mp3")

    def exists(path: str | os.PathLike[str]) -> bool:
        candidate = os.fspath(path)
        if candidate == collided_mp3:
            return True
        if candidate == alternate_mp3:
            return False
        return original_exists(path)

    monkeypatch.setattr(legacy_modules.worker.os.path, "exists", exists)
    downloaded: list[str] = []
    transcribed: list[str] = []

    def fake_download(_url: str, output_base: str) -> None:
        downloaded.append(output_base)
        Path(f"{output_base}.mp3").write_bytes(b"audio")

    def fake_transcribe(audio_path: str, output_file: str) -> None:
        transcribed.append(audio_path)
        Path(output_file).write_text("Transcrição", encoding="utf-8")

    monkeypatch.setattr(legacy_modules.worker, "download_audio_youtube", fake_download)
    monkeypatch.setattr(
        legacy_modules.worker, "transcribe_and_save_audio_youtube", fake_transcribe
    )

    worker.run()

    assert downloaded == [str(cache_dir / "temp_audio_1")]
    assert transcribed == [alternate_mp3]
    assert (output_dir / "sermao.txt").read_text(encoding="utf-8") == "Transcrição"


def test_legacy_instagram_integration_is_explicitly_unimplemented(
    legacy_modules: SimpleNamespace, tmp_path: Path
) -> None:
    with pytest.raises(NotImplementedError, match="não suporta download por URL"):
        legacy_modules.instagram.download_video_instagram(
            "https://www.instagram.com/p/example/", tmp_path
        )


def test_legacy_python_sources_remain_parseable_on_supported_python() -> None:
    project_root = Path(__file__).resolve().parents[2]
    legacy_files = [
        project_root / "main.py",
        *sorted((project_root / "core").rglob("*.py")),
        *sorted((project_root / "gui").rglob("*.py")),
    ]

    for source_path in legacy_files:
        source = source_path.read_text(encoding="utf-8")
        compile(source, str(source_path), "exec")
