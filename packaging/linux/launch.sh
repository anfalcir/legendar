#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="$HOME/.local/share/legendar/app"
UV_BIN="$HOME/.local/bin/uv"
LOG_DIR="$HOME/.cache/legendar/logs"
LOG_FILE="$LOG_DIR/launcher.log"
fail() { printf 'ERRO: %s\n' "$*" >&2; exit 1; }
[[ -d "$APP_DIR/src/legendar" ]] || fail "Instalação ausente. Execute novamente o instalador do Legendar."
[[ -x "$UV_BIN" ]] || fail "uv não encontrado. Reexecute o instalador do Legendar."
mkdir -p "$LOG_DIR"
chmod 700 "$LOG_DIR" 2>/dev/null || true
cd "$APP_DIR"
# Verificação offline idempotente. Só tenta reparar pela rede após consentimento.
if ! "$UV_BIN" sync --locked --no-dev --extra runtime-cpu --python 3.12 --offline >"$LOG_FILE" 2>&1; then
    prompt="Foram detectadas dependências ausentes ou inconsistentes. Deseja reparar a instalação agora? O reparo pode baixar pacotes Python."
    accepted=1
    if command -v zenity >/dev/null 2>&1; then
        zenity --question --title="Legendar — reparar instalação" --text="$prompt" || accepted=0
    elif [[ -t 0 ]]; then
        read -r -p "$prompt [s/N] " answer
        case "$answer" in s|S|sim|SIM|Sim) ;; *) accepted=0 ;; esac
    else
        fail "Dependências precisam de reparo. Execute ~/.local/share/legendar/app/launch.sh em um terminal. Log: $LOG_FILE"
    fi
    [[ "$accepted" -eq 1 ]] || fail "Reparo cancelado pelo usuário."
    if ! "$UV_BIN" sync --locked --no-dev --extra runtime-cpu --python 3.12 >>"$LOG_FILE" 2>&1; then
        if command -v zenity >/dev/null 2>&1; then
            zenity --error --title="Legendar — falha na instalação" --text="Não foi possível reparar as dependências. Consulte $LOG_FILE."
        fi
        fail "Falha ao reparar dependências. Consulte $LOG_FILE."
    fi
fi
exec "$UV_BIN" run --locked --no-sync --python 3.12 python -m legendar "$@"
