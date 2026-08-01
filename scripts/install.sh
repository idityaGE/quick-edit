#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${QUICKEDIT_REPO_URL:-https://github.com/idityaGE/quick-edit.git}"
REF="${QUICKEDIT_REF:-main}"
INSTALL_DIR="${QUICKEDIT_INSTALL_DIR:-$HOME/.local/share/quick-edit}"
BIN_DIR="${QUICKEDIT_BIN_DIR:-$HOME/.local/bin}"
EXTRAS="${QUICKEDIT_EXTRAS:-}"
PYTHON_BIN="${PYTHON:-python3}"

log() {
  printf '%s\n' "$*"
}

fail() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

have() {
  command -v "$1" >/dev/null 2>&1
}

print_dep_help() {
  cat >&2 <<'EOF'

Install the missing dependency with your system package manager, then rerun this script.

macOS with Homebrew:
  brew install git python ffmpeg

Debian/Ubuntu:
  sudo apt update
  sudo apt install -y git python3 python3-venv ffmpeg

Fedora:
  sudo dnf install -y git python3 ffmpeg

Arch:
  sudo pacman -S git python ffmpeg
EOF
}

require_command() {
  if ! have "$1"; then
    print_dep_help
    fail "$1 was not found on PATH"
  fi
}

require_command git
require_command ffmpeg
require_command ffprobe
require_command "$PYTHON_BIN"

"$PYTHON_BIN" - <<'PY' || {
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
  print_dep_help
  fail "Python 3.11 or newer is required"
}

if ! "$PYTHON_BIN" -m venv --help >/dev/null 2>&1; then
  print_dep_help
  fail "Python venv support is required"
fi

log "Installing QuickEdit from source"
log "Repository: $REPO_URL"
log "Ref:        $REF"
log "Location:   $INSTALL_DIR"

if [ -e "$INSTALL_DIR" ] && [ ! -d "$INSTALL_DIR/.git" ]; then
  fail "$INSTALL_DIR exists but is not a Git checkout"
fi

if [ -d "$INSTALL_DIR/.git" ]; then
  log "Updating existing checkout"
  git -C "$INSTALL_DIR" fetch origin "$REF"
  git -C "$INSTALL_DIR" checkout "$REF"
  current_branch="$(git -C "$INSTALL_DIR" symbolic-ref --short -q HEAD || true)"
  if [ "$current_branch" = "$REF" ]; then
    git -C "$INSTALL_DIR" pull --ff-only origin "$REF"
  fi
else
  mkdir -p "$(dirname "$INSTALL_DIR")"
  git clone --branch "$REF" "$REPO_URL" "$INSTALL_DIR"
fi

log "Creating virtual environment"
"$PYTHON_BIN" -m venv "$INSTALL_DIR/.venv"
VENV_PYTHON="$INSTALL_DIR/.venv/bin/python"

log "Installing Python dependencies from the source checkout"
cd "$INSTALL_DIR"
if [ -n "$EXTRAS" ]; then
  "$VENV_PYTHON" -m pip install --upgrade pip
  "$VENV_PYTHON" -m pip install -e ".[${EXTRAS}]"
else
  "$VENV_PYTHON" -m pip install --upgrade pip
  "$VENV_PYTHON" -m pip install -e .
fi

mkdir -p "$BIN_DIR"
TARGET="$BIN_DIR/quickedit"
SOURCE="$INSTALL_DIR/.venv/bin/quickedit"
if [ -e "$TARGET" ] && [ ! -L "$TARGET" ]; then
  fail "$TARGET already exists and is not a symlink. Remove it or set QUICKEDIT_BIN_DIR."
fi
ln -sfn "$SOURCE" "$TARGET"

cat <<EOF

QuickEdit installed.

Command:
  $TARGET

Check it with:
  $TARGET --version

If your shell cannot find quickedit, add this to your shell profile:
  export PATH="$BIN_DIR:\$PATH"

Optional LLM provider installs:
  curl -fsSL https://raw.githubusercontent.com/idityaGE/quick-edit/main/scripts/install.sh | QUICKEDIT_EXTRAS=anthropic bash
  curl -fsSL https://raw.githubusercontent.com/idityaGE/quick-edit/main/scripts/install.sh | QUICKEDIT_EXTRAS=gemini bash
EOF
