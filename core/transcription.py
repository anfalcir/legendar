import os
import sys
from collections.abc import Callable
from pathlib import Path

import whisper


def transcribe_and_save_audio(
    audio_path,
    output_file,
    status_callback: Callable[[str], None] | None = None,
):
    def report_status(message):
        if status_callback is not None:
            status_callback(message)

    project_dir = Path(
        getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)
    )
    ffmpeg_dir = project_dir / "ffmpeg" / "bin"
    if ffmpeg_dir.is_dir():
        current_path = os.environ.get("PATH", "")
        path_entries = current_path.split(os.pathsep)
        if str(ffmpeg_dir) not in path_entries:
            os.environ["PATH"] = str(ffmpeg_dir) + os.pathsep + current_path

    report_status("Carregando o modelo Whisper...")
    model = whisper.load_model("base")
    report_status(
        "Modelo carregado. Analisando o áudio; o tempo depende da duração do "
        "vídeo e do desempenho do computador."
    )
    result = model.transcribe(str(audio_path))
    report_status("Análise concluída. Salvando o arquivo de texto...")
    Path(output_file).write_text(result["text"], encoding="utf-8")


def transcribe_and_save_audio_youtube(audio_path, output_file):
    transcribe_and_save_audio(audio_path, output_file)
