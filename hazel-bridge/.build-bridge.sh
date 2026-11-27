#!/bin/zsh
export OPAMROOT=$HOME/.opam-arm PKG_CONFIG_PATH=$HOME/.opam-arm/pkgconfig:$HOME/.opam-arm/openssl/lib/pkgconfig
eval "$($HOME/.local/bin/opam-arm env --switch=hazel --set-switch)"
cd $HOME/yale/hazel
dune build --profile release ./src/fwbridge/fwbridge.bc.js 2>&1 | tail -40
cp _build/default/src/fwbridge/fwbridge.bc.js $HOME/yale/fw-expr/web/vendor/hazel.js   # (into fw's expr branch: the page loads it as dist/hazel.js)
