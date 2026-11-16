"""fwtest — what the suites share: a throwaway store, fw or the editor in a
pseudo-terminal, waiting on it, and check/report.

    import fwtest as F
    S = F.use_store("t/store.json")             # fw_store, on a throwaway store
    F.write_store([F.blk(A, "alpha body", "Alpha")], [A])
    t = F.editor("t/f.txt", "--meta", "t/f.meta.json")   # or F.fw("garden notes")
    t.key("hello", F.ENTER)                     # each key sent, then waited on
    t.settle()                                  # the next idle tick: saved
    F.check("typed", "hello" in t.text(), t.row(0))
    y = t.find("hello")                          # a row by its text, not its number
    F.check("in a box", t.cell(y - 1, 2).data == "┌" and t.lines()[-1] == "hello")
    t.close(); F.report("MINE")

Find rows by what they show (`find`, `lines`) rather than by number: then a
change of layout (a box more, a taller header) only breaks the checks that
are about the layout.

The programs run with $FW_SYNC, so fw tells us each time it's about to wait
for a key: how many it has read, how often it has woken idle, and whether
there's unsaved writing. key() waits until fw has read and drawn each key,
settle() until it has woken idle once with nothing unsaved (the save as the
keys stop, or a look at the store), and until() on anything else, with a
timeout as a backstop. pump() still sleeps a fixed time, for tests of timing
itself.
"""
import fcntl, json, os, pty, re, select, signal, struct, sys, termios, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pyte_fix, pyte

DEV = os.path.abspath("dev")                     # the copy of the code under test
ED = os.environ.get("FW_EDIT", f"{DEV}/fw_edit.py")
UP, DOWN, LEFT, RIGHT, HOME, END = "\x1b[A", "\x1b[B", "\x1b[D", "\x1b[C", "\x1b[H", "\x1b[F"
ESC, BS, DEL, ENTER, TAB, BTAB = "\x1b", "\x7f", "\x1b[3~", "\r", "\t", "\x1b[Z"
QUIT, SAVE, UNDO, REDO, MENU = "\x11", "\x13", "\x1a", "\x19", "\x1f"
SYNC = re.compile(rb"\x1b\]777;fw;(\d+);(\d+);(\d);(\d+)\x07")   # keys read, idle wakes, unsaved?, bytes unread
WAIT = 10   # seconds before a wait gives up (the check after it then fails)

# --- check and report
ok = True
def check(label, cond, detail=""):
    global ok; ok &= bool(cond); print(f"{'ok' if cond else 'FAIL':5} {label}" + (f": {detail}" if detail else ""))
def same(label, got, want):
    global ok; good = got == want; ok &= good; print(f"{'ok' if good else 'FAIL':5} {label}: {got!r}" + ("" if good else f"  want {want!r}"))
def report(name): print(f"{name} OK" if ok else f"{name} FAILURES")

def wait_for(cond, timeout=WAIT):
    """Poll cond() until it holds (True) or time runs out (False)."""
    end = time.time() + timeout
    while not cond():
        if time.time() >= end: return False
        time.sleep(0.02)
    return True

# --- a throwaway store
def use_store(path="t/store.json", clean=False):
    """fw_store, reading and writing `path` (it reads $FW_DATA once, on import)."""
    os.environ["FW_DATA"] = os.path.abspath(path)
    if clean and os.path.exists(path): os.remove(path)
    sys.path.insert(0, os.path.dirname(ED)); import fw_store
    assert str(fw_store.DATA_PATH) == os.environ["FW_DATA"], "use_store before anything imports fw_store"
    return fw_store
def blk(i, content, title=None, created="2026-10-01T10:00:00-04:00", words=0):
    """A block: content is text, a list of child ids, or {"quote": id[, "mask": [...]]}."""
    return {"id": i, "title": title, "content": content, "words": words, "created": created}
def write_store(blocks, entries, path=None, version=5):
    json.dump({"schemaVersion": version, "entries": entries, "blocks": blocks}, open(path or os.environ["FW_DATA"], "w"))
def write_meta(i, path="t/f.meta.json", fields=()):
    json.dump({"id": i, "fields": list(fields)}, open(path, "w"))

# --- a program in a pseudo-terminal
class Term:
    """argv in a pty of cols x rows, its screen read with pyte."""
    def __init__(self, argv, cols=60, rows=12, env=None, ready=True):
        self.scr = pyte.Screen(cols, rows); self.st = pyte.ByteStream(self.scr)
        self.sync, self.at_key, self.dead, self.tail = None, (-1, 0), False, b""
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))   # sized before it starts
            os.environ.update(TERM="xterm-256color", FW_SYNC="1", **(env or {}))
            os.execvp(argv[0], argv)
        if ready: self.until(lambda: self.sync)
    def read(self, secs):
        """Read what comes within `secs`; False once the program has gone."""
        if self.dead or not select.select([self.fd], [], [], max(secs, 0))[0]: return not self.dead
        try: data = os.read(self.fd, 65536)
        except OSError: data = b""
        if not data: self.dead = True; return False   # it's gone (macOS: EOF, or EIO)
        self.st.feed(data)
        buf = self.tail + data
        for m in SYNC.finditer(buf): self.sync = tuple(map(int, m.groups()))
        self.tail = buf[-40:]   # a marker split across two reads
        return True
    def pump(self, secs):   # read for a fixed time
        end = time.time() + secs
        while self.read(end - time.time()) and time.time() < end: pass
    def until(self, cond, timeout=WAIT):
        """Read until cond() holds (True), or the program ends or time runs out."""
        end = time.time() + timeout
        while not cond():
            if not self.read(min(end - time.time(), 0.05)) or time.time() >= end: return bool(cond())
        return True
    def key(self, *ks, wait=0):
        """Send each key, then wait until fw has read it and drawn the result."""
        for k in ks:
            if isinstance(k, float): self.pump(k); continue
            n = self.sync[0] if self.sync else -1
            os.write(self.fd, k.encode())
            self.until(lambda: self.sync and self.sync[0] > n and not self.sync[3])
            if self.sync: self.at_key = self.sync[:2]
            self.pump(wait)
    def settle(self, timeout=WAIT):
        """Wait for the next idle tick that leaves nothing unsaved: the save as
        the keys stop, or a look at the store (every 0.25 s)."""
        return self.until(lambda: self.sync and self.sync[1] > self.at_key[1] and not self.sync[2], timeout)
    def text(self): return "\n".join(l.rstrip() for l in self.scr.display)
    def row(self, y): return self.scr.display[y].rstrip()
    def inside(self, y):
        """Row y's text inside its boxes: no block number, no box sides."""
        return re.sub(r"^[\d ]*[│┃ ]*", "", self.row(y)).rstrip(" │┃")
    def lines(self):
        """The rows that hold text, as their text inside the boxes (a dot
        before a block with no room for a box left out), top to bottom: what
        reads on screen, wherever the layout puts it."""
        return [t for t in (self.inside(y).lstrip("·") for y in range(self.scr.lines - 1)) if t and t[0] not in "┌└┏┗"]
    def find(self, text, after=-1):
        """The first row below `after` whose text (as in lines) is `text`, else None."""
        return next((y for y in range(after + 1, self.scr.lines - 1) if self.inside(y).lstrip("·") == text), None)
    def cell(self, y, x): return self.scr.buffer[y][x]
    def cursor(self): return self.scr.cursor.y, self.scr.cursor.x
    def done(self, timeout=3):
        """Wait for it to exit; True if it did."""
        end = time.time() + timeout
        while time.time() < end:
            if os.waitpid(self.pid, os.WNOHANG)[0]: self.pid = None; return True
            self.read(0.01) or time.sleep(0.005)
        return False
    def kill(self, sig=signal.SIGKILL):
        if self.pid:
            try: os.kill(self.pid, sig)
            except OSError: pass
    def close(self, keys=QUIT):
        """Quit it (killed if that doesn't work)."""
        if self.pid:
            self.key(keys)
            if not self.done(): self.kill(); os.waitpid(self.pid, 0); self.pid = None
        os.close(self.fd)

def editor(*args, cols=60, rows=12, env=None):
    """The editor on a draft file: editor("t/f.txt", "--meta", "t/f.meta.json")."""
    return Term([os.environ.get("FW_PYTHON", "python3"), ED, *args], cols, rows, env)
def fw(*args, cols=70, rows=16, env=None, home=f"{DEV}/fw"):
    """fw itself (zsh fw ARGS), on the store in $FW_DATA."""
    return Term(["zsh", home, *args], cols, rows, env)


def loro_merge(base: dict, laptop: dict, mini: dict) -> dict:
    """Block `base` in two machines' documents (fw_loro; the mini's a copy of
    the laptop's), changed on each to `laptop` and `mini`, then merged: the
    block as the merged document says it."""
    import fw_loro as L
    store = lambda b: {"schemaVersion": 17, "blocks": [b]}
    a = L.load(None, 1); L.write(a, store(base))
    b = L.load(L.snapshot(a), 2)
    L.write(a, store(laptop)); L.write(b, store(mini))
    L.merge(a, L.snapshot(b))
    return L.to_data(a)["blocks"][0]
