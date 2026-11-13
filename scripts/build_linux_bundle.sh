#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
VERSION="$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "$ROOT/src/legendar/__init__.py")"
[[ -n "$VERSION" ]] || { echo "Não foi possível determinar a versão do Legendar." >&2; exit 1; }
DIST_DIR="$ROOT/dist"
BUNDLE_NAME="legendar-linux-x86_64-$VERSION"
BUNDLE_DIR="$DIST_DIR/$BUNDLE_NAME"
ARCHIVE="$DIST_DIR/$BUNDLE_NAME.tar.gz"
rm -rf -- "$BUNDLE_DIR"
mkdir -p "$BUNDLE_DIR/packaging/linux" "$BUNDLE_DIR/docs"
cp -a "$ROOT/src" "$BUNDLE_DIR/"
cp -a "$ROOT/pyproject.toml" "$ROOT/uv.lock" "$ROOT/README.md" "$ROOT/LICENSE" "$BUNDLE_DIR/"
cp -a "$ROOT/packaging/linux/install.sh" "$ROOT/packaging/linux/launch.sh" "$ROOT/packaging/linux/uninstall.sh" "$BUNDLE_DIR/packaging/linux/"
cp -a "$ROOT/docs/INSTALACAO.md" "$ROOT/docs/OPERACAO.md" "$ROOT/docs/HOMOLOGACAO.md" "$BUNDLE_DIR/docs/"
printf '%s\n' "$VERSION" > "$BUNDLE_DIR/VERSION"
chmod 755 "$BUNDLE_DIR/packaging/linux/"*.sh
mkdir -p "$DIST_DIR"
SOURCE_DATE_EPOCH="$(printenv SOURCE_DATE_EPOCH || printf '0')"
tar --sort=name --mtime="@$SOURCE_DATE_EPOCH" --owner=0 --group=0 --numeric-owner \
    -C "$DIST_DIR" -cf - "$BUNDLE_NAME" | gzip -n > "$ARCHIVE"
(cd "$DIST_DIR" && sha256sum "$(basename "$ARCHIVE")" > "$(basename "$ARCHIVE").sha256")
tar -tzf "$ARCHIVE" | grep -Fq "$BUNDLE_NAME/packaging/linux/install.sh"
tar -tzf "$ARCHIVE" | grep -Fq "$BUNDLE_NAME/uv.lock"
printf 'Bundle: %s\n' "$ARCHIVE"
printf 'SHA-256: %s\n' "$ARCHIVE.sha256"
