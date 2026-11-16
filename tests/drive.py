import os, re, select, signal, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import fwtest as F
ED = F.ED
def pump(fd, secs):  # read a pty for a fixed time (for suites that drive one by hand)
    end = time.time() + secs
    while time.time() < end:
        if select.select([fd], [], [], 0.01)[0]:
            try: os.read(fd, 65536)
            except OSError: return
MARK = re.compile(r"\{\{block(?: \S+)?\}\}")
QID = re.compile(r"(\{\{quote \S+) \S+\}\}")
def plain(text):  # the draft as the editor shows it: block markers hidden, quote ids (random) left out
    return None if text is None else "\n".join(QID.sub(r"\1}}", l) for l in text.split("\n") if not MARK.fullmatch(l))
def run(initial, keys, args=(), cols=40, rows=10, sig=None, raw=False):
    """The editor on t/f.txt (`initial`, or no file), sent `keys` (a float: wait
    that long), then killed with `sig` or left to quit; returns the file."""
    path = os.path.join("t", "f.txt")
    if initial is None:
        if os.path.exists(path): os.remove(path)
    else:
        open(path, "w").write(initial)
    t = F.Term([os.environ.get("FW_PYTHON", sys.executable), ED, path, *args], cols, rows, env={
        "PATH": os.path.abspath("fakebin") + ":/usr/local/bin",  # never touch the real clipboard
        "CLIP": os.path.abspath("t/clip.txt"),
        "FW_DATA": os.environ.get("FW_DATA", os.path.abspath("t/store.json"))})  # never the real store
    t.key(*keys)
    if sig: t.kill(sig)
    if not t.done(): t.kill(); os.waitpid(t.pid, 0); return "TIMEOUT"
    os.close(t.fd)
    text = open(path).read() if os.path.exists(path) else None
    return text if raw else plain(text)

S, Q, Z, Y = "\x13", "\x11", "\x1a", "\x19"
UP, DOWN, LEFT, RIGHT = "\x1b[A", "\x1b[B", "\x1b[D", "\x1b[C"
cases = [
 ("append at +3", "abc\n\n", ["hello world", S, Q], ["+3"], "abc\n\nhello world"),
 ("new file", None, ["hi", S, Q], [], "hi"),
 ("quit saves", "x", ["yo", Q], [], "yox"),
 ("autosave after idle (then SIGKILL)", "x", ["yo", 1.5], [], "yox"),
 ("saved as soon as the keys stop (SIGKILL 0.5 s later; there was a 1 s wait)", "x", ["yo", 0.5], [], "yox"),
 ("undo word", "", ["one two", Z, S, Q], [], "one"),
 ("undo+redo", "", ["one two", Z, Y, S, Q], [], "one two"),
 ("paste CR and CRLF", "", ["a\rb\r\nc", S, Q], [], "a\nb\nc"),
 ("backspace joins", "ab\ncd", [DOWN, "\x7f", S, Q], [], "abcd"),
 ("delete joins", "ab\ncd", ["\x1b[F", "\x1b[3~", S, Q], [], "abcd"),
 ("option-backspace", "", ["hello there", "\x1b\x7f", S, Q], [], "hello "),
 ("option-left ESC b", "", ["hello there", "\x1bb", "X", S, Q], [], "hello Xthere"),
 ("iterm option-left", "", ["hello there", "\x1b[1;3D", "X", S, Q], [], "hello Xthere"),
 ("wrap: up within wrapped line", "", ["aaaa bbbb cccc dddd eeee ffff gggg hhhh iiii", UP, "X", S, Q], [], None),
 ("unicode", "", ["café 日本 ✨", LEFT, "!", S, Q], [], "café 日本 !✨"),
 ("shift-left x3 then type", "hello", ["\x1b[F", "\x1b[1;2D"*3, "X", S, Q], [], "heX"),
 ("ctrl-a then type replaces all", "abc\ndef", ["\x01", "new", S, Q], [], "new"),
 ("typing over a selection is one undo", "abc", ["\x01", "z", Z, S, Q], [], "abc"),
 ("ctrl-a ctrl-x cuts all", "abc", ["\x01", "\x18", S, Q], [], ""),
 ("copy then paste at end", "abc", ["\x01", "\x03", "\x1b[C", "\x16", S, Q], [], "abcabc"),
 ("shift-down+shift-right then backspace", "ab\ncd", ["\x1b[1;2B", "\x1b[1;2C", "\x7f", S, Q], [], "d"),
 ("shift+option word select, then cut", "one two", ["\x1b[F", "\x1b[1;4D", "\x18", S, Q], [], "one "),
 ("multi-line paste from clipboard", "ab", ["\x1b[C", "\x16", S, Q], [], "ax\nyb"),
 ("SIGHUP saves", "", ["unsaved words"], [], "unsaved words", ),
]
if __name__ == '__main__':
  ok = True
  for c in cases:
      name, init, keys, args, want = c
      sig = signal.SIGHUP if name == "SIGHUP saves" else signal.SIGKILL if "SIGKILL" in name else None
      open("t/clip.txt", "w").write("x\ny" if "multi-line paste" in name else "")
      got = run(init, keys, args, cols=24, sig=sig)
      if "cut" in name: print("      clipboard:", repr(open("t/clip.txt").read()))
      if want is None:
          print(f"{'INFO':5} {name}: {got!r}"); continue
      good = got == want; ok &= good
      print(f"{'ok' if good else 'FAIL':5} {name}: {got!r}" + ("" if good else f" want {want!r}"))
  print("ALL OK" if ok else "FAILURES")
