#!/bin/zsh
# A native arm64 opam for building Hazel (2026-11-23): its own root (~/.opam-arm), sandbox kept on; nothing of the
# Intel opam (/usr/local/bin/opam, ~/.opam) is touched.
set -e
export OPAMROOT=$HOME/.opam-arm
export PKG_CONFIG_PATH=$HOME/.opam-arm/pkgconfig:$HOME/.opam-arm/openssl/lib/pkgconfig
OPAM=$HOME/.local/bin/opam-arm
uname -m
[ -d $OPAMROOT ] || $OPAM init --bare -n -y
$OPAM switch list | grep -q hazel || $OPAM switch create hazel ocaml-base-compiler.5.2.0 -y
eval "$($OPAM env --switch=hazel --set-switch)"
$OPAM repo list | grep -q archive || $OPAM repo add archive git+https://github.com/ocaml/opam-repository-archive -y
cd $HOME/yale/hazel
$OPAM install ./hazel.opam.locked --deps-only -y --assume-depexts
echo DEPS-DONE
