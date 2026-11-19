#!/bin/zsh
# run.sh — run fw's test suites against throwaway copies of the code.
#
#   tests/run.sh                 every suite, one per CPU core at once
#   tests/run.sh mask_test.py    just these ("web": the web editor's page: built, node tests, browser suite)
#   FW_TEST_JOBS=1 tests/run.sh  one at a time
#   NO_COLOR=1 tests/run.sh      no colour (there's none when piped, either)
#
# Each suite gets its own temp folder with fw, fw_*.py and the schema copied
# in (as `dev/`) and its stores under `t/`, so suites can run side by side and
# the installed code, and your real freewrites.json are
# never touched. The suites drive fw in a pseudo-terminal through fwtest.py,
# which waits on what fw reports ($FW_SYNC) instead of sleeping; the screen
# is read with pyte (in tests/.venv; if it's missing: python3 -m venv
# tests/.venv && tests/.venv/bin/pip install pyte==0.8.2 loro==1.17.1). A suite prints one
# line per check ("ok" or "FAIL") and ends with "<NAME> OK" or
# "<NAME> FAILURES". This prints a line per suite, the failed checks under
# it, and a summary; it exits 1 if anything failed.

zmodload zsh/datetime zsh/parameter
here="${0:A:h}"
app="${here:h}"
py="$here/.venv/bin/python"
[[ -x "$py" ]] || { print -u2 "no $py: python3 -m venv $here/.venv && $here/.venv/bin/pip install pyte==0.8.2 loro==1.17.1"; exit 1; }
export FW_WEB_PORT=8097   # (a test that starts the web editor never touches the port of the one you write in)
export FW_PYTHON="$py"  # what the suites run fw and the editor with: the store needs loro (pip install loro==1.17.1 here too)
jobs_at_once="${FW_TEST_JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)}"

root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT

run_one() {  # suite -> $root/<suite>.out, and its time in .time
  local work="$root/${1%.py}" t0=$EPOCHREALTIME
  mkdir -p "$work/dev/schema" "$work/t"
  cp "$app"/fw "$app"/fw_*.py "$app"/KEYS.md "$work/dev/"
  cp "$app"/schema/block.schema.json "$work/dev/schema/"
  mkdir -p "$work/dev/web" && cp "$app/web/index.html" "$work/dev/web/"   # (the web editor's page: web_test)
  cp "$here"/*.py "$work/"
  cp -R "$here/fakebin" "$work/"
  ( cd "$work" && FW_EDIT="$work/dev/fw_edit.py" FW_MEANING_URL="${FW_MEANING_URL-off}" "$py" "$1" ) >"$root/$1.out" 2>&1
  print -- $(( EPOCHREALTIME - t0 )) >"$root/$1.time"
}

run_web() {  # the web editor's page (web/): built from its source, its node tests, then the browser suite -> web.out
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
        # the sweep: every pericope of a copy of the real store (taken under fw's lock; the real one never written)
        # opened and left in the browser, nothing changed by it
        local real="$root/real"; mkdir -p "$real"
        if (cd "$app" && "${FW_PYTHON:-$app/.venv/bin/python}" -c "
import fw_store as S, shutil, sys
d = sys.argv[1]
with S.store_lock():
    shutil.copy(S.LORO_PATH, d); shutil.copy(S.DATA_PATH, d)
for f in (S.TITLES_PATH, S.GUESSES_PATH):
    if f.exists(): shutil.copy(f, d)
if S.IMAGES_PATH.exists(): shutil.copytree(S.IMAGES_PATH, d + '/images')" "$real") 2>/dev/null; then
          VERBOSE=1 node test/e2e.mjs --sweep "$real" 2>&1 | sed -E 's/^    //' | grep -E '^(ok|FAIL|no error)'
        else
          print -- "(no real store to sweep)"
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
(( $#suites )) || suites=(${(f)"$(cd "$here" && ls *_test.py e2e_blocks.py drive.py)"} web)
# the slowest first, so the others fill in around them
order=(web undo_edit_test.py undo_test.py maskui_test.py fix_test.py maskkeys_test.py drive.py block_test.py live_test.py)
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
