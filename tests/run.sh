#!/bin/zsh
# run.sh — run fw's test suites against throwaway copies of the code and throwaway stores.
#
#   tests/run.sh                 every suite, one per CPU core at once
#   tests/run.sh mask_test.py    just these ("web": the page: built, its node tests, the browser suite, the sweep)
#   FW_TEST_JOBS=1 tests/run.sh  one at a time
#   NO_COLOR=1 tests/run.sh      no colour (there's none when piped, either)
#
# Each suite runs in a temp folder of its own: the fw package, bin/ and web/index.html copied into dev/ (on
# PYTHONPATH), its stores under t/ ($FW_DATA points there from the start), so suites run side by side and no real
# store is ever touched. Python is the repo's .venv (it has loro). A suite prints a line per check ("ok" or
# "FAIL") and ends with "<NAME> OK" or "<NAME> FAILURES"; this prints a line per suite, the failed checks under
# it, and a summary, and exits 1 if anything failed.

zmodload zsh/datetime zsh/parameter
here="${0:A:h}"
app="${here:h}"
py="$app/.venv/bin/python"
[[ -x "$py" ]] || { print -u2 "no $py: python3 -m venv $app/.venv && $app/.venv/bin/pip install loro==1.17.1"; exit 1; }
export FW_PYTHON="$py" FW_WEB_PORT=8097 FW_WEB_WATCH=0 FW_MEANING_URL="${FW_MEANING_URL-off}"
jobs_at_once="${FW_TEST_JOBS:-$(sysctl -n hw.ncpu)}"

root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT

run_one() {  # suite -> $root/<suite>.out, its time in .time
  local work="$root/${1%.py}" t0=$EPOCHREALTIME
  mkdir -p "$work/dev/web" "$work/t"
  cp -R "$app/fw" "$app/bin" "$work/dev/" && cp "$app/web/index.html" "$work/dev/web/"
  cp "$here"/*.py "$work/"
  ( cd "$work" && PYTHONPATH="$work/dev" FW_DATA="$work/t/freewrites.json" "$py" "$1" ) >"$root/$1.out" 2>&1
  print -- $(( EPOCHREALTIME - t0 )) >"$root/$1.time"
}

run_web() {  # the page (web/): built, its node tests, the browser suite, the sweep -> web.out
  local t0=$EPOCHREALTIME out="$root/web.out"
  {
    if ! command -v node >/dev/null && command -v fnm >/dev/null; then eval "$(fnm env --shell zsh)"; fi
    if ! command -v node >/dev/null || [[ ! -d "$app/web/node_modules" ]]; then
      print -- "(no node, or web/node_modules: the web editor's tests skipped)"
    else
      cd "$app/web"
      node build.mjs >/dev/null 2>"$root/web.build" && print -- "ok    the page built" || { print -- "FAIL  the page didn't build"; cat "$root/web.build"; }
      node --test test/*.test.mjs 2>&1 | sed -nE 's/^ok [0-9]+ - (.*)/ok    \1/p; s/^not ok [0-9]+ - (.*)/FAIL  \1/p'
      if [[ -x "${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}" ]]; then
        VERBOSE=1 node test/e2e.mjs 2>&1 | sed -E 's/^    //' | grep -E '^(ok|FAIL|no error)|E2E'
        # the sweep: every pericope of a copy of the store this code is installed beside (taken under its lock; that
        # store is never written) opened and left in the browser, nothing changed by it
        local real="$root/real"; mkdir -p "$real"
        if (cd "$app" && env -u FW_DATA PYTHONPATH="$app" "$py" -c "
from fw import store as S
import shutil, sys
d = sys.argv[1]
if not S.LORO_PATH.exists(): sys.exit(1)
with S.store_lock():
    shutil.copy(S.LORO_PATH, d); shutil.copy(S.DATA_PATH, d)
for f in (S.TITLES_PATH, S.GUESSES_PATH):
    if f.exists(): shutil.copy(f, d)
if S.IMAGES_PATH.exists(): shutil.copytree(S.IMAGES_PATH, d + '/images')" "$real") 2>/dev/null; then
          VERBOSE=1 node test/e2e.mjs --sweep "$real" 2>&1 | sed -E 's/^    //' | grep -E '^(ok|FAIL|no error)'
        else
          print -- "(no store beside this code to sweep)"
        fi
      else
        print -- "(no Chrome: the browser suite skipped)"
      fi
    fi
  } >"$out" 2>&1
  if grep -qE '^FAIL' "$out"; then print -- "WEB FAILURES" >>"$out"; else print -- "WEB OK" >>"$out"; fi
  print -- $(( EPOCHREALTIME - t0 )) >"$root/web.time"
}

suites=("$@")
(( $#suites )) || suites=(${(f)"$(cd "$here" && ls *_test.py)"} web)
order=(web live_test.py kinds_test.py mask_test.py)   # the slowest first, so the others fill in around them
suites=(${order:*suites} ${suites:|order})

if [[ -t 1 && -z "$NO_COLOR" ]]; then
  ok=$'\e[32m' bad=$'\e[31m' dim=$'\e[2m' bold=$'\e[1m' off=$'\e[0m' live=1
else
  ok= bad= dim= bold= off= live=0
fi
finished() { local f=("$root"/*.time(N)); print $#f }
running() { REPLY=${#${(M)jobstates:#running*}} }   # ($(jobs) is empty in a script)
progress() { (( live )) && printf '\r%s  running · %d of %d done%s\e[K' "$dim" "$(finished)" $#suites "$off" }

start=$EPOCHREALTIME
for t in $suites; do
  while running; (( REPLY >= jobs_at_once )); do progress; sleep 0.1; done
  if [[ $t == web ]]; then run_web & else run_one "$t" & fi
done
while running; (( REPLY )); do progress; sleep 0.1; done
wait
(( live )) && printf '\r\e[K'

width=0
for t in $suites; do (( ${#t} > width )) && width=${#t}; done
passed=0 failed=0 checks=0
for t in ${(o)suites}; do
  out="$root/$t.out"
  n=$(grep -cE '^(ok|FAIL)( |$)' "$out")
  secs=$(<"$root/$t.time")
  (( checks += n ))
  if grep -qE ' OK$' <(grep -E '(OK|FAILURES)$' "$out" | tail -1); then
    (( passed++ ))
    printf "  %s✓%s %-${width}s %4d checks  %s%5.1fs%s\n" "$ok" "$off" "$t" $n "$dim" $secs "$off"
  else
    (( failed++ ))
    printf "  %s✗ %-${width}s%s %4d checks  %s%5.1fs%s\n" "$bad$bold" "$t" "$off" $n "$dim" $secs "$off"
    if grep -qE 'FAIL|Traceback|Error' "$out"; then
      grep -E 'FAIL|Traceback|Error' "$out" | head -20
    else
      tail -5 "$out"   # no summary and no failed check: show how it ended
    fi | sed "s/^/      $bad/;s/\$/$off/"
  fi
done
total=$(( EPOCHREALTIME - start ))
summary="$passed passed, $failed failed · $checks checks · $(printf %.1f $total)s"
if (( failed )); then print -- "$bad$bold✗ $summary$off"; else print -- "$ok$bold✓ $summary$off"; fi
(( failed == 0 ))
