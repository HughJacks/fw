#!/bin/sh
# install.sh — set fw up in this folder: its Python (with loro), the page built, and `fw` on your PATH.
# Run it again any time (after a `git pull`, say): it only does what's missing.
set -e
cd "$(dirname "$0")"
here="$(pwd)"

say() { printf '\n\033[1m%s\033[0m\n' "$1"; }
fail() { printf '\n\033[31m%s\033[0m\n' "$1" >&2; exit 1; }

say "Checking what fw needs…"
command -v python3 >/dev/null || fail "Python 3 isn't installed. On a Mac: brew install python   (Homebrew: https://brew.sh)"
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || fail "fw needs Python 3.10 or newer (you have $(python3 --version)). On a Mac: brew install python"
command -v node >/dev/null || fail "Node isn't installed. On a Mac: brew install node   (or https://nodejs.org)"
[ "$(node -p 'process.versions.node.split(".")[0]')" -ge 22 ] || fail "fw needs Node 22 or newer (you have $(node --version)). On a Mac: brew upgrade node"
command -v zsh >/dev/null || fail "fw's launcher needs zsh (every Mac has it; on Linux: install zsh)"
echo "  python $(python3 --version | cut -d' ' -f2), node $(node --version), zsh: ok"

say "Setting up fw's Python (in .venv, just for fw)…"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/pip install --quiet --disable-pip-version-check loro==1.17.1

say "Building the page…"
(cd web && npm ci --silent --no-audit --no-fund && npm run build --silent)

say "Putting fw on your PATH…"
mkdir -p "$HOME/.local/bin"
ln -sf "$here/fw" "$HOME/.local/bin/fw"
case ":$PATH:" in
  *":$HOME/.local/bin:"*) echo "  fw is ready: type  fw" ;;
  *) echo "  linked fw into ~/.local/bin, which isn't on your PATH yet. Add this line to ~/.zshrc, then open a new terminal:"
     echo '    export PATH="$HOME/.local/bin:$PATH"'
     echo "  (or run it from here: $here/fw)" ;;
esac

say "Done. Start writing with:  fw"
