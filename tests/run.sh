#!/bin/zsh
# run.sh — run fw's test suites against throwaway copies of the code.
#
#   tests/run.sh                 every suite, one per CPU core at once
#   tests/run.sh mask_test.py    just these
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
export FW_PYTHON="$py"  # what the suites run fw and the editor with: the store needs loro (pip install loro==1.17.1 here too)
jobs_at_once="${FW_TEST_JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)}"

root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT

run_one() {  # suite -> $root/<suite>.out, and its time in .time
  local work="$root/${1%.py}" t0=$EPOCHREALTIME
  mkdir -p "$work/dev/schema" "$work/t"
  cp "$app"/fw "$app"/fw_*.py "$app"/KEYS.md "$work/dev/"
  cp "$app"/schema/block.schema.json "$work/dev/schema/"
  cp "$here"/*.py "$work/"
  cp -R "$here/fakebin" "$work/"
  ( cd "$work" && FW_EDIT="$work/dev/fw_edit.py" "$py" "$1" ) >"$root/$1.out" 2>&1
  print -- $(( EPOCHREALTIME - t0 )) >"$root/$1.time"
}

suites=("$@")
(( $#suites )) || suites=(${(f)"$(cd "$here" && ls *_test.py e2e_blocks.py drive.py)"})
# the slowest first, so the others fill in around them
order=(undo_edit_test.py undo_test.py maskui_test.py fix_test.py maskkeys_test.py drive.py block_test.py live_test.py)
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
  run_one "$t" &
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
