// e2e.mjs — the web editor end to end: real keys into the real page, the store checked through the core.
//   node test/e2e.mjs [scenario …] [--shots DIR] [--jobs N]      (from web/; `npm run build` first; VERBOSE=1 every check)
// Each scenario gets a store of its own (fresh, so none depends on another's leftovers), its own fw_web.py on
// its own port, and its own tab in one headless Chrome, driven over the DevTools protocol (Node's own
// WebSocket, nothing installed); they all run at once. The page is opened with ?test (its timers quick: saves
// 30 ms after the keys stop) and says when it has settled (window.fw.settled(): nothing in flight, no save
// waiting, no page switching), so the tests wait on that, not on fixed sleeps; window.fw.select puts the cursor
// or a selection where a test wants it. Keys are real key events (Input.dispatchKeyEvent): what's tested is
// the page's own handling of them.
import { spawn, execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const FW = resolve(HERE, "../..");
const PY = process.env.FW_PYTHON || join(FW, ".venv/bin/python");
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const argv = process.argv.slice(2);
const opt = (name, dflt) => (argv.includes(name) ? argv[argv.indexOf(name) + 1] : dflt);
const SHOTS = opt("--shots", null), JOBS = +opt("--jobs", 8);
const ONLY = argv.filter((a, n) => !a.startsWith("--") && !["--shots", "--jobs"].includes(argv[n - 1]));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// --- the store each scenario starts from ---------------------------------------------------------------------
const A = "20261001T100000-a000", A1 = "20261001T100000-a001", QA = "20261001T100000-a002";
const B = "20261002T100000-b000", B1 = "20261002T100000-b001";
const T = "20261003T100000-c000", T1 = "20261003T100000-c001", T2 = "20261003T100000-c002";
const M = "20261004T100000-d000", QM = "20261004T100000-d001";
const R = "20261005T100000-e000", R1 = "20261005T100000-e001", QR1 = "20261005T100000-e002", QR2 = "20261005T100000-e003";
const blk = (id, content, title = null) => ({ id, title, content, words: 0, created: "2026-10-01T10:00:00-04:00" });
const K = "20261006T100000-f000";   // a kind, "poem" (its description empty)
const N = "20261008T100000-b100", QN = "20261008T100000-b101", N1 = "20261008T100000-b102";   // a quote of alpha (which quotes beta): a quote inside a quote
const S0 = "20261007T100000-a100", S1 = "20261007T100000-a101", S2 = "20261007T100000-a102";   // a container holding one block
const STORE = { schemaVersion: 9, entries: [A, B, T, M, R, K, S0, N], blocks: [
  blk(N, [QN, N1], "nested"), blk(QN, { quote: A }), blk(N1, "after the quotes"),
  blk(S0, [S1], "one inside"), blk(S1, [S2]), blk(S2, "the only block inside"),
  blk(K, { kind: "poem", blocks: [] }),
  blk(A, [A1, QA], "alpha"), blk(A1, "first words"), blk(QA, { quote: B }),
  blk(B, [B1], "beta"), blk(B1, "beta's words"),
  blk(T, [T1, T2], "fox"), blk(T1, "the quick brown fox"), blk(T2, "jumps over the dog"),
  blk(M, [QM], "masker"), blk(QM, { quote: T }),
  blk(R, [R1, QR1, QR2], "two quotes"), blk(R1, "r words"), blk(QR1, { quote: B }), blk(QR2, { quote: T })] };

// --- the harness ----------------------------------------------------------------------------------------------
let chrome, chromePort;
async function startChrome(dir) {
  chromePort = 19000 + Math.floor(Math.random() * 900);
  // (native: this Node may be an Intel build, under Rosetta, and an app it starts would be translated too)
  const native = process.platform === "darwin" ? ["arch", ["-arm64", CHROME]] : [CHROME, []];
  chrome = spawn(native[0], [...native[1], "--headless=new", `--remote-debugging-port=${chromePort}`, `--user-data-dir=${join(dir, "chrome")}`,
    "--no-first-run", "--window-size=1200,900",
    // (every tab runs at full speed: a background tab's timers aren't slowed to once a second)
    "--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows",
    "about:blank"], { stdio: "ignore" });
  for (let n = 0; n < 300; n++) {
    try { await fetch(`http://127.0.0.1:${chromePort}/json/version`); return; } catch { await sleep(50); }
  }
  throw new Error("chrome didn't start");
}

/** A tab of its own, driven over the protocol. */
async function tab() {
  const t = await (await fetch(`http://127.0.0.1:${chromePort}/json/new?about:blank`, { method: "PUT" })).json();
  const ws = new WebSocket(t.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener("open", r));
  let seq = 0;
  const waiting = new Map(), thrown = [];
  ws.addEventListener("message", (m) => {
    const d = JSON.parse(m.data);
    if (waiting.has(d.id)) { waiting.get(d.id)(d); waiting.delete(d.id); }
    if (d.method === "Runtime.exceptionThrown") thrown.push(d.params.exceptionDetails.exception?.description?.split("\n")[0]);
  });
  const cdp = (method, params = {}) => new Promise((r) => { const id = ++seq; waiting.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
  await cdp("Page.enable");
  await cdp("Runtime.enable");
  await cdp("Emulation.setFocusEmulationEnabled", { enabled: true });   // (every tab behaves as the focused one)
  await cdp("Emulation.setDeviceMetricsOverride", { width: 1200, height: 900, deviceScaleFactor: 1, mobile: false });
  return { cdp, thrown, close: () => { ws.close(); fetch(`http://127.0.0.1:${chromePort}/json/close/${t.id}`).catch(() => {}); } };
}

/** A scenario: its store, its core, its tab; `fn(t)` runs on them; what it checked comes back. `fn.store`: a copy
 * of that store instead (the sweep: the real one's). */
async function run(name, fn) {
  const dir = mkdtempSync(join(tmpdir(), `fw-e2e-${name}-`));
  const store = join(dir, "freewrites.json");
  if (fn.store) execFileSync("cp", ["-R", ...["freewrites.loro", "freewrites.json", "images", "picture-titles.json", "kind-guesses.json"]
    .map((f) => join(fn.store, f)).filter((f) => { try { readFileSync(f); return true; } catch { return f.endsWith("images"); } }), dir], { stdio: "ignore" });
  else writeFileSync(store, JSON.stringify(STORE));
  const env = { ...process.env, FW_DATA: store, FW_MEANING_URL: "off", FW_WEB_WATCH: "0" };   // (never rebuilt or restarted mid-test)
  execFileSync(PY, [join(FW, "fw_store.py"), "migrate"], { env, stdio: "ignore" });
  if (fn.setup) fn.setup(dir, JSON.parse(readFileSync(store, "utf8")));   // (what a scenario needs beside its store)
  const port = 20000 + Math.floor(Math.random() * 20000);
  const server = spawn(PY, [join(FW, "fw_web.py"), "--port", String(port), "--no-open"], { env, stdio: "ignore" });
  const out = [];
  let ok = true;
  const { cdp, thrown, close } = await tab();
  const js = async (expr) => (await cdp("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true })).result?.result?.value;
  const until = async (expr, ms = 4000) => { for (const end = Date.now() + ms; Date.now() < end; await sleep(25)) if (await js(expr)) return true; return false; };
  const t = {
    js, until, cdp, port, dir,
    check(label, cond, detail = "") { ok &&= !!cond; out.push(`${cond ? "ok   " : "FAIL "} ${label}${cond || !detail ? "" : ": " + detail}`); },
    /** The page settled: nothing in flight, nothing waiting to save, no switch (twice in a row, to be sure). */
    async settle(ms = 6000) {
      for (const end = Date.now() + ms; Date.now() < end; await sleep(20)) {
        if (await js("window.fw?.settled()")) { await sleep(20); if (await js("window.fw?.settled()")) return true; }
      }
      return false;
    },
    async key(k, mods = 0) {   // (mods: 1 Alt, 2 Ctrl, 4 Meta, 8 Shift)
      const named = { Enter: 13, Backspace: 8, Delete: 46, Tab: 9, ArrowLeft: 37, ArrowUp: 38, ArrowRight: 39, ArrowDown: 40, Escape: 27 }[k];
      const code = named || ({ "/": 191, "[": 219, "]": 221 }[k]) || k.toUpperCase().charCodeAt(0);
      const p = { key: k, code: named ? k : { "/": "Slash", "[": "BracketLeft", "]": "BracketRight" }[k] || `Key${k.toUpperCase()}`, windowsVirtualKeyCode: code, modifiers: mods };
      await cdp("Input.dispatchKeyEvent", { type: "rawKeyDown", ...p });
      await cdp("Input.dispatchKeyEvent", { type: "keyUp", ...p });
    },
    type: (text) => cdp("Input.insertText", { text }),
    async click(x, y) { for (const type of ["mousePressed", "mouseReleased"]) await cdp("Input.dispatchMouseEvent", { type, x, y, button: "left", clickCount: 1 }); },
    /** The page at `hash` (a pericope: its editor the one open; home: its waiting pericope and search box), settled. */
    async open(hash) {
      await cdp("Page.navigate", { url: `http://127.0.0.1:${port}/?test${hash}` });
      const id = hash.match(/^#\/p\/([^@]+)/)?.[1];
      await until(id ? `window.fw?.editor()?.id === "${id}"` : hash === "#/keys" ? `!!document.querySelector(".fw-keyrow")`
        : `!!document.querySelector(".fw-search .fw-input") && window.fw?.home() && !window.fw.editor()?.id`, 6000);
      return t.settle();
    },
    select: (text, o = {}) => js(`window.fw.select(${JSON.stringify(text)}, ${JSON.stringify(o)})`),
    /** The cursor at the very end of the open pericope (a pericope opens at its top since 2026-11-18). */
    end: () => js(`window.fw.end()`),
    get: async (path) => (await fetch(`http://127.0.0.1:${port}${path}`)).json(),
    kids: async (id) => (await t.get(`/api/pericope/${id}`)).children,
    async shot(file) {
      if (!SHOTS) return;
      const { result } = await cdp("Page.captureScreenshot", { format: "png" });
      writeFileSync(join(SHOTS, file), Buffer.from(result.data, "base64"));
    },
  };
  for (let n = 0; n < 200; n++) { try { await fetch(`http://127.0.0.1:${port}/api/stamp`); break; } catch { await sleep(25); } }
  const t0 = Date.now();
  try { await fn(t); } catch (e) { t.check("no error", false, e.stack.split("\n").slice(0, 3).join(" / ")); }
  if (thrown.length) t.check("the page threw nothing", false, thrown.join(" | "));
  close();
  server.kill();
  rmSync(dir, { recursive: true, force: true });
  return { name, ok, out, ms: Date.now() - t0 };
}

// --- the scenarios -----------------------------------------------------------------------------------------
const scenarios = {
  async visit(t) {   // opening a pericope and leaving it changes nothing (the sweep found it could: 2026-11-18)
    await t.open(`#/p/${S0}`);
    await t.open("#/");
    const c = (await t.kids(S0))[0];
    t.check("a pericope visited and left: unchanged (a container holding one block kept, its ids)", c.t === "container" && c.id === S1 && c.children[0].id === S2,
      JSON.stringify(c));
  },

  async deleting(t) {   // a pericope deleted, from home and from inside it; asked first, in the page
    await t.open("#/");
    await t.key("ArrowDown");   // (out of home's waiting pericope, into the search)
    await t.type("beta");
    await t.until(`[...document.querySelectorAll(".fw-row.fw-sel")].some(r => r.innerText.includes("beta"))`, 2000);
    await t.key("Backspace", 4);   // ⌘⌫
    t.check("home: ⌘⌫ on a pericope: asked first, in the page", await t.until(`document.querySelector(".fw-ask")?.innerText.includes("delete “beta”")`, 1000));
    await t.key("n");
    await t.settle();
    t.check("  anything but y or ↵: kept", (await t.get("/api/home")).rows.some((r) => r.key === B));
    await t.js(`document.querySelector(".fw-search .fw-input").focus(); 1`);
    await t.key("Backspace", 4);
    await t.until(`!!document.querySelector(".fw-ask")`, 1000);
    await t.key("y");
    await t.settle();
    t.check("  y: deleted; its quote elsewhere keeps its last text", !(await t.get("/api/home")).rows.some((r) => r.key === B)
      && (await t.kids(A))[1].t === "text" && (await t.kids(A))[1].text === "beta's words");
    await t.open(`#/p/${T}@${T1}`);
    await t.key("Backspace", 12);   // ⌘⇧⌫
    await t.until(`!!document.querySelector(".fw-ask")`, 1000);
    await t.key("Enter");
    await t.settle();
    t.check("inside one: ⌘⇧⌫, ↵: deleted, and home", !(await t.get("/api/home")).rows.some((r) => r.key === T) && await t.until(`window.fw.home()`, 2000));
  },

  async bindings(t) {   // the keys page: a command given other keys, which then work; the browser's own refused; the default back
    await t.open("#/keys");
    t.check("the keys page: every command, its key", await t.until(`document.querySelectorAll(".fw-keyrow").length > 10 && document.body.innerText.includes("⌘E")`, 2000));
    await t.js(`document.querySelector('.fw-keyrow[data-id="popout"]').focus(); 1`);
    await t.key("Enter");
    await t.key("j", 5);   // ⌘⌥J
    await t.settle();
    t.check("  Enter, then keys: its new key, kept by the core", (await t.get("/api/keys")).keys.popout === "Mod-Alt-j"
      && await t.until(`document.querySelector('.fw-keyrow[data-id="popout"]').innerText.includes("⌘⌥J")`, 1000));
    await t.js(`document.querySelector('.fw-keyrow[data-id="link"]').focus(); 1`);
    await t.key("Enter");
    await t.key("t", 4);   // ⌘T: the browser's
    t.check("  a key the browser keeps: refused, saying so", await t.until(`document.querySelector(".fw-foot").innerText.includes("browser keeps")`, 1000)
      && !(await t.get("/api/keys")).keys.link);
    await t.open(`#/p/${A}@${A1}`);
    await t.key("j", 5);   // the new key
    await t.settle();
    t.check("  the new key works in the editor", (await t.kids(A))[0].t === "quote");
    await t.open("#/keys");
    await t.js(`document.querySelector('.fw-keyrow[data-id="popout"]').focus(); 1`);
    await t.key("Backspace");
    await t.settle();
    t.check("  Backspace: the default again", !(await t.get("/api/keys")).keys.popout);
  },

  async home(t) {
    await t.open("#/");
    t.check("home: the pericopes listed", await t.until(`document.body.innerText.includes("alpha") && document.body.innerText.includes("beta")`));
    await t.key("ArrowDown");   // (out of the waiting pericope, into the search)
    await t.type("bet");
    t.check("  typing: what the search service will add is shown coming", await t.until(`!!document.querySelector(".fw-results .fw-pending")`, 1000));
    t.check("    gone once its answer's in", await t.until(`!document.querySelector(".fw-results .fw-pending")`, 3000));
    t.check("  typing searches", await t.until(`[...document.querySelectorAll(".fw-row")].some(r => r.innerText.includes("beta") && r.classList.contains("fw-sel"))`));
    t.check("  the results over the page, the garden still behind them", await t.js(`document.querySelector("#main").classList.contains("fw-searching") && document.querySelectorAll(".fw-home-page .fw-card").length > 0`));
    await t.key("Escape");
    const n = (await t.get("/api/home")).library.length;
    t.check("below the garden, the library: every pericope, a line each", await t.until(`document.querySelectorAll(".fw-library .fw-row").length === ${n}`, 1000) && n >= 7);
    for (let k = 0; k < 12; k++) await t.key("ArrowDown");
    t.check("  ↓ through the garden into the library", await t.js(`!!document.querySelector(".fw-library .fw-sel")`));
    await t.key("Enter");
    t.check("  ↵ there opens it", await t.until(`!!window.fw.editor()?.id && !window.fw.home()`, 2000));
    await t.shot("home.png");
  },

  async waiting(t) {   // home (2026-11-19): a waiting pericope in the middle, the search and garden below it; typed in, it's made
    const entries = async () => (await t.get("/api/home")).library.map((l) => l.key).sort().join(" ");
    const before = await entries();
    await t.open("#/");
    const box = await t.js(`(() => { const h = document.querySelector(".fw-waiting .fw-header").getBoundingClientRect(),
      d = document.querySelector(".fw-waiting .fw-doc").getBoundingClientRect(), s = document.querySelector(".fw-search").getBoundingClientRect(),
      g = document.querySelector(".fw-home-page .fw-card")?.getBoundingClientRect();
      return { mid: (h.top + d.bottom) / 2, search: s.top, card: g && g.top, h: innerHeight }; })()`);
    t.check("home: an empty, untitled pericope in the middle of the first screen", box && Math.abs(box.mid - box.h / 2) < box.h / 6
      && await t.js(`window.fw.editor() && !window.fw.editor().id && document.querySelector(".fw-waiting .fw-title").value === ""`), JSON.stringify(box));
    t.check("  the cursor in it", await t.js(`!!document.activeElement.closest(".fw-waiting .ProseMirror")`));
    t.check("  below it the search and the garden, from near the bottom of the screen and off it", box.search > box.h * 0.6 && box.search < box.h
      && box.card > box.search && await t.js(`document.querySelectorAll(".fw-library .fw-row").length >= 7`), JSON.stringify(box));
    t.check("  nothing selected in the garden while you're in the pericope", await t.js(`!document.querySelector(".fw-sel")`));
    await t.shot("home-open.png");
    await t.js(`document.querySelector(".fw-home-page .fw-card").scrollIntoView({ block: "start" }); 1`);
    await t.shot("home-garden.png");
    await t.key("ArrowDown");
    t.check("↓ past its end: the search, its first row selected", await t.js(`document.activeElement === document.querySelector(".fw-search .fw-input")
      && !!document.querySelector(".fw-home-page .fw-sel")`));
    await t.key("ArrowUp");
    t.check("  ↑ from the search's top: back into the pericope", await t.js(`!!document.activeElement.closest(".fw-waiting .ProseMirror") && !document.querySelector(".fw-sel")`));
    await t.open(`#/p/${A}`);
    await t.open("#/");
    await t.settle();
    t.check("opening home and leaving it, and back: nothing written", (await entries()) === before);
    await t.js(`window.__view = window.fw.editor().view; window.__n = history.length; 1`);
    const span = `(() => { const h = document.querySelector(".fw-centre .fw-header").getBoundingClientRect(), d = document.querySelector(".fw-centre .fw-doc").getBoundingClientRect();
      return { top: h.top, bottom: d.bottom, mid: (h.top + d.bottom) / 2, y: scrollY }; })()`;
    const was = await t.js(span);
    await t.type("q");
    t.check("typed in: the search, garden and library gone at once", await t.js(`!document.querySelector(".fw-search, .fw-home-page, .fw-library, .fw-waiting")`));
    const now = await t.js(span);
    t.check("  the pericope still where it was, in the middle (no jump to the top)", Math.abs(now.mid - was.mid) < 12 && now.y === 0, JSON.stringify([was, now]));
    const words = "uick, a note typed fast while the pericope is being made";
    for (const ch of words) await t.type(ch);
    await t.settle();
    const made = await t.js(`window.fw.editor().id`);
    t.check("  made in the store, the address its own, replaced (no new place), the editor the same one", !!made
      && await t.js(`location.hash === "#/p/${made}" && window.fw.editor().view === window.__view && history.length === window.__n`),
      await t.js(`location.hash + " " + history.length + "/" + window.__n`));
    const one = await t.js(span);
    for (const line of ["two", "three", "four"]) { await t.key("Enter"); for (const ch of line) await t.type(ch); }
    await t.settle();
    const grown = await t.js(span);
    t.check("  growing, it grows from the centre: its top up, its bottom down, its middle kept", grown.top < one.top - 20 && grown.bottom > one.bottom + 20
      && Math.abs(grown.mid - one.mid) < 12 && grown.y === 0, JSON.stringify([one, grown]));
    for (let i = 0; i < ["two", "three", "four"].join("").length + 3; i++) await t.key("Backspace");   // (the three lines and their three Enters, taken back)
    await t.settle();
    const k = made && await t.kids(made);
    t.check("  everything typed kept, whole", k && k.length === 1 && k[0].text === "q" + words, JSON.stringify(k));
    t.check("  the cursor still at the end of it", await t.js(`(() => { const v = window.fw.editor().view; return v.hasFocus() && v.state.selection.from === v.state.doc.content.size - 1; })()`));
    await t.shot("home-typed.png");
    await t.key("Enter", 12);   // ⌘⇧↵: sent away
    t.check("⌘⇧↵ on it: home again, a fresh waiting pericope and the garden", await t.until(`window.fw.home() && !window.fw.editor()?.id
      && !!document.querySelector(".fw-waiting .ProseMirror") && !!document.querySelector(".fw-home-page .fw-card") && location.hash === "#/"`, 3000));
    await t.settle();
    t.check("  what was sent away is in the store, unchanged", (await t.kids(made))[0].text === "q" + words);
    await t.key("[", 4);
    t.check("  ⌘[: back to it", await t.until(`window.fw.editor()?.id === "${made}" && !window.fw.home()`, 3000));
  },

  async away(t) {   // send it away (⌘⇧↵): from a pericope, saved and home; ⌘[ reaches it; a blank one: nothing
    await t.open(`#/p/${T}`);
    await t.end();
    await t.type(" and away");
    await t.key("Enter", 12);   // (at once: nothing waited for)
    t.check("a pericope sent away (⌘⇧↵): home", await t.until(`window.fw.home() && !window.fw.editor()?.id && location.hash === "#/"`, 3000));
    await t.settle();
    const k = await t.kids(T);
    t.check("  what was typed just before, saved", k[1].text === "jumps over the dog and away", JSON.stringify(k));
    await t.key("[", 4);
    t.check("  ⌘[: back to what was sent away", await t.until(`window.fw.editor()?.id === "${T}"`, 3000));
    await t.key("]", 4);
    t.check("  ⌘]: home again", await t.until(`window.fw.home()`, 3000));
    await t.settle();
    const n = (await t.get("/api/home")).library.length;
    await t.key("Enter", 12);
    await t.settle();
    t.check("home's waiting pericope, blank: nothing sent, nothing made", await t.js(`window.fw.home() && location.hash === "#/"
      && document.querySelector(".fw-status").innerText.includes("nothing here")`) && (await t.get("/api/home")).library.length === n);
    await t.open("#/keys");
    t.check("its key on the keys page", await t.until(`document.querySelector('.fw-keyrow[data-id="done"]')?.innerText.includes("⌘⇧↵")
      && document.querySelector('.fw-keyrow[data-id="done"]').innerText.includes("Send it away")`, 2000));
    // the slide (on by default; off in ?test, so ?motion here): caught mid-way
    await t.cdp("Page.navigate", { url: `http://127.0.0.1:${t.port}/?test&motion#/p/${T}` });
    await t.until(`window.fw?.editor()?.id === "${T}"`, 6000);
    await t.settle();
    await t.key("Enter", 12);
    const mid = await t.until(`(() => { const a = document.querySelector("#main").getAnimations()[0]; if (!a) return false;
      a.pause(); a.currentTime = 150; return new DOMMatrix(getComputedStyle(document.querySelector("#main")).transform).m42 < -20; })()`, 1000);
    await t.shot("send-away-mid.png");   // (held mid-way for the picture, then let go)
    await t.js(`document.getAnimations().forEach((a) => a.play()); 1`);
    t.check("  sliding up off the top (with motion), then home", mid && await t.until(`window.fw.home() && getComputedStyle(document.querySelector("#main")).transform === "none"`, 3000));
  },

  async typing(t) {
    await t.open(`#/p/${A}`);
    await t.end();
    t.check("a pericope open: its blocks, the quote drawn with what it shows",
      await t.js(`document.body.innerText.includes("first words") && document.querySelector(".fw-quote")?.innerText.includes("beta's words")`));
    t.check("  the header", await t.js(`document.querySelector(".fw-label").innerText === "block" && document.querySelector(".fw-title").value === "alpha"`));
    await t.type("written in the browser");   // (it opens below the quote: a block of its own to write in)
    t.check("  typed: on the page as soon as the key's handled", await t.js(`document.querySelector(".fw-doc").innerText.includes("written in the browser")`));
    await t.key("Enter", 8);   // Shift+Enter: a line break in the block
    await t.type("its second line");
    await t.key("Enter");      // Enter: a new block
    await t.type("another block");
    await t.settle();
    const k = await t.kids(A);
    t.check("  saved once the keys stop: a block below the quote, its two lines; then another",
      k.length === 4 && k[2].text === "written in the browser\nits second line" && k[3].text === "another block", JSON.stringify(k.map((c) => c.text || c.t)));
    await t.select("another block", { collapse: true, start: true });
    await t.key("Backspace");
    await t.settle();
    const k2 = await t.kids(A);
    t.check("Backspace at a block's start merges it into the one above", k2.length === 3 && k2[2].text === "written in the browser\nits second lineanother block",
      JSON.stringify(k2.map((c) => c.text || c.t)));
    await t.shot("pericope.png");
  },

  async through(t) {
    await t.open(`#/p/${A}`);
    await t.end();
    await t.key("ArrowUp");   // (from the block below it)
    t.check("edit-through: the arrows select the quote whole", await t.until(`!!document.querySelector(".fw-quote.ProseMirror-selectednode")`, 1000));
    await t.key("ArrowUp");
    t.check("  the same arrow again: into it", await t.until(`!!document.querySelector(".fw-quote.fw-in")`, 1000));
    await t.type(" and more");
    await t.settle();
    t.check("  typed there: saved into the quoted pericope", (await t.kids(B))[0].text === "beta's words and more");
    await t.key("Escape");
    t.check("  Esc: out a level, the quote selected whole (it shows one block: that block's box is the quote's)",
      await t.until(`!document.querySelector(".fw-quote.fw-in") && !!document.querySelector(".fw-quote.ProseMirror-selectednode")`, 1000));
    await t.key("Enter");
    await t.type("after the quote");
    await t.settle();
    t.check("  Enter on it: a new block below; saved (the pericope's base kept up, not refused)",
      (await t.kids(A)).some((c) => c.text === "after the quote") && !(await t.js(`document.querySelector("#bar-left").innerText.includes("not saved")`)));
    await t.js(`document.querySelector(".fw-open").dispatchEvent(new MouseEvent("mousedown", {bubbles: true})); 1`);
    t.check("Open it on the quote (its ↗): its source opened", await t.until(`window.fw.editor()?.id === "${B}" && document.body.innerText.includes("beta's words")`));
    t.check("  its header says what points at it", await t.until(`/\\d · \\d quotes?/.test(document.querySelector(".fw-fields")?.innerText)`));
  },

  async slash(t) {
    await t.open(`#/p/${A}`);
    await t.type("/");
    t.check("/ at a line's start: the menu, at the cursor", await t.until(`document.querySelector(".fw-menu")?.innerText.includes("Quote a block")`, 1000));
    await t.key("Enter");
    t.check("  Quote a block: a search", await t.until(`document.querySelector(".fw-menu")?.innerText.includes("quote ›")`, 2000));
    await t.type("beta");
    await t.until(`[...document.querySelectorAll(".fw-menu .fw-row.fw-sel")].some(r => r.innerText.includes("beta"))`, 2000);
    await t.key("Enter");
    await t.settle();
    t.check("  Enter: quoted here, saved", (await t.kids(A)).filter((c) => c.t === "quote" && c.target === B).length === 2,
      JSON.stringify((await t.kids(A)).map((c) => c.t)));
    await t.type("/");
    await t.key("Enter");
    await t.until(`!!document.querySelector(".fw-menu input")`, 2000);
    await t.type("fresh idea");
    await t.until(`[...document.querySelectorAll(".fw-menu .fw-row")].some(r => r.innerText.includes("+ new pericope “fresh idea”"))`, 2000);
    await t.key("ArrowUp");
    await t.key("Enter");
    t.check("  + new pericope: made, quoted here, and you're in it", await t.until(`!!document.activeElement?.closest(".fw-quote") && !!document.querySelector(".fw-quote.fw-in")`, 4000));
    await t.type("written in the new one");
    await t.settle();
    const home = await t.get("/api/home");
    t.check("    written there: saved into it, not into the pericope around it",
      home.rows.some((x) => x.title === "fresh idea" && x.preview.some((y) => y.text?.includes("written in the new one"))) && !(await t.kids(A)).some((c) => c.text === "written in the new one"));
    await t.key("Escape"); await t.key("Escape");
    await t.key("Enter");
    await t.type("/xyz");
    t.check("  what matches no command is just text", await t.until(`!document.querySelector(".fw-menu") && document.querySelector(".fw-doc").innerText.includes("/xyz")`, 1000));
    await t.shot("menu.png");
  },

  async actions(t) {
    await t.open(`#/p/${A}@${A1}`);
    await t.key("e", 4);   // ⌘E: Turn into a quote
    await t.settle();
    t.check("⌘E: the block a pericope of its own, quoted where it was", (await t.kids(A))[0].t === "quote" && (await t.kids(A))[0].title === "first words");
    await t.key("z", 4);   // ⌘Z: the action taken back, in the store too
    await t.settle();
    t.check("  ^Z: taken back, in the store too", (await t.kids(A))[0].text === "first words");
    await t.key("y", 4);   // ⌘Y
    await t.settle();
    t.check("  ^Y: done again", (await t.kids(A))[0].t === "quote");
    await t.open(`#/p/${A}@${QA}`);
    await t.key("/", 4);   // ⌘/
    t.check("⌘/ on a quote: the menu, what fits there", await t.until(`document.querySelector(".fw-menu")?.innerText.includes("Turn into text") && document.querySelector(".fw-menu").innerText.includes("Lock writing through")`, 1000));
    await t.type("lock");
    await t.key("Enter");
    await t.settle();
    t.check("  typed to filter, Enter: locked, and the menu stays, saying so", (await t.kids(A))[1].lock === true
      && await t.until(`document.querySelector(".fw-menu")?.innerText.includes("Unlock writing through")`, 2000));
    await t.open(`#/p/${R}@${QR1}`);
    await t.key("t", 5);   // ⌘⌥T: Turn into text
    await t.settle();
    const k = await t.kids(R);
    t.check("⌘⌥T: the quote turned into text, a plain copy", k[1].t === "text" && k[1].text === "beta's words");
    t.check("  the quote beside it drawn again with what it shows", await t.until(`[...document.querySelectorAll(".fw-doc > .ProseMirror > .fw-quote")].every(q => q.innerText.includes("quick brown"))`, 2000));
  },

  async links(t) {
    await t.open(`#/p/${A}@${A1}`);
    t.check("(the cursor put on \"words\")", await t.select("words"));
    await t.key("k", 4);   // ⌘K
    await t.until(`document.querySelector(".fw-menu")?.innerText.includes("link ›")`, 2000);
    await t.type("beta");
    await t.until(`[...document.querySelectorAll(".fw-menu .fw-row.fw-sel")].some(r => r.innerText.includes("beta"))`, 2000);
    await t.key("Enter");
    await t.settle();
    t.check("⌘K on a selection: linked to the pericope picked, in the store", JSON.stringify((await t.kids(A))[0].links.map((l) => [l.to, l.at])) === JSON.stringify([[B, [6, 11]]]),
      JSON.stringify((await t.kids(A))[0].links));
    t.check("  drawn as a link", await t.until(`document.querySelector(".fw-doc .fw-link")?.textContent === "words"`, 2000));
    await t.select("or", { collapse: true });
    await t.key("o", 4);   // ⌘O on it
    t.check("  ⌘O on it: the pericope it links to", await t.until(`window.fw.editor()?.id === "${B}"`, 3000));
    await t.open(`#/p/${A}@${A1}`);
    await t.select("or", { collapse: true });
    await t.key("K", 12);   // ⌘⇧K (with Shift, a browser says "K")
    await t.settle();
    t.check("⌘⇧K in it: the link removed, the text kept", (await t.kids(A))[0].links.length === 0 && (await t.kids(A))[0].text === "first words"
      && await t.until(`!document.querySelector(".fw-doc .fw-link")`, 2000));
  },

  async blocks(t) {
    await t.open(`#/p/${R}@${R1}`);
    await t.key("Escape");
    t.check("Esc in a block of text: it selected whole, drawn bright", await t.until(`document.querySelectorAll(".fw-doc > .ProseMirror > .fw-picked").length === 1`, 1000));
    await t.key("ArrowDown", 8);   // Shift+↓
    t.check("  Shift+↓: the next block too", await t.until(`document.querySelectorAll(".fw-doc > .ProseMirror > .fw-picked").length === 2`, 1000));
    await t.key("Backspace");
    await t.settle();
    t.check("  Backspace: both gone, from the store too", (await t.kids(R)).length === 1, JSON.stringify((await t.kids(R)).map((c) => c.t)));
    await t.open(`#/p/${B}@${B1}`);
    const nb = await t.js(`(() => { const r = document.querySelector(".fw-doc > .ProseMirror > *").getBoundingClientRect(); return [r.left - 36, r.top + 12]; })()`);   // (its number, in the gutter)
    await t.click(nb[0], nb[1]);
    t.check("a click on a block's number: it selected whole", await t.until(`document.querySelector(".fw-doc > .ProseMirror > *").matches(".fw-picked")`, 1000));
    await t.type("replaced");
    await t.settle();
    t.check("  typing over it: a new block, what's typed", (await t.kids(B)).map((c) => c.text).join("|") === "replaced", JSON.stringify(await t.kids(B)));
    await t.open(`#/p/${M}`);   // (it ends with a quote: an empty block below it, to write in)
    await t.end();
    await t.key("Backspace");
    await t.settle();
    t.check("Backspace in an empty block: it goes, the quote above selected, not taken",
      (await t.kids(M)).length === 1 && await t.js(`!!document.querySelector(".fw-quote.ProseMirror-selectednode")`));
  },

  async masking(t) {
    await t.open(`#/p/${M}@${QM}`);
    await t.key("M", 12);   // ⌘⇧M: masking
    t.check("⌘⇧M on a quote: masking, its whole text", await t.until(`document.querySelector(".fw-masking")?.innerText.includes("jumps over the dog")`, 3000));
    await t.js(`(() => {   // "quick brown" selected in the masking view (not ProseMirror: the page's own selection)
      const piece = [...document.querySelectorAll(".fw-masking [data-off]")].find(s => s.textContent.includes("the quick brown fox"));
      const x = piece.firstChild, at = x.textContent.indexOf("quick");
      const r = document.createRange(); r.setStart(x, at); r.setEnd(x, at + "quick brown".length);
      const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r); return true; })()`);
    const caret = `(() => { const s = window.getSelection(); return s.focusNode?.parentElement?.closest(".fw-masking") ? s.focusNode.parentElement.textContent + "|" + s.focusOffset : null; })()`;
    await t.key("ArrowDown");
    const down = await t.js(caret);
    t.check("  ↓ moves the caret in masking (the page doesn't take it), still masking", down && !down.startsWith("the quick brown fox") && await t.js(`!!document.querySelector(".fw-masking")`), down);
    await t.key("ArrowUp");
    t.check("  ↑ back", (await t.js(caret))?.startsWith("the quick brown fox"), await t.js(caret));
    const at = await t.js(`(() => { const piece = [...document.querySelectorAll(".fw-masking [data-off]")].find(s => s.textContent.includes("jumps over"));
      const r = document.createRange(); r.setStart(piece.firstChild, 6); r.setEnd(piece.firstChild, 7); const b = r.getBoundingClientRect(); return [b.left + 1, b.top + b.height / 2]; })()`);
    await t.click(at[0], at[1]);
    await t.settle();
    t.check("  a click in its text: the caret there, still masking", await t.js(`!!document.querySelector(".fw-masking")`) && (await t.js(caret))?.startsWith("jumps over"), await t.js(caret));
    await t.js(`(() => {   // "quick brown" selected again
      const piece = [...document.querySelectorAll(".fw-masking [data-off]")].find(s => s.textContent.includes("the quick brown fox"));
      const x = piece.firstChild, at = x.textContent.indexOf("quick");
      const r = document.createRange(); r.setStart(x, at); r.setEnd(x, at + "quick brown".length);
      const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r); return true; })()`);
    const qx = `(() => { const w = document.createTreeWalker(document.querySelector(".fw-masking"), NodeFilter.SHOW_TEXT);
      for (let n; (n = w.nextNode());) { const i = n.data.indexOf("quick"); if (i >= 0) { const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + 1); return Math.round(r.getBoundingClientRect().left); } } })()`;
    const before = await t.js(qx);
    await t.key("[");
    t.check("  marking never moves the text (the brackets take no room)", await t.until(`document.querySelectorAll(".fw-masking .fw-br").length === 2`, 2000) && (await t.js(qx)) === before,
      JSON.stringify([before, await t.js(qx)]));
    t.check("  [ on a selection: just it shows, the rest dim, in brackets", await t.until(`[...document.querySelectorAll(".fw-masking .fw-shown")].map(s => s.textContent).join("") === "quick brown"
      && document.querySelectorAll(".fw-masking .fw-br").length === 2`, 2000), await t.js(`document.querySelector(".fw-masking")?.innerText`));
    await t.key("Escape");
    await t.settle();
    const q = (await t.kids(M))[0], shown = q.body.map((b) => b.text).join(" ");
    t.check("  Esc: finished, the mask saved; the quote shows just that", q.masked && shown.includes("quick brown") && !shown.includes("jumps"), JSON.stringify(q.body));
    t.check("    drawn so: …quick brown…", await t.until(`document.querySelector(".fw-doc .fw-quote")?.innerText.includes("quick brown") && document.querySelector(".fw-doc .fw-quote").innerText.includes("…")`, 2000));
    t.check("(the cursor after \"brown\", in the quote)", await t.select("brown", { collapse: true }));
    await t.type(" red");   // (written through the mask, the lens)
    await t.settle();
    const tk = await t.kids(T);
    t.check("  written through the mask: the source changed, what's hidden kept", tk[0].text === "the quick brown red fox" && tk[1].text === "jumps over the dog", JSON.stringify(tk.map((c) => c.text)));
    await t.js(`window.fw.editor().view.focus(); 1`);
    await t.key("z", 4);
    await t.settle();
    t.check("  ^Z (in the pericope): the mask taken back", !(await t.kids(M))[0].masked);
    await t.shot("masking.png");
  },

  async paraphrase(t) {
    await t.open(`#/p/${M}@${QM}`);
    await t.key("/", 4);
    await t.until(`document.querySelector(".fw-menu")?.innerText.includes("Paraphrase it")`, 2000);
    await t.type("paraphrase it");
    await t.key("Enter");
    await t.settle();
    t.check("Paraphrase it on a quote: an empty paraphrase of what it quoted in its place", (await t.kids(M))[0].t === "text" && (await t.kids(M))[0].para?.id === T);
    t.check("  drawn red, ≈ its source; the source dim inside", await t.until(`document.querySelector(".fw-doc .fw-para")?.dataset.para === "≈ fox" && document.querySelector(".fw-doc .fw-guide")?.innerText.includes("quick brown")`, 2000));
    await t.type("a fox, quick");
    await t.settle();
    t.check("  written in: your words, the dim source gone", (await t.kids(M))[0].text === "a fox, quick" && await t.until(`!document.querySelector(".fw-doc .fw-guide")`, 2000));
    await t.key("/", 4);
    await t.until(`document.querySelector(".fw-menu")?.innerText.includes("Not a paraphrase")`, 2000);
    await t.type("not a para");
    await t.key("Enter");
    await t.settle();
    t.check("Not a paraphrase: your words stay, no longer pointing", (await t.kids(M))[0].text === "a fox, quick" && !(await t.kids(M))[0].para);
  },

  async nesting(t) {
    await t.open(`#/p/${B}@${B1}`);
    await t.select("beta's", { collapse: true });
    await t.key("Enter", 4);   // ⌘↵ after "beta's": the rest in a new block, inside
    await t.type("inside");
    await t.settle();
    const c = (await t.kids(B))[0];
    t.check("⌘↵: a block inside the block (it a container, keeping its id)", c.t === "container" && c.id === B1 && c.children.map((x) => x.text).join("|") === "beta's|inside words",
      JSON.stringify(c));
    await t.select("words", { collapse: true });
    await t.key("Enter");
    await t.key("Enter");   // (an empty block inside: Enter steps it out)
    await t.type("after it");
    await t.settle();
    const k = await t.kids(B);
    t.check("  Enter on an empty block inside: out a level, after the container", k.length === 2 && k[1].t === "text" && k[1].text === "after it", JSON.stringify(k.map((x) => x.t + ":" + (x.text || ""))));
  },

  async selectionQuote(t) {
    await t.open(`#/p/${T}@${T1}`);
    await t.select("quick brown");
    await t.key("e", 4);   // ⌘E on a selection
    await t.settle();
    const c = (await t.kids(T))[0];
    t.check("⌘E on a selection: just it, a pericope of its own, quoted in the middle of its block (a container now, its id kept)",
      c.t === "container" && c.id === T1 && c.children.map((x) => x.t + ":" + (x.text ?? x.title)).join("|") === "text:the |quote:quick brown|text: fox",
      JSON.stringify(c));
  },

  async review(t) {   // (a model's guesses beside the store, as a model outside fw writes them: alpha and beta might be poems)
    await t.open(`#/p/${K}`);
    t.check("a kind's header: its maybes, to review", await t.until(`[...document.querySelectorAll(".fw-field")].some(f => f.innerText.includes("2 · ↵ review them"))`, 2000),
      await t.js(`document.querySelector(".fw-fields")?.innerText`));
    await t.js(`[...document.querySelectorAll(".fw-chip")].find(c => c.innerText.includes("review them")).click(); 1`);
    await t.settle();
    t.check("  reviewing: the first maybe, where it lives; the bar asks", await t.until(`window.fw.editor()?.id === "${A}" && document.querySelector("#bar-left").innerText.includes("is “alpha” one?")`, 3000),
      await t.js(`document.querySelector("#bar-left").innerText`));
    await t.key("Enter");   // yes
    await t.settle();
    t.check("  Enter: yes; the next", await t.until(`window.fw.editor()?.id === "${B}"`, 3000));
    await t.key("Backspace");   // no
    await t.settle();
    const answers = async (id) => (await t.get(`/api/pericope/${id}`)).kindTokens.map((x) => x.mark).join(",");
    t.check("  Backspace: no; done, back on the kind, saying how it went", await t.until(`window.fw.editor()?.id === "${K}" && document.querySelector("#bar-left").innerText.includes("reviewed: 1 yes, 1 no")`, 3000)
      && (await answers(A)) === "yes" && (await answers(B)) === "no", `${await answers(A)} / ${await answers(B)}`);
  },

  async clipboard(t) {   // (headless Chrome has no system clipboard: real copy, cut and paste events, each with its own data)
    const fire = (type, text = null) => t.js(`(() => {
      const dt = new DataTransfer(); ${text === null ? "" : `dt.setData("text/plain", ${JSON.stringify(text)});`}
      document.activeElement.dispatchEvent(new ClipboardEvent("${type}", { clipboardData: dt, bubbles: true, cancelable: true }));
      return dt.getData("text/plain"); })()`);
    await t.open(`#/p/${R}@${R1}`);
    await t.key("Escape");
    const copied = await fire("copy");
    await t.settle();
    const clip = await t.get("/api/clip");
    t.check("blocks selected whole, copied: their text on the clipboard, fw's clip kept", copied === "r words" && clip.blocks?.[0]?.id === R1 && !clip.cut, JSON.stringify(clip));
    await t.open(`#/p/${R}`);   // (at the end: below its last quote, a block to write in)
    await t.end();
    await fire("paste", "r words");
    await t.settle();
    const k = await t.kids(R);
    t.check("  pasted: a live quote of it", k[k.length - 1].t === "quote" && k[k.length - 1].target === R1, JSON.stringify(k.map((c) => c.t + ":" + (c.target || c.text))));
    const where = `(() => { const e = window.fw.editor(), s = e.view.state.selection.toJSON();
      const a = document.activeElement, q = a?.closest?.(".fw-quote");
      return { sel: s.type, from: s.anchor, size: e.view.state.doc.content.size, last: e.view.state.doc.lastChild.type.name, reloads: window.fw.reloads || 0,
        focus: !a ? "none" : q ? "a quote's editor (" + (q.innerText || "").slice(0, 12) + ")" : a.matches(".ProseMirror") ? "the page's editor" : a.tagName,
        current: document.querySelector(".fw-current")?.closest(".fw-quote") ? "a quote's" : "the page's" }; })()`;
    const before = await t.js(where);
    await t.js(`(window.fwLog = [], 1)`);
    await t.key("Enter");
    const after = await t.js(where);
    const log = await t.js(`JSON.stringify(window.fwLog)`);
    await t.key("v", 12);   // ⌘⇧V: paste and match style
    const atPaste = await t.js(where);
    await fire("paste", "r words");
    await t.settle();
    const k2 = await t.kids(R);
    t.check("  ⌘⇧V: a plain copy of its text", k2[k2.length - 1].t === "text" && k2[k2.length - 1].text === "r words",
      JSON.stringify(k2.map((c) => c.t + ":" + (c.target || c.text))) + " · before Enter, after it, at the paste: " + JSON.stringify([before, after, atPaste]) + " · what Enter did: " + log);
    await t.open(`#/p/${B}@${B1}`);
    await t.key("Escape");
    await fire("cut");
    await t.settle();
    t.check("cut: gone from here, but kept by the store while the clipboard holds it", (await t.kids(B)).every((c) => c.id !== B1)
      && (await t.get(`/api/blocks?ids=${B1}`)).blocks.length === 1 && (await t.get("/api/clip")).cut === true);
    await t.open(`#/p/${A}`);   // (at the end: a block to write in)
    await t.end();
    await fire("paste", "beta's words");
    await t.settle();
    const ka = await t.kids(A);
    t.check("  pasted elsewhere: moved, the block itself (its id)", ka.some((c) => c.id === B1 && c.text === "beta's words") && (await t.kids(B)).every((c) => c.id !== B1),
      JSON.stringify(ka.map((c) => c.id.slice(-4) + ":" + (c.target || c.text))));
  },

  async title(t) {   // a title typed slowly, saves and the header's redraws landing between the keys: every key kept, the cursor never taken
    await t.open(`#/p/${T}@${T1}`);
    await t.js(`(() => { const x = document.querySelector(".fw-title"); x.focus(); x.select(); return true; })()`);
    for (const ch of "a slow title") { await t.type(ch); await sleep(60); }   // (a save 30 ms after each key here: they land between)
    t.check("a title typed slowly: still in the title, every key kept", await t.js(`document.activeElement?.classList.contains("fw-title") && document.querySelector(".fw-title").value === "a slow title"`),
      await t.js(`document.activeElement?.className + " / " + document.querySelector(".fw-title").value`));
    await t.settle();
    t.check("  saved", (await t.get(`/api/pericope/${T}`)).title === "a slow title");
    await t.js(`(() => { const x = document.querySelector(".fw-title"); x.focus(); x.select(); return true; })()`);
    await t.key("Backspace");
    await t.select("the quick", { collapse: true, start: true });
    await t.type("so ");   // (the text's save and the title's together)
    t.check("  cleared: the first line its title at once, as it's typed", await t.js(`document.querySelector(".fw-title").placeholder === "so the quick brown fox"`),
      await t.js(`document.querySelector(".fw-title").placeholder`));
    await t.settle();
    const p = await t.get(`/api/pericope/${T}`);
    t.check("  and saved: no title written, the text's", !p.title && p.shown === "so the quick brown fox", JSON.stringify([p.title, p.shown]));
    await t.js(`(() => { const x = document.querySelector(".fw-title"); x.focus(); return true; })()`);
    await t.type("left at once");
    await t.open("#/");
    t.check("  typed and left at once: kept", (await t.get(`/api/pericope/${T}`)).title === "left at once");
  },

  async trail(t) {   // ⌘O steps into a quote's source, ⌘[ steps out again, ⌘] back in; ⌘[ never leaves fw
    await t.open(`#/p/${A}`);
    t.check("the writing in the humanist sans", await t.until(`document.fonts.check('18px "Source Sans 3"') && getComputedStyle(document.body).fontFamily.includes("Source Sans 3")`, 3000));
    t.check("a pericope opens at its top: the cursor at its start", await t.js(`window.fw.editor().view.state.selection.from <= 2 && window.scrollY === 0`));
    await t.key("[", 4);   // (the first place: nowhere to step out to)
    await t.settle();
    t.check("  ⌘[ where it started: stays", await t.js(`location.hash === "#/p/${A}"`));
    await t.js(`(() => { const q = document.querySelector(".fw-doc .fw-quote"); const v = window.fw.editor().view; v.focus();
      let at = null; v.state.doc.descendants((n, pos) => { if (at === null && n.type.name === "quote") at = pos; });
      v.dispatch(v.state.tr.setSelection(window.fw.nodeSel(v.state.doc, at))); return true; })()`);
    await t.key("o", 4);
    t.check("⌘O on a quote: into its source", await t.until(`window.fw.editor()?.id === "${B}"`, 3000));
    await t.key("[", 4);
    t.check("  ⌘[: out again", await t.until(`window.fw.editor()?.id === "${A}"`, 3000));
    await t.key("]", 4);
    t.check("  ⌘]: in again", await t.until(`window.fw.editor()?.id === "${B}"`, 3000));
  },

  async boxes(t) {   // every block in a thin box; text lines up at every depth; a block selected whole: no blue selection
    const textX = (text) => `(() => { const w = document.createTreeWalker(document.querySelector(".fw-doc"), NodeFilter.SHOW_TEXT);
      for (let n; (n = w.nextNode());) if (n.data.includes(${JSON.stringify("@")})) { const r = document.createRange(); r.setStart(n, 0); r.setEnd(n, 1); return Math.round(r.getBoundingClientRect().left); }
      return null; })()`.replace(JSON.stringify("@"), JSON.stringify(text));
    await t.open(`#/p/${A}`);
    const top = await t.js(textX("first words")), inQuote = await t.js(textX("beta's words"));
    await t.open(`#/p/${S0}`);
    const nested = await t.js(textX("the only block inside"));
    t.check("text starts at one column: a top-level block's, a quote's, two boxes deep", top && top === inQuote && top === nested, JSON.stringify([top, inQuote, nested]));
    t.check("  each in a thin box, a box inside a box a step out", await t.js(`(() => { const a = document.querySelector(".fw-doc .fw-container"), b = a.querySelector(".fw-text");
      return getComputedStyle(b).borderTopWidth === "1px" && b.getBoundingClientRect().left > a.getBoundingClientRect().left; })()`));
    const active = (text) => `(() => { const here = [...document.querySelectorAll(".fw-here")].find(e => e.innerText.includes(${JSON.stringify(text)}));
      if (!here) return "none"; const c = getComputedStyle(here); return c.borderTopColor !== "rgba(0, 0, 0, 0)" && parseFloat(c.paddingTop) > 6
        && c.color === "rgb(221, 218, 211)"; })()`;   // (its box, more room, its text full: --fg)
    await t.select("the only block", { collapse: true });
    t.check("  in a block two boxes deep: drawn as a top-level one (its box, more room)", await t.until(active("the only block"), 1000), await t.js(active("the only block")));
    await t.open(`#/p/${R}`);
    await t.select("jumps over the dog", { collapse: true });
    t.check("  the block you're in: the same weight as the rest (its lines never re-break)", await t.js(`(() => {
      const here = document.querySelector(".fw-here"), rest = [...document.querySelectorAll(".fw-doc .fw-text")].find(e => !e.matches(".fw-here"));
      return getComputedStyle(here).fontWeight === getComputedStyle(rest).fontWeight; })()`));
    t.check("  in a block of a quote showing several: the same", await t.until(active("jumps over the dog"), 1000), await t.js(active("jumps over the dog")));
    t.check("    the quote around it: faint (the path), not the focus's bright red", await t.until(`(() => { const c = getComputedStyle([...document.querySelectorAll(".fw-quote")].find(q => q.innerText.includes("jumps over"))).borderTopColor;
      return c !== "rgb(215, 111, 111)" && c !== "rgba(0, 0, 0, 0)"; })()`, 1000));
    await t.open(`#/p/${A}`);
    await t.js(`(() => { const v = window.fw.editor().view; v.focus(); let at = null; v.state.doc.descendants((n, p) => { if (at === null && n.type.name === "quote") at = p; });
      v.dispatch(v.state.tr.setSelection(window.fw.nodeSel(v.state.doc, at))); return true; })()`);
    t.check("  a quote selected whole: drawn so", await t.until(`!!document.querySelector(".fw-quote.fw-chosen")`, 1000));
    await t.select("beta's words", { collapse: true });
    t.check("  then in it: only where you are is drawn (the page's selection of the quote, left behind, isn't)",
      await t.until(`!document.querySelector(".fw-chosen") && !!document.querySelector(".fw-quote:has(.fw-current) .fw-here")`, 1000));
    t.check("  a quote showing one block: its box is the block's (no second box inside)", await t.until(`(() => {
      const here = document.querySelector(".fw-quote .fw-here"), q = here.closest(".fw-quote");
      return getComputedStyle(here).borderTopColor === "rgba(0, 0, 0, 0)" && getComputedStyle(here).color === "rgb(221, 218, 211)"
        && getComputedStyle(q).borderTopColor === "rgb(215, 111, 111)"; })()`, 1000));
    await t.open(`#/p/${S0}`);
    await t.select("the only block", { collapse: true });
    await t.key("Escape");
    t.check("  selected whole (Esc): drawn so, without the browser's blue selection", await t.until(`!!document.querySelector(".fw-picked, .ProseMirror-selectednode")`, 1000)
      && await t.js(`getComputedStyle(document.querySelector(".fw-picked, .ProseMirror-selectednode").querySelector("*") || document.querySelector(".fw-picked, .ProseMirror-selectednode"), "::selection").backgroundColor === "rgba(0, 0, 0, 0)"`));
  },

  async motion(t) {   // (motion on: ?motion) ⌘O zooms in from the quote into the page; ⌘[ zooms out from the page into it
    await t.cdp("Page.navigate", { url: `http://127.0.0.1:${t.port}/?test&motion#/p/${A}` });
    await t.until(`window.fw?.editor()?.id === "${A}"`, 6000);
    await t.settle();
    await t.js(`(() => { const v = window.fw.editor().view; v.focus(); let at = null;
      v.state.doc.descendants((n, pos) => { if (at === null && n.type.name === "quote") at = pos; });
      v.dispatch(v.state.tr.setSelection(window.fw.nodeSel(v.state.doc, at))); return true; })()`);
    await t.key("o", 4);
    await t.until(`window.fw?.editor()?.id === "${B}"`, 3000);
    await t.settle();
    const into = await t.js(`window.fw.lastMove()`);
    t.check("⌘O: stepping in, the quote becoming the page's frame", into?.dir === "in" && into.from === "fw-quote" && into.to === "body", JSON.stringify(into));
    await t.key("[", 4);
    await t.until(`window.fw?.editor()?.id === "${A}"`, 3000);
    await t.settle();
    const out = await t.js(`window.fw.lastMove()`);
    t.check("  ⌘[: stepping out, the frame shrinking back into the quote", out?.dir === "out" && out.from === "body" && out.to === "fw-quote", JSON.stringify(out));
    t.check("  nothing left named after (the page as before)", await t.js(`![...document.querySelectorAll("*")].some(e => e.style.viewTransitionName)`));
  },

  async scrolling(t) {   // the cursor stays on screen: a block taller than the screen is never scrolled to as a whole
    await t.open(`#/p/${T}`);
    await t.select("the quick brown fox", { collapse: true });
    for (let k = 0; k < 45; k++) { await t.key("Enter", 8); await t.type(`line ${k}`); }   // (⇧↵: one block, 46 lines)
    await t.settle();
    const onScreen = `(() => { const v = window.fw.editor().view, c = v.coordsAtPos(v.state.selection.head); return c.top >= 0 && c.bottom <= innerHeight; })()`;
    await t.open(`#/p/${T}@${T1}`);
    t.check("opened at a block taller than the screen: the cursor on screen (at its start)", await t.js(onScreen),
      await t.js(`JSON.stringify([window.fw.editor().view.coordsAtPos(window.fw.editor().view.state.selection.head).top, innerHeight, scrollY])`));
    await t.select("line 44", { collapse: true });
    await t.key("ArrowDown");
    await t.settle();
    t.check("  ↓ out of its last line into the next block: the cursor still on screen", await t.js(onScreen) && await t.js(`window.fw.editor().context().block?.id === "${T2}"`));
    await t.key("ArrowUp");
    await t.settle();
    t.check("  ↑ back into it, at its last line: on screen", await t.js(onScreen) && await t.js(`window.fw.editor().context().block?.id === "${T1}"`));
  },

  async maskNested(t) {   // a quote inside the quote being masked: drawn in full while masking, and after (not a stand-in)
    await t.open(`#/p/${N}@${QN}`);
    await t.key("M", 12);
    t.check("masking a quote that holds a quote: the inner one drawn in full", await t.until(`!!document.querySelector(".fw-masking .fw-quote.fw-unit")?.innerText.includes("beta's words")`, 3000),
      await t.js(`document.querySelector(".fw-masking")?.innerText`));
    await t.js(`(() => { const piece = [...document.querySelectorAll(".fw-masking [data-off]")].find(s => s.textContent.includes("first words"));
      const x = piece.firstChild, r = document.createRange(); r.setStart(x, 0); r.setEnd(x, "first".length);
      const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r); return true; })()`);
    await t.key("]");   // ("first" hidden; the rest, the quote inside too, shown)
    await t.key("Escape");
    await t.settle();
    t.check("  masked: the quote inside still drawn in full, as a quote (not a one-line stand-in)",
      await t.until(`!!document.querySelector(".fw-doc .fw-quote .fw-quote")?.innerText.includes("beta's words") && !document.querySelector(".fw-rawline")`, 2000),
      await t.js(`document.querySelector(".fw-doc .fw-quote")?.innerText`));
  },

  async arrowFlow(t) {   // the arrows flow through quotes inside quotes; a quote reached from outside is selected whole first
    // (nested: a quote of alpha [first words, a quote of beta [beta's words]], then "after the quotes")
    const at = `(() => { const ch = document.querySelector(".fw-chosen"); const short = (x) => (x || "").replace(/\\s+/g, " ").trim();
      if (ch) return "whole:" + short(ch.querySelector(".fw-qtext, .fw-text")?.textContent);
      return "text:" + short(window.getSelection().focusNode?.textContent); })()`;
    const walk = async (key, n) => { const out = []; for (let k = 0; k < n; k++) { await t.key(key); await t.settle(); out.push(await t.js(at)); } return out; };
    await t.open(`#/p/${N}`);
    await t.select("after the quotes", { collapse: true, start: true });
    const up = await walk("ArrowUp", 4);
    t.check("↑ from below: the outer quote whole, the inner whole, its text, then the outer's text",
      JSON.stringify(up) === JSON.stringify(["whole:first words", "whole:beta's words", "text:beta's words", "text:first words"]), JSON.stringify(up));
    const down = await walk("ArrowDown", 3);
    t.check("↓ back: the inner quote whole, its text, then out of both (nothing after them inside) to what's below",
      JSON.stringify(down) === JSON.stringify(["whole:beta's words", "text:beta's words", "text:after the quotes"]), JSON.stringify(down));
    await t.select("beta's words", { collapse: true });
    const esc = await walk("Escape", 2);
    t.check("Esc steps out a level each time: the inner quote (its one block is its box), then the outer",
      JSON.stringify(esc) === JSON.stringify(["whole:beta's words", "whole:first words"]), JSON.stringify(esc));
    t.check("  selected whole: bolder than being in it (a second line inside its border)",
      await t.js(`getComputedStyle(document.querySelector(".fw-chosen")).boxShadow !== "none"`));
  },

  async tabs(t) {   // the focus's tab: outlined; selected whole, filled; a quote's ↗ the same
    const tab = `document.querySelector(".fw-tabs .fw-tab-focus")`;
    await t.open(`#/p/${A}`);
    await t.select("first words", { collapse: true });
    t.check("in a block: its number a tab, bright (outlined), a line to its border", await t.until(`!!${tab} && ${tab}.textContent === "1" && !${tab}.matches(".fw-tab-filled") && !!document.querySelector(".fw-tabs .fw-tab-line")`, 1000),
      await t.js(`[...document.querySelectorAll(".fw-tabs > *")].map(e => e.className + ":" + e.textContent).join(" | ")`));
    await t.key("Escape");
    t.check("  selected whole: the tab filled", await t.until(`!!${tab} && ${tab}.matches(".fw-tab-filled")`, 1000));
    t.check("  selected whole: no caret (one focus)", await t.until(`!!document.querySelector(".fw-selecting") && getComputedStyle(document.querySelector(".fw-selecting")).caretColor === "rgba(0, 0, 0, 0)"`, 1000));
    await t.select("beta's words", { collapse: true });
    t.check("in a quote: its ↗ a tab (outlined, a line to its border)", await t.until(`(() => { const o = document.querySelector(".fw-doc .fw-quote > .fw-top > .fw-open");
      return getComputedStyle(o).outlineStyle === "solid" && getComputedStyle(o, "::before").borderTopStyle === "solid"; })()`, 1000));
    await t.key("Escape");
    t.check("  only the ↗ where ⌘O goes is a tab", await t.js(`[...document.querySelectorAll(".fw-doc .fw-open")].filter(o => getComputedStyle(o).outlineStyle === "solid").length === 1`));
    t.check("  the quote selected whole: its ↗ filled, its arrow the page's colour", await t.until(`(() => { const o = document.querySelector(".fw-doc .fw-quote > .fw-top > .fw-open");
      return getComputedStyle(o).backgroundColor === "rgb(215, 111, 111)" && getComputedStyle(o).color === "rgb(17, 17, 17)"; })()`, 1000));
  },

  async letterTabs(t) {   // every block on your path a tab in the gutter: numbered, lettered, ...; the focus's bright
    // (nested: a quote of alpha [first words, a quote of beta [beta's words]], then "after the quotes")
    const tabs = `[...document.querySelectorAll(".fw-tabs .fw-tab")].map(e => e.textContent + (e.matches(".fw-tab-focus") ? "*" : "")).join(" ")`;
    await t.open(`#/p/${N}`);
    await t.select("after the quotes", { collapse: true });
    t.check("in a top-level block: its number, a tab", await t.until(`${tabs} === "2*"`, 1000), await t.js(tabs));
    await t.select("first words", { collapse: true });
    t.check("in a block inside a quote (not itself a quote): the quote's number, then its letter, the focus's bright",
      await t.until(`${tabs} === "1 a*"`, 1000), await t.js(tabs));
    t.check("  the quote starting on its first block's line: its tab above the block's, as they nest, each line on its own box, padded from its ends",
      await t.js(`(() => { const ts = [...document.querySelectorAll(".fw-tabs .fw-tab")], ls = [...document.querySelectorAll(".fw-tabs .fw-tab-line")];
        const [q, b] = ts.map((x) => x.getBoundingClientRect()), mid = (l) => l.getBoundingClientRect().top;
        const qb = document.querySelector(".fw-doc .fw-quote").getBoundingClientRect(), bb = document.querySelector(".fw-current .fw-here").getBoundingClientRect();
        const pad = 0.3 * q.height;   // (each line padded inside its box at both ends, things pushed down to make it)
        return q.bottom <= b.top && mid(ls[0]) >= qb.top + pad && mid(ls[0]) <= qb.bottom - pad && mid(ls[1]) >= bb.top + pad && mid(ls[1]) <= bb.bottom - pad; })()`),
      await t.js(`[...document.querySelectorAll(".fw-tabs > *")].map((x) => x.className + "@" + Math.round(x.getBoundingClientRect().top)).join(" ")`));
    await t.select("beta's words", { collapse: true });
    t.check("in a quote showing one block: the quote's tab is the focus (its block has none of its own)", await t.until(`${tabs} === "1 b*"`, 1000), await t.js(tabs));
    const centred = `(() => { const tab = document.querySelector(".fw-tabs .fw-tab-focus").getBoundingClientRect();
      const n = [...document.querySelectorAll(".fw-doc .fw-quote .fw-quote .fw-text")].find(e => e.textContent.includes("beta's")).firstChild.firstChild || [...document.querySelectorAll(".fw-doc .fw-quote .fw-quote .fw-text")].find(e => e.textContent.includes("beta's")).firstChild;
      const r = document.createRange(); r.setStart(n, 0); r.setEnd(n, 1); const l = r.getBoundingClientRect();
      return Math.abs((tab.top + tab.height / 2) - (l.top + l.height / 2)) <= 1; })()`;
    t.check("  the focus's tab centred on its block's first line", await t.js(centred));
    t.check("  every tab's line meets its own box (its middle within the box's top and bottom)", await t.js(`(() => {
      const lines = [...document.querySelectorAll(".fw-tabs .fw-tab-line")];
      return lines.every((l) => { const y = l.getBoundingClientRect().top, x = l.getBoundingClientRect().right;
        const box = [...document.querySelectorAll(".fw-doc .fw-text, .fw-doc .fw-quote, .fw-doc .fw-container")].find((b) => Math.abs(b.getBoundingClientRect().left - x) < 2 && y >= b.getBoundingClientRect().top && y <= b.getBoundingClientRect().bottom);
        return !!box; }); })()`));
    t.check("  tabs never overlap (one on another's line moves above or below it, clear)", await t.js(`(() => { const r = [...document.querySelectorAll(".fw-tabs .fw-tab")].map(e => e.getBoundingClientRect());
      return r.every((x, i) => i === 0 || x.top >= r[i - 1].bottom); })()`));
    t.check("  the quote around it (the path): faint, not the focus's bright red", await t.until(`getComputedStyle(document.querySelector(".fw-doc > .ProseMirror > .fw-quote")).borderTopColor === "rgba(154, 106, 106, 0.55)"`, 1000),
      await t.js(`getComputedStyle(document.querySelector(".fw-doc > .ProseMirror > .fw-quote")).borderTopColor`));
    await t.select("first words", { collapse: true, start: true });
    await t.settle();
    const at = await t.js(`document.querySelector(".fw-tabs .fw-tab-focus").getBoundingClientRect().top`);
    await t.key("ArrowRight"); await t.key("ArrowRight");
    await t.settle();
    const tabsAt = `[...document.querySelectorAll(".fw-tabs .fw-tab")].map(e => e.textContent + "@" + Math.round(e.getBoundingClientRect().top)).join(" ")`;
    t.check("  moving within the block: its tab stays put", Math.abs((await t.js(`document.querySelector(".fw-tabs .fw-tab-focus").getBoundingClientRect().top`)) - at) < 1,
      `before ${at} after ${await t.js(tabsAt)}`);
    await t.select("beta's words", { collapse: true });
    await t.key("Escape");   // (beta's quote selected whole, in alpha's quote's editor)
    t.check("  a quote selected inside another: only its ↗ is a tab (⌘O opens it), not the one around it", await t.until(`(() => {
      const on = [...document.querySelectorAll(".fw-doc .fw-open")].filter(o => getComputedStyle(o).outlineStyle === "solid");
      return on.length === 1 && on[0].closest(".fw-quote").matches(".fw-chosen"); })()`, 1000));
    await t.select("first words", { collapse: true, start: true });
    const one = await t.js(`(() => { const r = [...document.querySelectorAll(".fw-tabs .fw-tab")].find(e => e.textContent === "1").getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()`);
    await t.click(one[0], one[1]);
    t.check("  a click on a path tab (the quote around you): that quote selected whole, its tab now the focus, filled",
      await t.until(`!!document.querySelector(".fw-doc > .ProseMirror > .fw-quote.fw-chosen") && document.querySelector(".fw-tabs .fw-tab-focus")?.matches(".fw-tab-filled")`, 1000));
    t.check("  a top-level block with a tab: its plain number hidden under it", await t.js(`getComputedStyle(document.querySelector(".fw-doc > .ProseMirror > .fw-quote"), "::before").visibility === "hidden"`));
  },

  async liveHeader(t) {   // the header's words and updated change as you type, before any save
    await t.open(`#/p/${T}@${T1}`);
    const words = `+document.querySelector(".fw-hbox").innerText.match(/words (\\d+)/)[1]`;
    const before = await t.js(words);
    await t.select("the quick brown fox", { collapse: true });
    await t.type(" and two more");
    t.check("typing: the word count up at once (before the save)", (await t.js(words)) === before + 3, `${before} -> ${await t.js(words)}`);
    t.check("  updated: just now", await t.js(`document.querySelector(".fw-hbox").innerText.includes("updated just now")`));
    await t.settle();
    t.check("  saved: the store's count agrees", (await t.get(`/api/pericope/${T}`)).words === before + 3);
  },

  async kinds(t) {
    await t.open(`#/p/${B}@${B1}`);
    await t.key("ArrowUp");
    t.check("↑ from the first line: the title", await t.until(`document.activeElement?.classList.contains("fw-title")`, 1000));
    await t.key("ArrowUp");
    t.check("  ↑ again: the kinds line", await t.until(`document.activeElement?.classList.contains("fw-chip")`, 1000));
    await t.key("h");   // (typing on the line: the picker, with it typed)
    await t.until(`document.querySelector(".fw-menu")?.innerText.includes("kind ›")`, 2000);
    await t.type("aiku");
    t.check("  the picker: + new kind, with what's typed", await t.until(`document.querySelector(".fw-menu")?.innerText.includes("+ new kind “haiku”")`, 2000));
    await t.key("Enter");
    await t.settle();
    const tok = (await t.get(`/api/pericope/${B}`)).kindTokens;
    t.check("  a new kind, said yes to: in the store, a token", tok.length === 1 && tok[0].name === "haiku" && tok[0].mark === "yes"
      && await t.until(`document.activeElement?.classList.contains("fw-chip-yes") && document.activeElement.innerText === "haiku"`, 2000), JSON.stringify(tok));
    await t.key("Backspace");
    await t.settle();
    t.check("  ⌫ on it: the answer taken back", (await t.get(`/api/pericope/${B}`)).kindTokens.length === 0);
    const haiku = (await t.get("/api/kinds")).kinds.find((k) => k.name === "haiku").id;
    await t.open(`#/p/${haiku}`);
    await t.js(`(() => { const x = document.querySelector(".fw-title"); x.focus(); x.select(); return true; })()`);
    await t.type("verse");
    await t.key("Enter");
    await t.settle();
    t.check("a kind's title: its name, renamed as you leave it", (await t.get("/api/kinds")).kinds.some((k) => k.name === "verse"));
  },
};

scenarios.review.setup = (dir, data) => {   // the guesses, current: each pair's kind and block as stored now
  const at = Object.fromEntries(data.blocks.map((b) => [b.id, b.updated]));
  writeFileSync(join(dir, "kind-guesses.json"), JSON.stringify({ model: "test",
    guesses: { [K]: { [A]: [0.8, at[K], at[A]], [B]: [0.7, at[K], at[B]] } } }));
};

// --sweep DIR: every pericope of a copy of the store in DIR opened and left; nothing should change by it
const SWEEP = opt("--sweep", null);
if (SWEEP) {
  const sweep = async (t) => {
    const before = JSON.parse(readFileSync(join(t.dir, "freewrites.json"), "utf8"));
    const ids = before.blocks.filter((b) => b.entry).map((b) => b.id);
    let opened = 0, bad = [];
    for (const id of ids) {
      await t.open(`#/p/${id}`);
      const ok = await t.js(`window.fw.editor()?.id === "${id}" && !!document.querySelector(".fw-doc .ProseMirror")`);
      const p = await t.get(`/api/pericope/${id}`);
      const drawn = await t.js(`document.querySelectorAll(".fw-doc > .ProseMirror > *").length`);
      const want = Math.max(1, p.children.length);
      if (ok && drawn >= want && drawn <= want + 1) opened++; else bad.push(`${p.shown} (drawn ${drawn}, holds ${p.children.length})`);
    }
    await t.open("#/");
    await t.shot("sweep-home.png");
    t.check(`every pericope opened and drawn: ${opened} of ${ids.length}`, opened === ids.length, bad.slice(0, 8).join("; "));
    const after = JSON.parse(readFileSync(join(t.dir, "freewrites.json"), "utf8"));
    const strip = (d) => Object.fromEntries(d.blocks.map(({ updated, visits, words, ...b }) => [b.id, JSON.stringify(b)]));
    const [a, b] = [strip(before), strip(after)];
    const changed = Object.keys({ ...a, ...b }).filter((k) => a[k] !== b[k]);
    t.check("  visiting them changed nothing in the store", changed.length === 0,
      changed.slice(0, 6).map((k) => `${k}: ${(a[k] || "gone").slice(0, 120)} -> ${(b[k] || "gone").slice(0, 120)}`).join(" | "));
  };
  sweep.store = SWEEP;
  scenarios.sweep = sweep;
  ONLY.splice(0, ONLY.length, "sweep");
}

// --- run them, all at once ---------------------------------------------------------------------------------
const names = ONLY.length ? ONLY : Object.keys(scenarios);
const unknown = names.filter((n) => !scenarios[n]);
if (unknown.length) { console.log(`no scenario ${unknown.join(", ")}; there are: ${Object.keys(scenarios).join(" ")}`); process.exit(2); }
const dir = mkdtempSync(join(tmpdir(), "fw-e2e-chrome-"));
const started = Date.now();
await startChrome(dir);
const results = [];
const queue = [...names];
await Promise.all(Array.from({ length: Math.min(JOBS, queue.length) }, async () => {
  while (queue.length) { const n = queue.shift(); results.push(await run(n, scenarios[n])); }
}));
chrome.kill();
await sleep(300);
try { rmSync(dir, { recursive: true, force: true }); } catch {}
let all = true;
for (const r of names.map((n) => results.find((x) => x.name === n))) {
  all &&= r.ok;
  console.log(`${r.ok ? "✓" : "✗"} ${r.name} (${(r.ms / 1000).toFixed(1)}s, ${r.out.length} checks)`);
  for (const line of r.out) if (!r.ok || process.env.VERBOSE) console.log("    " + line);
}
console.log(`${all ? "E2E OK" : "E2E FAILURES"} · ${results.reduce((n, r) => n + r.out.length, 0)} checks · ${((Date.now() - started) / 1000).toFixed(1)}s`);
process.exit(all ? 0 : 1);
