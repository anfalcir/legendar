from PySide6.QtCore import QThread, Signal
import os
import time
import shutil
from pathlib import Path
from core.youtube import download_audio_youtube
from core.transcription import (
    transcribe_and_save_audio,
    transcribe_and_save_audio_youtube,
)

CACHE_DIR = "cache"


def unique_transcription_path(output_dir, filename):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    transcription_path = output_path / f"{filename}.txt"
    counter = 1
    while transcription_path.exists():
        transcription_path = output_path / f"{filename}_{counter}.txt"
        counter += 1
    return str(transcription_path)


class DownloadTranscribeWorker(QThread):
    log_signal = Signal(str)
    finished_signal = Signal(str)
    error_signal = Signal(str)

    def __init__(self, url, output_dir, filename):
        super().__init__()
        self.url = url
        self.output_dir = output_dir
        self.filename = filename
        
    def log(self, message):
        self.log_signal.emit(message)

    def run(self):
        try:
            filename = self.filename or "transcription"
            
            if not os.path.exists(CACHE_DIR):
                os.makedirs(CACHE_DIR)
            
            self.log("Processando o seu vídeo para gerar a legenda...")
            time.sleep(3)
            
            if os.path.exists(CACHE_DIR):
                shutil.rmtree(CACHE_DIR)
                os.makedirs(CACHE_DIR)

            audio_base = os.path.join(CACHE_DIR, "temp_audio")
            counter_audio = 1
            audio_path = f"{audio_base}.mp3"
            while os.path.exists(f"{audio_base}.mp3"):
                audio_base = f"{os.path.join(CACHE_DIR, "temp_audio")}_{counter_audio}"
                counter_audio += 1

            transcription_path = unique_transcription_path(
                self.output_dir, filename
            )

            self.log("Transcrevendo o áudio para texto com inteligência artificial...")
            download_audio_youtube(self.url, audio_base)

            self.log("Finalizando a geração da legenda e salvando o arquivo...")
            transcribe_and_save_audio_youtube(audio_path, transcription_path)
            time.sleep(2)
            
            self.log("Transcrição realizada sem erros!")
            if os.path.exists(audio_path):
                os.remove(audio_path)
                time.sleep(2)

            self.finished_signal.emit(transcription_path)

        except Exception as e:
            self.error_signal.emit(str(e))


class LocalFileTranscribeWorker(QThread):
    log_signal = Signal(str)
    finished_signal = Signal(str)
    error_signal = Signal(str)

    def __init__(self, file_path, output_dir, filename):
        super().__init__()
        self.file_path = file_path
        self.output_dir = output_dir
        self.filename = filename

    def run(self):
        try:
            filename = self.filename or "transcription"
            transcription_path = unique_transcription_path(
                self.output_dir, filename
            )

            self.log_signal.emit("Iniciando a transcrição do arquivo MP4...")
            transcribe_and_save_audio(
                self.file_path,
                transcription_path,
                status_callback=self.log_signal.emit,
            )
            self.log_signal.emit("Transcrição realizada sem erros!")
            self.finished_signal.emit(transcription_path)
        except Exception as e:
            self.error_signal.emit(str(e))
