from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QPushButton, QLabel, QLineEdit, QFileDialog,
    QVBoxLayout, QTabWidget, QMessageBox, QHBoxLayout, QGroupBox,
    QProgressBar, QTextEdit, QApplication
)
from PySide6.QtCore import QStandardPaths
from gui.styles import MINIMAL_STYLE
from .worker import DownloadTranscribeWorker, LocalFileTranscribeWorker

from core.instagram import download_video_instagram
from PySide6.QtGui import QIcon


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gerador de Legendas com IA")
        self.setWindowIcon(QIcon("assets/icon.png"))
        self.setMinimumSize(600, 400)
        self.setStyleSheet(MINIMAL_STYLE)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Header
        header = QLabel("🎙️ Gerador de Legendas")
        header.setStyleSheet("font-size: 20pt; font-weight: bold;")
        layout.addWidget(header)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self.youtube_tab_ui(), "YouTube")
        self.tabs.addTab(self.local_file_tab_ui(), "Arquivo MP4")
        #self.tabs.addTab(self.instagram_tab_ui(), "Instagram")
        layout.addWidget(self.tabs)

        # Progresso e Logs
        self.progress_status = QLabel("Aguardando processamento.")
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setPlaceholderText("Log de atividades...")
        layout.addWidget(self.progress_status)
        layout.addWidget(self.progress)
        layout.addWidget(self.logs)


        self.setLayout(layout)

    def youtube_tab_ui(self):
        widget = QWidget()
        layout = QVBoxLayout()

        url_group = QGroupBox("Cole sua URL aqui:")
        url_layout = QHBoxLayout()
        self.youtube_url = QLineEdit()
        url_layout.addWidget(self.youtube_url)
        url_group.setLayout(url_layout)
        layout.addWidget(url_group)

        output_group = QGroupBox("Salvar em:")
        output_layout = QHBoxLayout()
        self.output_dir = QLineEdit()
        browse_button = QPushButton("Pasta de destino")
        
        filename_group = QGroupBox("Nome do arquivo:")
        filename_layout = QHBoxLayout()
        self.filename_input = QLineEdit()
        self.filename_input.setText("Transcription-Audio")
        filename_layout.addWidget(self.filename_input)
        ext_label = QLabel(".txt")
        filename_layout.addWidget(ext_label)
        filename_group.setLayout(filename_layout)
        layout.addWidget(filename_group)
        
        desktop_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        self.output_dir.setText(desktop_path)
        browse_button.clicked.connect(self.select_output_dir)
        output_layout.addWidget(self.output_dir)
        output_layout.addWidget(browse_button)
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        actions_group = QGroupBox("Ação")
        actions_layout = QHBoxLayout()
        convert_button = QPushButton("Converter áudio em texto")
        convert_button.clicked.connect(self.download_and_transcribe)

        actions_layout.addWidget(convert_button)
        actions_group.setLayout(actions_layout)
        layout.addWidget(actions_group)

        widget.setLayout(layout)
        return widget

    def local_file_tab_ui(self):
        widget = QWidget()
        layout = QVBoxLayout()

        source_group = QGroupBox("Arquivo MP4:")
        source_layout = QHBoxLayout()
        self.local_file_input = QLineEdit()
        self.local_file_input.setReadOnly(True)
        browse_button = QPushButton("Selecionar vídeo")
        browse_button.clicked.connect(self.select_local_file)
        source_layout.addWidget(self.local_file_input)
        source_layout.addWidget(browse_button)
        source_group.setLayout(source_layout)
        layout.addWidget(source_group)

        output_group = QGroupBox("Salvar em:")
        output_layout = QHBoxLayout()
        self.local_output_dir = QLineEdit()
        desktop_path = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DesktopLocation
        )
        self.local_output_dir.setText(desktop_path)
        output_browse_button = QPushButton("Pasta de destino")
        output_browse_button.clicked.connect(self.select_local_output_dir)
        output_layout.addWidget(self.local_output_dir)
        output_layout.addWidget(output_browse_button)
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        filename_group = QGroupBox("Nome do arquivo:")
        filename_layout = QHBoxLayout()
        self.local_filename_input = QLineEdit()
        self.local_filename_input.setText("Transcription-Audio")
        filename_layout.addWidget(self.local_filename_input)
        filename_layout.addWidget(QLabel(".txt"))
        filename_group.setLayout(filename_layout)
        layout.addWidget(filename_group)

        actions_group = QGroupBox("Ação")
        actions_layout = QHBoxLayout()
        convert_button = QPushButton("Transcrever arquivo")
        convert_button.clicked.connect(self.transcribe_local_file)
        actions_layout.addWidget(convert_button)
        actions_group.setLayout(actions_layout)
        layout.addWidget(actions_group)

        widget.setLayout(layout)
        return widget

    '''def instagram_tab_ui(self):
        widget = QWidget()
        layout = QVBoxLayout()

        url_group = QGroupBox("Cole sua URL aqui:")
        url_layout = QHBoxLayout()
        self.instagram_url = QLineEdit()
        url_layout.addWidget(self.instagram_url)
        url_group.setLayout(url_layout)
        layout.addWidget(url_group)

        output_group = QGroupBox("Salvar em:")
        output_layout = QHBoxLayout()
        self.output_dir_ig = QLineEdit()
        browse_button = QPushButton("Procurar")
        browse_button.clicked.connect(self.select_output_dir_ig)
        output_layout.addWidget(self.output_dir_ig)
        output_layout.addWidget(browse_button)
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        actions_group = QGroupBox("Ação")
        actions_layout = QHBoxLayout()
        download_button = QPushButton("Baixar Vídeo IG")
        download_button.clicked.connect(self.download_video_instagram_ui)
        actions_layout.addWidget(download_button)
        actions_group.setLayout(actions_layout)
        layout.addWidget(actions_group)

        widget.setLayout(layout)
        return widget'''
    
    def select_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Selecionar Diretório")
        if path:
            self.output_dir.setText(path)

    def select_local_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar arquivo MP4",
            "",
            "Vídeos MP4 (*.mp4);;Todos os arquivos (*)",
        )
        if path:
            self.local_file_input.setText(path)

    def select_local_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Selecionar Diretório")
        if path:
            self.local_output_dir.setText(path)

    def select_output_dir_ig(self):
        path = QFileDialog.getExistingDirectory(self, "Selecionar Diretório")
        if path:
            self.output_dir_ig.setText(path)

    def show_message(self, message):
        QMessageBox.information(self, "Info", message)
        
    def log(self, message):
        self.logs.append(message)
        QApplication.processEvents()  # força atualização da UI para mostrar o texto imediatamente

    def download_and_transcribe(self):
        url = self.youtube_url.text().strip()
        output = self.output_dir.text().strip()
        filename = self.filename_input.text().strip() or "audio"

        if not url or not output:
            self.show_message("Por favor, preencha a URL e o diretório de saída.")
            return

        self.start_worker(DownloadTranscribeWorker(url, output, filename))

    def transcribe_local_file(self):
        file_path = Path(self.local_file_input.text().strip())
        output = self.local_output_dir.text().strip()
        filename = self.local_filename_input.text().strip() or "transcription"

        if not file_path.is_file():
            self.show_message("Selecione um arquivo MP4 válido.")
            return
        if file_path.suffix.lower() != ".mp4":
            self.show_message("O arquivo selecionado deve estar no formato MP4.")
            return
        if not output:
            self.show_message("Informe a pasta onde salvar a transcrição.")
            return

        self.start_worker(
            LocalFileTranscribeWorker(str(file_path), output, filename)
        )

    def start_worker(self, worker):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.show_message("Aguarde a transcrição em andamento terminar.")
            return

        self.logs.clear()
        self.progress.setRange(0, 0)
        self.progress_status.setText(
            "Processando… a barra animada indica que a tarefa está ativa. "
            "O Whisper não fornece um percentual nesta etapa."
        )
        self.worker = worker
        self.worker.log_signal.connect(self.on_worker_log)
        self.worker.finished_signal.connect(self.on_process_finished)
        self.worker.error_signal.connect(self.on_process_error)
        self.worker.start()
        
    def on_worker_log(self, message):
        self.progress_status.setText(message)
        self.log(message)

    def on_process_finished(self, transcription_path):
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress_status.setText("Processamento concluído.")
        self.log(f"O texto está salvo em: {transcription_path}")
        self.show_message("Audio convertido em texto com sucesso!")
        self.log("Obrigado por usar o Gerador de Legendas com IA! 😊")

    def on_process_error(self, error_msg):
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress_status.setText(
            "O processamento falhou. Consulte os detalhes no log."
        )
        self.log(f"Erro: {error_msg}")
        self.show_message(f"Ocorreu um erro: {error_msg}")

    def download_video_instagram_ui(self):
        url = self.instagram_url.text()
        output = self.output_dir_ig.text()
        if url and output:
            try:
                download_video_instagram(url, output)
                self.show_message("Download do vídeo IG concluído!")
            except Exception as e:
                self.show_message(f"Erro: {str(e)}")
