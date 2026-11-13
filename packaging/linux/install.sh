#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="$HOME/.local/share/legendar/app"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
UV_VERSION="0.13.7"
SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
BUNDLE_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
fail() { printf 'ERRO: %s\n' "$*" >&2; exit 1; }
ask() {
    local prompt="$1" answer
    if [[ -t 0 ]]; then
        read -r -p "$prompt [s/N] " answer
        case "$answer" in s|S|sim|SIM|Sim) return 0 ;; *) return 1 ;; esac
    elif command -v zenity >/dev/null 2>&1; then
        zenity --question --title="Legendar" --text="$prompt"
    else
        printf '%s\n' "$prompt" "Abra um terminal e execute novamente para confirmar." >&2
        return 1
    fi
}
[[ "$(uname -s)" == "Linux" ]] || fail "Este pacote é destinado ao Linux."
case "$(uname -m)" in x86_64|amd64) ;; *) fail "Arquitetura não suportada; exige Linux x86_64." ;; esac
for required in pyproject.toml uv.lock src/legendar/__main__.py; do
    [[ -f "$BUNDLE_ROOT/$required" ]] || fail "Pacote incompleto: $required ausente."
done
command -v curl >/dev/null 2>&1 || fail "Instale curl para continuar."
ensure_media_tools() {
    if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then return; fi
    printf '\nO Legendar precisa de FFmpeg e ffprobe para processar mídia.\n'
    if ! command -v apt-get >/dev/null 2>&1 || ! command -v sudo >/dev/null 2>&1; then
        fail "Instale manualmente ffmpeg, libegl1, libgl1 e libxkbcommon-x11-0."
    fi
    ask "Deseja instalar FFmpeg e bibliotecas de interface pelo APT? Será solicitada a senha do sistema." \
        || fail "Instalação cancelada; nenhuma alteração foi feita no sistema."
    sudo apt-get update
    sudo apt-get install --yes --no-install-recommends \
        ffmpeg libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0
    command -v ffmpeg >/dev/null 2>&1 || fail "FFmpeg não foi instalado corretamente."
    command -v ffprobe >/dev/null 2>&1 || fail "ffprobe não foi instalado corretamente."
}
ensure_uv() {
    local uv_bin="$BIN_DIR/uv" installer
    mkdir -p "$BIN_DIR"
    if [[ -x "$uv_bin" ]] && "$uv_bin" --version | grep -Fq " $UV_VERSION"; then return; fi
    if command -v uv >/dev/null 2>&1 && uv --version | grep -Fq " $UV_VERSION"; then return; fi
    printf 'Instalando uv %s no diretório privado do usuário...\n' "$UV_VERSION"
    installer="$(mktemp)"
    curl --fail --location --silent --show-error https://astral.sh/uv/install.sh --output "$installer"
    UV_VERSION="$UV_VERSION" UV_INSTALL_DIR="$BIN_DIR" UV_NO_MODIFY_PATH=1 sh "$installer"
    rm -f "$installer"
    [[ -x "$uv_bin" ]] || fail "O instalador não produziu $uv_bin."
    "$uv_bin" --version | grep -Fq " $UV_VERSION" || fail "Versão do uv divergente."
}
ensure_media_tools
ensure_uv
export PATH="$BIN_DIR:$HOME/.cargo/bin:$PATH"
printf '\nPreparando o Legendar em %s...\n' "$APP_DIR"
mkdir -p "$APP_DIR" "$DESKTOP_DIR" "$ICON_DIR"
cp -a "$BUNDLE_ROOT/src" "$APP_DIR/"
cp -a "$BUNDLE_ROOT/pyproject.toml" "$BUNDLE_ROOT/uv.lock" "$BUNDLE_ROOT/README.md" "$BUNDLE_ROOT/LICENSE" "$APP_DIR/"
cp -a "$BUNDLE_ROOT/packaging/linux/launch.sh" "$APP_DIR/launch.sh"
cp -a "$BUNDLE_ROOT/packaging/linux/uninstall.sh" "$APP_DIR/uninstall.sh"
chmod 700 "$APP_DIR/launch.sh" "$APP_DIR/uninstall.sh"
printf 'Preparando Python 3.12 gerenciado pelo uv...\n'
uv python install 3.12
(cd "$APP_DIR" && uv sync --locked --no-dev --extra runtime-cpu --python 3.12)
if [[ -f "$BUNDLE_ROOT/src/legendar/presentation/qt/assets/legendar.svg" ]]; then
    install -m 644 "$BUNDLE_ROOT/src/legendar/presentation/qt/assets/legendar.svg" "$ICON_DIR/legendar.svg"
fi
cat > "$BIN_DIR/legendar" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
exec "$APP_DIR/launch.sh" "\$@"
EOF
chmod 755 "$BIN_DIR/legendar"
cat > "$DESKTOP_DIR/legendar.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Legendar
Comment=Transcrição, alinhamento e tradução de legendas
Exec="$BIN_DIR/legendar"
Icon=legendar
Terminal=false
Categories=AudioVideo;Audio;Video;
StartupNotify=true
EOF
chmod 644 "$DESKTOP_DIR/legendar.desktop"
printf '\nInstalação concluída. Abra "Legendar" no menu ou execute: %s/legendar\n' "$BIN_DIR"
printf 'Modelos, configurações e logs ficam fora da instalação e serão preservados nas atualizações.\n'
