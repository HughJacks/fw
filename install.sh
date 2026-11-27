#!/bin/sh
# Install or update fw:  curl -fsSL https://raw.githubusercontent.com/HughJacks/fw/main/install.sh | sh
# Inside a checkout it sets that checkout up; otherwise it clones into $FW_HOME (default ~/fw). Safe to rerun.
set -e
say() { printf '\033[1m%s\033[0m\n' "$1"; }
die() { printf '\033[31m%s\033[0m\n' "$1" >&2; exit 1; }
need() { command -v "$1" >/dev/null || { command -v brew >/dev/null && brew install "$2"; } || die "fw needs $1: install $2 (https://brew.sh, then: brew install $2)"; }

need git git; need python3 python; need node node
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || die "fw needs Python 3.10+ (brew install python)"
[ "$(node -p 'process.versions.node.split(".")[0]')" -ge 22 ] || die "fw needs Node 22+ (brew upgrade node)"

here="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
if [ -d "$here/fw" ] && [ -f "$here/bin/fw" ]; then dir="$here"
else
  dir="${FW_HOME:-$HOME/fw}"
  if [ -d "$dir/.git" ]; then say "Updating $dir"; git -C "$dir" pull -q --ff-only
  else say "Downloading fw into $dir"; git clone -q https://github.com/HughJacks/fw.git "$dir"; fi
fi
cd "$dir"

say "Python (.venv, with loro)"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/pip install -q --disable-pip-version-check loro==1.17.1

say "Building the page"
(cd web && npm ci --silent --no-audit --no-fund && npm run build --silent)

mkdir -p "$HOME/.local/bin" && ln -sf "$dir/bin/fw" "$HOME/.local/bin/fw"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *)
  rc="$HOME/.zshrc"; [ "${SHELL##*/}" = bash ] && rc="$HOME/.bashrc"
  grep -qs '.local/bin' "$rc" || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$rc"
  say "Added ~/.local/bin to your PATH in $rc: open a new terminal." ;;
esac
say "Done. Start writing: fw"
