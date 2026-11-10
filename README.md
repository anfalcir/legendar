# Legendar

Aplicação desktop para transcrever o áudio de vídeos em texto, utilizando o modelo Whisper.

## Funcionalidades

- Transcrição de arquivos MP4 locais.
- Download de áudio a partir de links do YouTube.
- Transcrição automática com Whisper.
- Salvamento das transcrições em arquivos de texto (.txt).
- Interface gráfica desenvolvida com PySide6.

## Tecnologias

- [Whisper](https://github.com/openai/whisper) — reconhecimento de fala.
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — obtenção de áudio a partir de vídeos.
- [PySide6](https://doc.qt.io/qtforpython/) — interface gráfica.
- [FFmpeg](https://ffmpeg.org/) — processamento de áudio e vídeo.
- Python — lógica e integração da aplicação.

## Requisitos

- Python compatível com as dependências listadas em `requirements.txt`.
- FFmpeg disponível em `ffmpeg/bin` ou no `PATH` do sistema.
- Conexão com a internet para baixar áudio de vídeos do YouTube e obter o modelo Whisper na primeira execução.

## Instalação

1. Obtenha uma cópia do repositório privado e entre na pasta do projeto.
2. Crie um ambiente virtual:

   ```bash
   python -m venv .venv
   ```

3. Ative o ambiente virtual.

   Linux/macOS:

   ```bash
   source .venv/bin/activate
   ```

   Windows:

   ```powershell
   .venv\Scripts\Activate.ps1
   ```

4. Instale as dependências:

   ```bash
   pip install -r requirements.txt
   ```

## Execução

Com o ambiente virtual ativado, execute:

```bash
python main.py
```

## Transcrever um arquivo MP4

1. Abra a aba **Arquivo MP4**.
2. Selecione o vídeo.
3. Escolha a pasta de destino.
4. Informe o nome desejado para o arquivo de texto.
5. Clique em **Transcrever arquivo**.

A transcrição será salva com a extensão `.txt`. Caso já exista um arquivo com o mesmo nome, a aplicação acrescentará um sufixo numérico para evitar sobrescrevê-lo.

## Transcrever áudio de um vídeo do YouTube

1. Abra a aba **YouTube**.
2. Informe o endereço do vídeo.
3. Escolha a pasta de destino e o nome do arquivo.
4. Clique em **Converter áudio em texto**.

O áudio será obtido com `yt-dlp` e processado pelo Whisper.

## Solução de problemas no Linux

Se a aplicação não iniciar e o Qt informar que falta `xcb-cursor0` ou `libxcb-cursor0`, instale a biblioteca no Ubuntu/Debian:

```bash
sudo apt update
sudo apt install libxcb-cursor0
```

Depois, execute novamente:

```bash
./.venv/bin/python main.py
```

## Estrutura do projeto

```text
legendar/
├── core/
│   ├── __init__.py
│   ├── instagram.py
│   ├── transcription.py
│   └── youtube.py
├── gui/
│   ├── __init__.py
│   ├── styles.py
│   ├── ui_main.py
│   └── worker.py
├── .gitignore
├── main.py
├── README.md
└── requirements.txt
```

## Licença

O projeto utiliza a licença MIT.
