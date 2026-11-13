#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="$HOME/.local/share/legendar/app"
BIN_LINK="$HOME/.local/bin/legendar"
DESKTOP_FILE="$HOME/.local/share/applications/legendar.desktop"
ICON_FILE="$HOME/.local/share/icons/hicolor/scalable/apps/legendar.svg"
DOC_DIR="$HOME/.local/share/doc/legendar"
printf 'O aplicativo e seu ambiente Python serão removidos.\n'
printf 'Cache de modelos, configurações e logs serão preservados.\n'
if [[ -t 0 ]]; then
    read -r -p "Confirma a desinstalação? [s/N] " answer
    case "$answer" in s|S|sim|SIM|Sim) ;; *) printf 'Cancelada.\n'; exit 0 ;; esac
elif command -v zenity >/dev/null 2>&1; then
    zenity --question --title="Remover Legendar" --text="Remover o aplicativo? Modelos, configurações e logs serão preservados." || exit 0
else
    printf 'Execute este script em um terminal para confirmar a desinstalação.\n' >&2
    exit 1
fi
rm -rf -- "$APP_DIR"
rm -f -- "$BIN_LINK" "$DESKTOP_FILE" "$ICON_FILE"
rm -rf -- "$DOC_DIR"
printf 'Legendar removido. O cache em ~/.cache/legendar foi preservado.\n'
