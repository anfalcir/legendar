#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
TEMP_HOME="$(mktemp -d)"
trap 'rm -rf "$TEMP_HOME"' EXIT

APP_DIR="$TEMP_HOME/.local/share/legendar/app"
TOOLS_DIR="$TEMP_HOME/.local/share/legendar/tools"
BIN_DIR="$TEMP_HOME/bin"
mkdir -p "$APP_DIR/src/legendar" "$TOOLS_DIR" "$BIN_DIR"
cp "$ROOT/packaging/linux/launch.sh" "$APP_DIR/launch.sh"
chmod 700 "$APP_DIR/launch.sh"

cat > "$TOOLS_DIR/uv" <<'FAKE_UV'
#!/usr/bin/env bash
set -Eeuo pipefail
printf '%s\n' "$*" >> "$HOME/uv-calls.log"
if [[ "$1" == "sync" ]]; then
    if [[ "$FAKE_UV_REPAIR" == "1" && " $* " == *" --offline "* ]]; then
        exit 1
    fi
    exit 0
fi
if [[ "$1" == "run" ]]; then
    printf 'PYTHONPATH=%s\n' "$PYTHONPATH"
    exit 0
fi
exit 99
FAKE_UV
chmod 700 "$TOOLS_DIR/uv"

cat > "$BIN_DIR/zenity" <<'FAKE_ZENITY'
#!/usr/bin/env bash
set -Eeuo pipefail
exit 0
FAKE_ZENITY
chmod 700 "$BIN_DIR/zenity"

expected_path="$APP_DIR/src"
output="$(HOME="$TEMP_HOME" PATH="$BIN_DIR:$PATH" FAKE_UV_REPAIR=0 bash "$APP_DIR/launch.sh")"
grep -Fq "PYTHONPATH=$expected_path" <<< "$output"
grep -Fq "sync --locked --no-dev --extra runtime-cpu --python 3.12 --offline" "$TEMP_HOME/uv-calls.log"
grep -Fq "run --locked --no-sync --python 3.12 python -m legendar" "$TEMP_HOME/uv-calls.log"

: > "$TEMP_HOME/uv-calls.log"
output="$(HOME="$TEMP_HOME" PATH="$BIN_DIR:$PATH" FAKE_UV_REPAIR=1 bash "$APP_DIR/launch.sh")"
grep -Fq "PYTHONPATH=$expected_path" <<< "$output"
grep -Fq "sync --locked --no-dev --extra runtime-cpu --python 3.12 --offline" "$TEMP_HOME/uv-calls.log"
grep -Fq "sync --locked --no-dev --extra runtime-cpu --python 3.12" "$TEMP_HOME/uv-calls.log"
grep -Fq "run --locked --no-sync --python 3.12 python -m legendar" "$TEMP_HOME/uv-calls.log"

printf 'Linux launcher smoke (healthy + consented repair): OK\n'
