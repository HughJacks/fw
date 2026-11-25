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
import { mkdtempSync, writeFileSync, readFileSync, rmSync, statSync } from "node:fs";
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
    async shot(file, clip) {   // (clip: {x, y, width, height, scale}, a part of the page, magnified)
      if (!SHOTS) return;
      const { result } = await cdp("Page.captureScreenshot", clip ? { format: "png", clip: { scale: 1, ...clip } } : { format: "png" });
      writeFileSync(join(SHOTS, file), Buffer.from(result.data, "base64"));
    },
  };
  for (let n = 0; n < 200; n++) { try { await fetch(`http://127.0.0.1:${port}/api/stamp`); break; } catch { await sleep(25); } }
  const t0 = Date.now();
  try { await fn(t); } catch (e) { t.check("no error", false, e.stack.split("\n").slice(0, 3).join(" / ")); }
  if (thrown.length) t.check("the page threw nothing", false, thrown.join(" | "));
  close();
  const gone = new Promise((r) => (server.exitCode !== null ? r() : server.once("exit", r)));
  server.kill();
  await gone;   // (it writes its .json copy as it goes: store.json_later)
  rmSync(dir, { recursive: true, force: true });
  return { name, ok, out, ms: Date.now() - t0 };
}

/** The store's .json copy in `dir`, once it's caught up with the document (the core writes it a moment after its
 * last save: store.json_later). */
async function storedIn(dir) {
  const mtime = (f) => { try { return statSync(join(dir, f)).mtimeMs; } catch { return 0; } };
  for (let n = 0; n < 60 && mtime("freewrites.json") < mtime("freewrites.loro"); n++) await sleep(50);
  return JSON.parse(readFileSync(join(dir, "freewrites.json"), "utf8"));
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
    await t.until(`!document.querySelector(".fw-pending") && document.querySelector(".fw-library .fw-hint")?.innerText === "found"
      && document.querySelector(".fw-library .fw-row.fw-sel .fw-row-label")?.innerText === "beta"`, 2000);
    await t.settle();
    await t.key("Backspace", 4);   // ⌘⌫
    t.check("home: ⌘⌫ on a pericope: asked first, in the page", await t.until(`document.querySelector(".fw-ask")?.innerText.includes("delete “beta”")`, 1000),
      await t.js(`(document.querySelector(".fw-ask")?.innerText || "") + " | " + document.querySelector(".fw-status").innerText`));
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
    // (seen as it happens: it shows only until the search service answers, ~50 ms in the tests, which a poll can miss)
    await t.js(`window.__sawPending = false; const seen = () => { if (document.querySelector(".fw-library .fw-pending:not(.fw-gone)")) window.__sawPending = true; };
      new MutationObserver(seen).observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ["class"] }); 1`);
    await t.type("bet");
    t.check("  typing: what the search service will add is shown coming", await t.until(`window.__sawPending`, 1000));
    t.check("    gone once its answer's in", await t.until(`!document.querySelector(".fw-library .fw-pending:not(.fw-gone)")`, 3000));
    t.check("  typing searches, the best first and selected", await t.until(`document.querySelector(".fw-library .fw-row")?.innerText.includes("beta")
      && document.querySelector(".fw-library .fw-row").classList.contains("fw-sel")`));
    t.check("  in the list itself, no menu over it (2026-11-21): what doesn't match gone",
      await t.js(`!document.querySelector(".fw-results")
        && ![...document.querySelectorAll(".fw-library .fw-row")].some(r => r.innerText.includes("alpha") && !r.innerText.includes("beta"))
        && document.querySelector(".fw-library .fw-hint").innerText === "found"`),
      await t.js(`JSON.stringify([[...document.querySelectorAll(".fw-library .fw-row, .fw-library .fw-hint")].map(r => r.className + ":" + r.innerText)])`));
    t.check("  + new, titled with it, last", await t.js(`document.querySelector(".fw-new .fw-row").innerText.includes("+ new pericope “bet”")`));
    await t.key("Escape");
    const n = (await t.get("/api/home")).rows.length;
    t.check("below, the list: every pericope, a line each", await t.until(`document.querySelectorAll(".fw-library .fw-row").length === ${n}`, 1000) && n >= 7);
    for (let k = 0; k < 2; k++) await t.key("ArrowDown");
    t.check("  ↓ into the list", await t.js(`!!document.querySelector(".fw-library .fw-sel")`));
    await t.key("Enter");
    t.check("  ↵ there opens it", await t.until(`!!window.fw.editor()?.id && !window.fw.home()`, 2000));
    await t.shot("home.png");
  },

  async spread(t) {   // (motion on: ?motion) the room round the block you're in eases out, its tab on it throughout (2026-11-19)
    await t.cdp("Page.navigate", { url: `http://127.0.0.1:${t.port}/?test&motion#/p/${A}` });
    await t.until(`window.fw?.editor()?.id === "${A}"`, 6000);
    await t.select("first words", { collapse: true });
    await t.key("Enter");   // (a new block below, the one you're in)
    await t.until(`document.querySelector(".fw-tab-focus")?.textContent === "2"`, 2000); await t.settle();
    const sample = `(() => { const h = document.querySelector(".fw-here"), tab = document.querySelector(".fw-tab-focus");
      return h && tab ? [parseFloat(getComputedStyle(h).paddingTop), parseFloat(tab.style.top), h.getBoundingClientRect().top - tab.offsetParent.getBoundingClientRect().top,
        h.getBoundingClientRect().bottom - tab.offsetParent.getBoundingClientRect().top, tab.offsetHeight, h.innerText.includes("first words")] : null; })()`;
    // (the new block's room all there, and its tab come to rest)
    await t.until(`(() => { const s = ${sample}; if (!s) return false; const was = window.__top; window.__top = s; return !!was && was[0] === s[0] && was[1] === s[1]; })()`, 3000);
    const full = (await t.js(sample))[0], rest = 1.6;   // (the room round the block you're in, all there; .1rem at rest)
    // (recorded in the page, a sample each frame, so a busy machine can't make the test miss the motion)
    await t.js(`window.__rec = []; (function rec() { const s = ${sample}; if (s) window.__rec.push(s); if (window.__rec.length < 400) window.__recFrame = requestAnimationFrame(rec); })(); 1`);
    await t.key("ArrowUp");   // (into the block above: its room eases out, the tab goes up with it)
    await t.until(`(() => { const r = window.__rec.filter((s) => s[5]); return r.length > 2 && r.at(-1)[0] === ${full} && r.at(-1)[1] === r.at(-2)[1] && r.at(-2)[1] === r.at(-3)[1]; })()`, 4000);
    await t.js(`cancelAnimationFrame(window.__recFrame); 1`);
    const seen = (await t.js(`window.__rec`)).filter((s) => s[5]);
    const pads = seen.map((s) => s[0]), tops = seen.map((s) => s[1]), last = seen.at(-1);
    t.check("moving to another block: its room eases out (between at rest and full, on the way)", pads.some((v) => v > rest + 0.1 && v < full - 0.1), JSON.stringify(pads));
    t.check("  its tab on its block all the while (no gliding from the other: each block's own, 2026-11-19)",
      seen.every((s) => s[1] + s[4] / 2 > s[2] && s[1] + s[4] / 2 < s[3]), JSON.stringify(seen.map((s) => s.slice(1, 4).map(Math.round))));
    t.check("  and ends on its block (its middle within the box)", last && last[1] + last[4] / 2 > last[2] && last[1] + last[4] / 2 < last[3], JSON.stringify(last));
  },

  async openline(t) {   // the line from a quote to its ↗ (2026-11-19): from the colour of the quote's border to the ↗'s
    const line = `(() => { const o = [...document.querySelectorAll(".fw-open")].find(e => getComputedStyle(e, "::before").content !== "none");
      return o ? getComputedStyle(o, "::before").backgroundImage : "none"; })()`;
    await t.open(`#/p/${A}`); await t.select("beta's", { collapse: true }); await t.settle();
    t.check("writing in a quote's one block: faded to faded (in, not selected)", await t.until(`${line} === "linear-gradient(to right, rgba(216, 111, 111, 0.55), rgba(216, 111, 111, 0.55))"`, 1000), await t.js(line));
    await t.open(`#/p/${N}`); await t.select("first words", { collapse: true }); await t.settle();
    t.check("  in one of a quote's blocks: dim (its border's) to faded", await t.until(`${line} === "linear-gradient(to right, rgba(154, 106, 106, 0.38), rgba(216, 111, 111, 0.55))"`, 1000), await t.js(line));
  },

  async visits(t) {   // your attention told to the core, written as visits (2026-11-20: the web editor recorded none)
    await t.open(`#/p/${B}@${B1}`);
    await t.type("x");
    t.check("opened, written in: told", await t.until(`(window.fwVisits || []).some(v => v.pericope === "${B}")
      && (window.fwVisits || []).some(v => v.block === "${B1}" && v.flags.includes("w"))`, 2000), await t.js(`JSON.stringify(window.fwVisits)`));
    await t.open("#/");
    t.check("  left: written into the store", await t.until(`(window.fwVisits || []).some(v => v.flush)`, 2000)
      && await (async () => { for (let n = 0; n < 40; n++) { const d = JSON.parse(readFileSync(join(t.dir, "freewrites.json"), "utf8"));
        if (d.blocks.find((b) => b.id === B1)?.visits?.recent?.some(([, f]) => f.includes("w"))) return true; await sleep(50); } return false; })());
  },

  async exits(t) {   // the foot of every page (2026-11-20): the same as home's, the search and the suggestions from here
    await t.open(`#/p/${B}`);
    const rows = `[...document.querySelectorAll(".fw-on-pericope .fw-suggested .fw-library .fw-row")]`;
    t.check("from beta: alpha, which quotes it, at the foot", await t.until(`${rows}.some(r => r.dataset.pericope === "${A}")`, 3000));
    t.check("  the same as home's: go to, the suggestions said lightly, + new pericope last", await t.js(`!!document.querySelector(".fw-on-pericope .fw-suggested .fw-search input")
      && document.querySelector(".fw-on-pericope .fw-suggested .fw-prompt").innerText.includes("go to") && document.querySelector(".fw-on-pericope .fw-suggested .fw-hint").innerText === "suggested from this"
      && [...document.querySelectorAll(".fw-on-pericope .fw-suggested .fw-home-page .fw-row")].at(-1).innerText.includes("+ new pericope")`));
    await t.js(`document.querySelector('.fw-suggested .fw-library .fw-row[data-pericope="${A}"]').dispatchEvent(new MouseEvent("mousedown", { bubbles: true })); 1`);
    t.check("  a click: there", await t.until(`window.fw.editor()?.id === "${A}"`, 3000));
    await t.settle();
    t.check("  not beta from alpha: it's on alpha's page already", await t.js(`!${rows}.some(r => r.dataset.pericope === "${B}")`));
    t.check("  never empty: filled from home's order", await t.js(`${rows}.length > 0`));
    await t.key("[", 4);
    t.check("  ⌘[: back to beta", await t.until(`window.fw.editor()?.id === "${B}"`, 3000));
    await t.until(`${rows}.length > 0`, 3000);
    t.check("  a short pericope: at the bottom of the screen, as wide as its blocks", await t.js(`(() => {
      const x = document.querySelector(".fw-on-pericope .fw-suggested").getBoundingClientRect(), d = document.querySelector(".fw-doc").getBoundingClientRect(),
        s = document.querySelector(".fw-on-pericope .fw-search").getBoundingClientRect();
      return innerHeight - x.bottom < 60 && x.top > d.bottom && Math.abs(s.width - d.width) < 2 && Math.abs(s.left - d.left) < 2; })()`),
      await t.js(`JSON.stringify([innerHeight, document.querySelector(".fw-on-pericope .fw-suggested").getBoundingClientRect(), document.querySelector(".fw-doc").getBoundingClientRect()])`));
    t.check("  a short pericope: nothing to scroll past its foot", await t.js(`document.documentElement.scrollHeight <= innerHeight + 1`),
      await t.js(`JSON.stringify([document.documentElement.scrollHeight, innerHeight])`));
    await t.js(`window.fw.end(); 1`);
    await t.key("ArrowDown");
    t.check("  ↓ past the end: into its search", await t.until(`!!document.activeElement?.closest(".fw-on-pericope .fw-suggested .fw-search")`, 1000));
    await t.key("ArrowUp");
    t.check("  ↑ from its top: back at the pericope's end", await t.until(`!!document.activeElement?.closest(".fw-doc")`, 1000));
    await t.key("ArrowDown");
    const first = await t.js(`document.querySelector(".fw-on-pericope .fw-suggested .fw-library .fw-row").dataset.pericope`);
    t.check("  in its search, the first suggestion selected", await t.until(`document.querySelector(".fw-on-pericope .fw-suggested .fw-sel")?.dataset.pericope === "${first}"`, 1000));
    await t.key("Enter");
    t.check("  Enter: there", await t.until(`window.fw.editor()?.id === "${first}"`, 3000));
    // following what's written (2026-11-21): a suggestion quoted here leaves the suggestions once it's saved, the page not opened again
    await t.open(`#/p/${T}`);
    await t.until(`${rows}.length > 0`, 3000);
    await t.settle();
    const [y, title] = await t.js(`[${rows}[0].dataset.pericope, ${rows}[0].querySelector(".fw-row-label").innerText]`);
    await t.js(`window.__foot = document.querySelector(".fw-suggested"); 1`);
    await t.end();
    await t.key("Enter");
    await t.type("/");
    await t.key("Enter");
    await t.until(`!!document.querySelector(".fw-menu input")`, 2000);
    for (const ch of title) await t.type(ch);
    await t.until(`document.querySelector(".fw-menu .fw-row.fw-sel")?.innerText.includes(${JSON.stringify(title)})`, 2000);
    await t.key("Enter");
    await t.settle();
    t.check("  following what's written: one quoted here, saved, leaves its suggestions", await t.until(`!${rows}.some(r => r.dataset.pericope === "${y}")`, 3000),
      await t.js(`JSON.stringify(${rows}.map(r => r.dataset.pericope)) + " ${y}"`));
    t.check("    the same suggestions, not made again", await t.js(`document.querySelector(".fw-suggested") === window.__foot`));
    await t.open("#/");
    t.check("home: one of them, under the waiting pericope", await t.until(`document.querySelectorAll(".fw-suggested").length === 1 && !document.querySelector(".fw-on-pericope .fw-suggested")`, 2000));
  },

  async onepage(t) {   // one page (2026-11-19): one header and one body for every pericope; moving changes what they show
    await t.open("#/");
    await t.js(`window.__h = document.querySelector(".fw-header"); window.__b = document.querySelector(".fw-doc"); window.__alive = 1; 1`);
    const same = `document.querySelector(".fw-header") === window.__h && document.querySelector(".fw-doc") === window.__b
      && document.querySelectorAll(".fw-header, .fw-doc").length === 2 && window.__alive === 1`;
    const go = async (hash, cond) => { await t.js(`location.hash = ${JSON.stringify(hash)}; 1`); const ok = await t.until(cond, 3000); await t.settle(); return ok; };
    const title = `document.querySelector(".fw-title").value`;
    t.check("home to a pericope: the same header and body, showing it", await go(`#/p/${A}`, `window.fw.editor()?.id === "${A}"`)
      && await t.js(same) && await t.js(`${title} === "alpha" && !document.querySelector(".fw-waiting") && !window.fw.home()`),
      await t.js(`[${title}, document.querySelectorAll(".fw-header").length]`));
    t.check("  its blocks in the body", await t.js(`document.querySelector(".fw-doc").innerText.includes("first words")`));
    t.check("  to another: the same header and body", await go(`#/p/${B}`, `window.fw.editor()?.id === "${B}"`) && await t.js(same)
      && await t.js(`${title} === "beta" && !document.querySelector(".fw-doc").innerText.includes("first words")`));
    await t.key("[", 4);
    t.check("  ⌘[ back: the same header and body, the one before", await t.until(`window.fw.editor()?.id === "${A}"`, 3000) && await t.js(same));
    t.check("the keys page: the pericope hidden, not gone", await go("#/keys", `!!document.querySelector(".fw-keyrow")`)
      && await t.js(`!!window.__h.closest("[hidden]") && document.querySelector(".fw-header") === window.__h`));
    t.check("home again: the same header and body, a waiting pericope, the list below", await go("#/", `window.fw.home() && !window.fw.editor()?.id`)
      && await t.js(same) && await t.js(`!window.__h.closest("[hidden]") && !!document.querySelector(".fw-waiting .fw-header") && !!document.querySelector(".fw-library .fw-row") && ${title} === ""`));
  },

  async waiting(t) {   // home (2026-11-19): a waiting pericope in the middle, the search and the list below it; typed in, it's made
    const entries = async () => (await t.get("/api/home")).rows.map((l) => l.key).sort().join(" ");
    const before = await entries();
    await t.open("#/");
    const box = await t.js(`(() => { const h = document.querySelector(".fw-waiting .fw-header").getBoundingClientRect(),
      d = document.querySelector(".fw-waiting .fw-doc").getBoundingClientRect(), s = document.querySelector(".fw-search").getBoundingClientRect(),
      g = document.querySelector(".fw-library .fw-row")?.getBoundingClientRect();
      return { mid: (h.top + d.bottom) / 2, search: s.top, card: g && g.top, h: innerHeight }; })()`);
    t.check("home: an empty, untitled pericope at the top of the screen", box && box.mid < box.h / 4
      && await t.js(`window.fw.editor() && !window.fw.editor().id && document.querySelector(".fw-waiting .fw-title").value === ""`), JSON.stringify(box));
    t.check("  the cursor in it", await t.js(`!!document.activeElement.closest(".fw-waiting .ProseMirror")`));
    t.check("  below it the search and the list, from near the bottom of the screen and off it", box.search > box.h * 0.6 && box.search < box.h
      && box.card > box.search && await t.js(`document.querySelectorAll(".fw-library .fw-row").length >= 7`), JSON.stringify(box));
    t.check("  nothing selected in the list while you're in the pericope", await t.js(`!document.querySelector(".fw-sel")`));
    await t.shot("home-open.png");
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
    t.check("typed in: no longer waiting, the suggestions kept below it (2026-11-20)", await t.js(`!document.querySelector(".fw-waiting") && !!document.querySelector(".fw-centre + .fw-suggested .fw-library .fw-row")`));
    const now = await t.js(span);
    t.check("  the pericope still where it was, at the top (no jump)", Math.abs(now.top - was.top) < 12 && now.y === 0, JSON.stringify([was, now]));
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
    t.check("  growing, it grows down, as any page: its top kept, its bottom down", Math.abs(grown.top - one.top) < 4 && grown.bottom > one.bottom + 40
      && grown.y === 0, JSON.stringify([one, grown]));
    for (let i = 0; i < ["two", "three", "four"].join("").length + 3; i++) await t.key("Backspace");   // (the three lines and their three Enters, taken back)
    await t.settle();
    const k = made && await t.kids(made);
    t.check("  everything typed kept, whole", k && k.length === 1 && k[0].text === "q" + words, JSON.stringify(k));
    t.check("  the cursor still at the end of it", await t.js(`(() => { const v = window.fw.editor().view; return v.hasFocus() && v.state.selection.from === v.state.doc.content.size - 1; })()`));
    await t.shot("home-typed.png");
    await t.key("Enter", 12);   // ⌘⇧↵: sent away
    t.check("⌘⇧↵ on it: home again, a fresh waiting pericope and the list", await t.until(`window.fw.home() && !window.fw.editor()?.id
      && !!document.querySelector(".fw-waiting .ProseMirror") && !!document.querySelector(".fw-library .fw-row") && location.hash === "#/"`, 3000));
    await t.settle();
    t.check("  what was sent away is in the store, unchanged", (await t.kids(made))[0].text === "q" + words);
    await t.key("[", 4);
    t.check("  ⌘[: back to it", await t.until(`window.fw.editor()?.id === "${made}" && !window.fw.home()`, 3000));
  },

  async away(t) {   // send it away (⌘⇧↵): from a pericope, saved and home; ⌘[ reaches it; a blank one: nothing
    await t.open(`#/p/${T}`);
    await t.end();
    await t.type(" and away");
    await t.js(`window.__foot = document.querySelector(".fw-suggested"); 1`);
    await t.key("Enter", 12);   // (at once: nothing waited for)
    t.check("a pericope sent away (⌘⇧↵): home", await t.until(`window.fw.home() && !window.fw.editor()?.id && location.hash === "#/"`, 3000));
    await t.settle();
    const k = await t.kids(T);
    t.check("  what was typed just before, saved", k[1].text === "jumps over the dog and away", JSON.stringify(k));
    t.check("  only the pericope went: the suggestions stayed on the page (2026-11-21)", await t.js(`document.querySelector(".fw-suggested") === window.__foot`));
    await t.key("[", 4);
    t.check("  ⌘[: back to what was sent away", await t.until(`window.fw.editor()?.id === "${T}"`, 3000));
    await t.key("]", 4);
    t.check("  ⌘]: home again", await t.until(`window.fw.home()`, 3000));
    await t.settle();
    const n = (await t.get("/api/home")).rows.length;
    await t.key("Enter", 12);
    await t.settle();
    t.check("home's waiting pericope, blank: nothing sent, nothing made", await t.js(`window.fw.home() && location.hash === "#/"
      && document.querySelector(".fw-status").innerText.includes("nothing here")`) && (await t.get("/api/home")).rows.length === n);
    await t.open("#/keys");
    t.check("its key on the keys page", await t.until(`document.querySelector('.fw-keyrow[data-id="done"]')?.innerText.includes("⌘⇧↵")
      && document.querySelector('.fw-keyrow[data-id="done"]').innerText.includes("Send it away")`, 2000));
    // the slide (on by default; off in ?test, so ?motion here): caught mid-way
    await t.cdp("Page.navigate", { url: `http://127.0.0.1:${t.port}/?test&motion#/p/${T}` });
    await t.until(`window.fw?.editor()?.id === "${T}"`, 6000);
    await t.settle();
    await t.key("Enter", 12);
    const foot0 = await t.js(`document.querySelector(".fw-suggested").getBoundingClientRect().top`);
    const mid = await t.until(`(() => { const a = document.querySelector(".fw-peri").getAnimations()[0]; if (!a) return false;
      a.pause(); a.currentTime = 150; return new DOMMatrix(getComputedStyle(document.querySelector(".fw-peri")).transform).m42 < -5; })()`, 1000);   // (how far: its height on screen, so only that it's going)
    t.check("  mid-way, the pericope going, the suggestions where they were", Math.abs(await t.js(`document.querySelector(".fw-suggested").getBoundingClientRect().top`) - foot0) < 1);
    await t.shot("send-away-mid.png");   // (held mid-way for the picture, then let go)
    await t.js(`document.getAnimations().forEach((a) => a.play()); 1`);
    t.check("  sliding up off the top (with motion), then home", mid && await t.until(`window.fw.home() && getComputedStyle(document.querySelector(".fw-peri")).transform === "none"`, 3000));
  },

  async typing(t) {
    await t.open(`#/p/${A}`);
    await t.end();
    t.check("a pericope open: its blocks, the quote drawn with what it shows",
      await t.js(`document.body.innerText.includes("first words") && document.querySelector(".fw-quote")?.innerText.includes("beta's words")`));
    t.check("  the header", await t.js(`document.querySelector(".fw-label").innerText === "pericope" && document.querySelector(".fw-title").value === "alpha"`));
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
    t.check("edit-through: the arrow goes into the quote, not selecting it whole first (2026-11-20)", await t.until(`!!document.querySelector(".fw-quote.fw-in") && !document.querySelector(".fw-quote.ProseMirror-selectednode")`, 1000));
    await t.type(" and more");
    await t.settle();
    t.check("  typed there: saved into the quoted pericope", (await t.kids(B))[0].text === "beta's words and more");
    await t.key("Escape");
    t.check("  Esc: out a level, the quote selected whole (it shows one block: that block's box is the quote's)",
      await t.until(`!document.querySelector(".fw-quote.fw-in") && !!document.querySelector(".fw-quote.ProseMirror-selectednode")`, 1000));
    await t.key("Enter");
    t.check("  Enter on it (selected by Esc: block level): in a level, the caret at the end of its text (2026-11-19, later)",
      await t.until(`!!document.querySelector(".fw-quote.fw-in") && window.getSelection().focusOffset === "beta's words and more".length`, 1000));
    await t.end();   // (alpha ends with the quote: a block below it to write in)
    await t.type("after the quote");
    await t.settle();
    t.check("  written through it, then below it: saved (the pericope's base kept up, not refused)",
      (await t.kids(A)).some((c) => c.text === "after the quote") && !(await t.js(`document.querySelector("#bar-left").innerText.includes("not saved")`)),
      JSON.stringify((await t.kids(A)).map((c) => c.text || c.t)));
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
      (await t.kids(home.rows.find((x) => x.title === "fresh idea")?.key)).some((c) => c.text?.includes("written in the new one")) && !(await t.kids(A)).some((c) => c.text === "written in the new one"));
    await t.key("Escape"); await t.key("Escape");
    await t.key("Enter");
    await t.type("/xyz");
    t.check("  what matches no command is just text", await t.until(`!document.querySelector(".fw-menu") && document.querySelector(".fw-doc").innerText.includes("/xyz")`, 1000));
    await t.shot("menu.png");
  },

  async actions(t) {
    await t.open(`#/p/${A}@${A1}`);
    await t.select("first wo", { collapse: true });
    // where the cursor is: the text it's in, how far in, and whether that's inside a quote (2026-11-19: a pop out kept it)
    const caret = `(() => { const s = getSelection(), n = s.anchorNode; return n ? [n.textContent, s.anchorOffset, !!n.parentElement?.closest(".fw-quote")].join("|") : ""; })()`;
    await t.key("e", 4);   // ⌘E: Turn into a quote
    await t.settle();
    t.check("⌘E: the block a pericope of its own, quoted where it was", (await t.kids(A))[0].t === "quote" && (await t.kids(A))[0].title === "first words");
    t.check("  the cursor where it was, in the same text, now through the quote", await t.until(`${caret} === "first words|8|true"`, 1000), await t.js(caret));
    await t.key("z", 4);   // ⌘Z: the action taken back, in the store too
    await t.settle();
    t.check("  ^Z: taken back, in the store too", (await t.kids(A))[0].text === "first words");
    t.check("  the cursor still where it was, out of the quote", await t.until(`${caret} === "first words|8|false"`, 1000), await t.js(caret));
    await t.key("y", 4);   // ⌘Y
    await t.settle();
    t.check("  ^Y: done again", (await t.kids(A))[0].t === "quote");
    t.check("  the cursor still where it was, through the quote again", await t.until(`${caret} === "first words|8|true"`, 1000), await t.js(caret));
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
    await t.key("Escape");
    await t.until(`document.querySelector(".fw-doc > .ProseMirror > *").matches(".fw-picked")`, 1000);
    await t.key("ArrowUp");
    t.check("  ↑ from the first block selected whole: the header, unfolded", await t.until(`document.activeElement?.classList.contains("fw-title")
      && document.querySelector(".fw-more").getBoundingClientRect().height > 0`, 1000), await t.js(`document.activeElement?.className`));
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
    const r0 = await t.js("window.fw.reloads || 0");
    t.check("(the cursor after \"brown\", in the quote)", await t.select("brown", { collapse: true }), "reloads " + r0 + " " + await t.js("window.fw.reloads || 0") + " " + await t.js(`document.querySelector(".fw-doc").innerText`));
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
    t.check("  drawn as a quote: a ↗, its source not named; the source dim inside", await t.until(`!!document.querySelector(".fw-doc .fw-para > .fw-open") && !document.querySelector(".fw-doc .fw-para")?.innerText.includes("≈") && document.querySelector(".fw-doc .fw-guide")?.innerText.includes("quick brown")`, 2000));
    t.check("  in it: its ↗'s tab drawn, where ⌘O goes", await t.js(`getComputedStyle(document.querySelector(".fw-doc .fw-para > .fw-open")).opacity === "1"`));
    await t.type("a fox, quick");
    await t.settle();
    t.check("  written in: your words, the dim source gone", (await t.kids(M))[0].text === "a fox, quick" && await t.until(`!document.querySelector(".fw-doc .fw-guide")`, 2000));
    const pid = (await t.kids(M))[0].id;
    await t.settle();
    const stored = (await storedIn(t.dir)).blocks.find((b) => b.id === pid)?.content;
    t.check("  in the store, a block of its own (2026-11-21, v18): {paraphrase, text}", JSON.stringify(stored) === JSON.stringify({ paraphrase: T, text: "a fox, quick" }), JSON.stringify(stored));
    // found in the search: never opened itself, its original is (2026-11-21)
    await t.open("#/");
    await t.key("ArrowDown");
    await t.type("a fox, quick");
    await t.until(`!document.querySelector(".fw-pending") && [...document.querySelectorAll(".fw-library .fw-row")].some(r => r.innerText.includes("a fox, quick"))`, 3000);
    await t.js(`[...document.querySelectorAll(".fw-library .fw-row")].find(r => r.innerText.includes("a fox, quick")).dispatchEvent(new MouseEvent("mousedown", { bubbles: true })); 1`);
    t.check("  a paraphrase found in the search: its original opened, not where the paraphrase lives", await t.until(`window.fw.editor()?.id === "${T}"`, 3000), await t.js(`location.hash`));
    await t.open(`#/p/${M}`);
    await t.key("o", 4);
    t.check("  ⌘O in it: its source opened", await t.until(`window.fw.editor()?.id === "${T}"`, 3000));
    await t.key("[", 4);
    await t.until(`window.fw.editor()?.id === "${M}"`, 3000);
    await t.settle();
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
    const sel = `(() => { const s = getSelection(); return s.toString() + "|" + !!s.anchorNode?.parentElement?.closest(".fw-quote"); })()`;
    t.check("  the selection kept, now through the quote", await t.until(`${sel} === "quick brown|true"`, 1000), await t.js(sel));
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
      if (!here) return "none"; const c = getComputedStyle(here); return c.borderTopColor !== "rgba(0, 0, 0, 0)" && parseFloat(c.paddingTop) > 4
        && c.color === "rgb(221, 218, 211)"; })()`;   // (its box, more room, its text full: --fg)
    await t.select("the only block", { collapse: true });
    t.check("  in a block two boxes deep: drawn as a top-level one (its box, more room)", await t.until(active("the only block"), 1000), await t.js(active("the only block")));
    await t.open(`#/p/${R}`);
    await t.select("jumps over the dog", { collapse: true });
    t.check("  the block you're in: the same weight as the rest (its lines never re-break)", await t.js(`(() => {
      const here = document.querySelector(".fw-here"), rest = [...document.querySelectorAll(".fw-doc .fw-text")].find(e => !e.matches(".fw-here"));
      return getComputedStyle(here).fontWeight === getComputedStyle(rest).fontWeight; })()`));
    t.check("  in a block of a quote showing several: the same", await t.until(active("jumps over the dog"), 1000), await t.js(active("jumps over the dog")));
    t.check("    the quote around it: faint (the path), not the focus's bright red", await t.until(`(() => { const c = getComputedStyle([...document.querySelectorAll(".fw-quote")].find(q => q.innerText.includes("jumps over"))).outlineColor;   // (the path: a hairline outline, 2026-11-19)
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
        && getComputedStyle(q).borderTopColor === "rgba(216, 111, 111, 0.55)"; })()`, 1000));   // (in it: faded and drawn, 2026-11-19)
    await t.open(`#/p/${S0}`);
    await t.select("the only block", { collapse: true });
    await t.key("Escape");
    t.check("  selected whole (Esc): drawn so, without the browser's blue selection", await t.until(`!!document.querySelector(".fw-picked, .ProseMirror-selectednode")`, 1000)
      && await t.js(`getComputedStyle(document.querySelector(".fw-picked, .ProseMirror-selectednode").querySelector("*") || document.querySelector(".fw-picked, .ProseMirror-selectednode"), "::selection").backgroundColor === "rgba(0, 0, 0, 0)"`));
  },

  async topline(t) {   // a quote's top line: a mini header of what it shows of its source (2026-11-19)
    await t.open(`#/p/${A}`);
    const top = `document.querySelector(".fw-doc .fw-quote > .fw-top > .fw-top-label")`;
    t.check("a quote showing nothing on its top line: no mini header", await t.js(`${top}.childElementCount === 0`));
    await fetch(`http://127.0.0.1:${t.port}/api/act`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ do: "show", quote: QA, show: ["title", "words", "updated"] }) });
    await t.open(`#/p/${B}`); await t.open(`#/p/${A}`);
    t.check("  showing its title, words, last update: a line of facts, then its title", await t.until(
      `${top}.querySelector(".fw-mini-title")?.textContent === "beta" && /^words \\d+ · updated /.test(${top}.querySelector(".fw-mini-facts")?.textContent)`, 2000),
      await t.js(`${top}.innerText`));
    t.check("  its title the header title's font and size, the writing's size", await t.js(`(() => { const a = getComputedStyle(${top}.querySelector(".fw-mini-title")),
      b = getComputedStyle(document.querySelector(".fw-title")), w = getComputedStyle(document.querySelector(".fw-text, .fw-doc p") || document.body);
      return a.fontSize === b.fontSize && a.fontWeight === b.fontWeight && a.fontFamily === b.fontFamily && a.fontSize === w.fontSize; })()`));
    await t.shot("topline.png");
    // toggled from the menu's submenu (2026-11-19, the user: each toggle kicked us out of the submenu and moved the cursor)
    await t.select("beta's", { collapse: true }); await t.settle();
    const caret = `(() => { const s = getSelection(), n = s.anchorNode; return n ? [n.textContent, s.anchorOffset, !!n.parentElement?.closest(".fw-quote")].join("|") : ""; })()`;
    const before = await t.js(caret);
    await t.key("/", 4);
    await t.until(`document.querySelector(".fw-menu")?.innerText.includes("Its top line")`, 1000);
    const down = await t.js(`[...document.querySelectorAll(".fw-menu .fw-row")].findIndex((r) => r.innerText.startsWith("Its top line"))`);
    for (let n = 0; n < down; n++) await t.key("ArrowDown");
    await t.key("ArrowRight");   // (into the submenu)
    await t.until(`document.querySelector(".fw-menu")?.innerText.includes("its date")`, 1000);
    const rows = `[...document.querySelectorAll(".fw-menu .fw-row")].map((r) => r.innerText.split("\\n")[0]).join(",")`;
    await t.js(`window.__left = 0; document.querySelector(".fw-menu input").addEventListener("blur", () => window.__left++); 1`);
    await t.key("Enter");   // (the first: Hide its title)
    await t.settle();
    t.check("  a toggle in the submenu: the menu still open, still the submenu, saying what's on now", await t.until(
      `document.querySelector(".fw-menu") && ${rows}.startsWith("Show its title,")`, 2000), await t.js(rows));
    await t.key("ArrowDown"); await t.key("Enter");   // Show its date
    await t.settle();
    t.check("  another: still there, the next toggled", await t.until(`document.querySelector(".fw-menu") && ${rows}.includes("Hide its date")`, 2000), await t.js(rows));
    t.check("  the focus never left the menu (a slow store would close it)", (await t.js(`window.__left`)) === 0, String(await t.js(`window.__left`)));
    t.check("  the store has both", JSON.stringify((await t.kids(A))[1].show) === JSON.stringify(["created", "updated", "words"]), JSON.stringify((await t.kids(A))[1].show));
    await t.key("Escape"); await t.key("Escape");
    await t.settle();
    t.check("  the menu closed: the cursor where it was", (await t.js(caret)) === before, `${await t.js(caret)} (was ${before})`);
    // nested, recursive (2026-11-19, the user): a quote's mini header joined to its first block; quiet at rest
    // (2026-11-20, the user: "the header border and glow only shows up when selected or adjacent"): its border unseen
    // but when the quote is selected whole or its first block is the active one, each quote's own, at any depth
    await fetch(`http://127.0.0.1:${t.port}/api/act`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ do: "show", quote: QN, show: ["title", "words"] }) });
    await t.open(`#/p/${B}`); await t.open(`#/p/${N}`);
    const line = (sel) => `(() => { const l = document.querySelector('${sel}'); return !!l && getComputedStyle(l, "::after").content !== "none"; })()`;
    const outer = `.fw-doc > .ProseMirror > .fw-quote > .fw-top > .fw-top-label`, inner = `.fw-doc .fw-quote .fw-quote > .fw-top > .fw-top-label`;
    // how its box is drawn: "unseen", "glow <colour>" (its bottom edge, a neighbour's), "box <colour>"; and where its text is
    const look = (sel) => `(() => { const top = document.querySelector('${sel}').parentElement, cs = getComputedStyle(top);
      const r = top.firstElementChild.getBoundingClientRect(), at = [r.left, r.top].map(Math.round).join(",");
      if (cs.borderImageSource !== "none") return "glow " + cs.getPropertyValue("--lit-down").trim() + " @" + at;
      return (cs.borderTopColor === "rgba(0, 0, 0, 0)" ? "unseen" : "box " + cs.borderTopColor) + " @" + at; })()`;
    const root = (v) => t.js(`(() => { const e = document.createElement("i"); e.style.color = "var(${v})"; document.body.append(e);
      const c = getComputedStyle(e).color; e.remove(); return c; })()`);   // (as the glow's registered colour computes: rgb(…))
    const [hi, fg] = [await root("--box-hi"), await root("--fg")];
    const kind = (s) => s.split(" @")[0], where = (s) => s.split(" @")[1];
    await t.select("after the", { collapse: true }); await t.settle();
    const rest = [await t.js(look(outer)), await t.js(look(inner))];
    t.check("  at rest: the mini headers' boxes unseen, no line to their blocks", rest.every((s) => kind(s) === "unseen")
      && !(await t.js(line(outer))) && !(await t.js(line(inner))), rest.join(" | "));
    await t.shot("topline-rest.png");
    await t.select("first wo", { collapse: true }); await t.settle();
    let now = [await t.js(look(outer)), await t.js(look(inner))];
    t.check("  in a quote's first block (adjacent): its bottom edge glows as a neighbour's, its line drawn; not the quote's inside it",
      kind(now[0]) === `glow ${hi}` && kind(now[1]) === "unseen" && await t.js(line(outer)) && !(await t.js(line(inner))), now.join(" | "));
    t.check("  nothing moves as it lights", where(now[0]) === where(rest[0]), `${where(now[0])} (at rest ${where(rest[0])})`);
    await t.shot("topline-adjacent.png");
    await t.select("beta's", { collapse: true }); await t.settle();
    now = [await t.js(look(outer)), await t.js(look(inner))];
    t.check("  in the quote inside it (recursive): that one's, not the outer's (in it, not beside its header: unseen)",
      kind(now[1]) === `glow ${hi}` && kind(now[0]) === "unseen" && await t.js(line(inner)) && !(await t.js(line(outer))), now.join(" | "));
    t.check("  its box a block's, its text on the blocks' column, the line from it reaching the first block", await t.js(`(() => {
      const top = document.querySelector('${inner}').parentElement, q = top.parentElement, l = top.firstElementChild;
      const tb = top.getBoundingClientRect(), lb = l.getBoundingClientRect(), after = getComputedStyle(l, "::after");
      const first = q.querySelector(":scope > .fw-body > .ProseMirror > *"), fb = first.getBoundingClientRect();
      const tx = first.querySelector(".fw-text, p") || first, range = document.createRange(); range.selectNodeContents(tx);
      const textX = range.getClientRects()[0].left, lineTop = lb.top + parseFloat(after.top), lineBot = lineTop + parseFloat(after.height);
      return getComputedStyle(top).borderTopStyle === "solid" && Math.abs(lb.left - textX) < 1.5 && Math.abs(lineTop - tb.bottom) < 1.5 && Math.abs(lineBot - fb.top) < 1.5; })()`));
    t.check("  both titles in the body's weight", await t.js(`getComputedStyle(document.querySelector(".fw-title")).fontWeight === getComputedStyle(document.body).fontWeight
      && getComputedStyle(document.querySelector(".fw-mini-title")).fontWeight === getComputedStyle(document.body).fontWeight`));
    await t.shot("topline-nested.png");
    await t.select("first wo", { collapse: true }); await t.key("Escape"); await t.settle();
    now = [await t.js(look(outer)), await t.js(look(inner))];
    t.check("  its first block selected whole: the glow bright, as beside any block selected whole",
      kind(now[0]) === `glow ${fg}` && kind(now[1]) === "unseen" && await t.js(line(outer)), now.join(" | "));
    await t.key("Escape"); await t.settle();   // (Esc again: out to the quote, selected whole)
    await t.until(`!!document.querySelector(".fw-doc > .ProseMirror > .fw-quote.fw-chosen")`, 1000);
    now = [await t.js(look(outer)), await t.js(look(inner))];
    t.check("  the quote selected whole: its mini header's box shown, its line drawn; the one inside it its own (unseen)",
      kind(now[0]) === `box ${await t.js(`getComputedStyle(document.querySelector('${outer}').parentElement).borderTopColor`)}` && kind(now[0]) !== "unseen"
      && kind(now[1]) === "unseen" && await t.js(line(outer)) && where(now[0]) === where(rest[0]), now.join(" | "));
    await t.shot("topline-selected.png");
  },

  async popopen(t) {   // (motion on: ?motion) Turn into a quote and open it: the pop out (the cursor kept, through the quote), then a step into it (2026-11-19)
    await t.cdp("Page.navigate", { url: `http://127.0.0.1:${t.port}/?test&motion#/p/${A}@${A1}` });
    await t.until(`window.fw?.editor()?.id === "${A}"`, 6000);
    await t.settle();
    await t.select("first wo", { collapse: true });
    await t.key("e", 12);   // ⌘⇧E
    await t.until(`window.fw?.editor() && window.fw.editor().id !== "${A}" && window.fw.settled()`, 5000);
    t.check("⌘⇧E: popped out and opened, by a step into the quote", (await t.js(`window.fw.lastMove()`))?.dir === "in" && (await t.kids(A))[0].t === "quote",
      JSON.stringify(await t.js(`window.fw.lastMove()`)));
    t.check("  the cursor where it was, in the pericope opened", await t.js(`(() => { const s = window.fw.editor().view.state.selection;
      return s.empty && s.$from.parent.textContent === "first words" && s.$from.parentOffset === 8; })()`),
      await t.js(`(() => { const s = window.fw.editor().view.state.selection; return s.$from.parent.textContent + "|" + s.$from.parentOffset; })()`));
  },

  async motion(t) {   // (motion on: ?motion) ⌘O steps into the quote, the page becoming it; ⌘[ steps back out into it (2026-11-19)
    await t.cdp("Page.navigate", { url: `http://127.0.0.1:${t.port}/?test&motion#/p/${A}` });
    await t.until(`window.fw?.editor()?.id === "${A}"`, 6000);
    await t.settle();
    await t.js(`(() => { const v = window.fw.editor().view; v.focus(); let at = null;
      v.state.doc.descendants((n, pos) => { if (at === null && n.type.name === "quote") at = pos; });
      v.dispatch(v.state.tr.setSelection(window.fw.nodeSel(v.state.doc, at))); return true; })()`);
    const clean = `!document.querySelector(".fw-ghost, .fw-veil, .fw-target") && !document.documentElement.matches(".fw-stepping, .fw-swapping")
      && !document.querySelector(".fw-header").style.transform && document.querySelector(".fw-doc > .ProseMirror").style.opacity === ""`;
    await t.key("o", 4);
    await t.until(`window.fw?.editor()?.id === "${B}"`, 5000);
    await t.settle();
    t.check("⌘O: a step in, and nothing of it left on the page", (await t.js(`window.fw.lastMove()`))?.dir === "in" && await t.js(clean),
      JSON.stringify(await t.js(`window.fw.lastMove()`)));
    t.check("  from a quote selected whole: nothing active, no caret, until a key", await t.js(`!document.querySelector(".fw-doc .fw-here") && document.querySelector(".fw-doc > .ProseMirror").classList.contains("fw-selecting")`));
    await t.key("[", 4);
    await t.until(`window.fw?.editor()?.id === "${A}"`, 5000);
    await t.settle();
    t.check("  ⌘[: a step out, nothing of it left", (await t.js(`window.fw.lastMove()`))?.dir === "out" && await t.js(clean));
    t.check("  back from a page opened expanded and untouched (nothing active): the quote selected whole (2026-11-19, later)",
      await t.js(`(() => { const c = [...document.querySelectorAll(".fw-doc .fw-chosen")]; return c.length === 1 && c[0].matches('.fw-quote[data-pericope="${B}"]') && !document.querySelector(".fw-doc .fw-here"); })()`),
      await t.js(`[...document.querySelectorAll(".fw-doc .fw-chosen, .fw-doc .fw-here")].map((e) => e.className).join(" | ")`));
    await t.key("]", 4);
    await t.until(`window.fw?.editor()?.id === "${B}" && window.fw.settled()`, 5000);
    await t.js(`history.back(); 1`);   // (the browser's own back: a swipe, its button)
    await t.until(`window.fw?.editor()?.id === "${A}" && window.fw.settled()`, 5000);
    t.check("  the browser's own back: a step out too", (await t.js(`window.fw.lastMove()`))?.dir === "out" && await t.js(clean));
    await t.select("beta's", { collapse: true }); await t.settle();
    await t.key("o", 4);
    await t.until(`window.fw?.editor()?.id === "${B}" && window.fw.settled()`, 5000);
    t.check("⌘O from the cursor in a quote: the cursor where it was, in the block opened", await t.js(`(() => { const s = window.fw.editor().view.state.selection;
      return s.empty && s.$from.parent.textContent === "beta's words" && s.$from.parentOffset === 6; })()`));
    // (⌘[ and ⌘] land exactly where you were on the page you come back to: the caret, text selected, a block selected
    // whole, the quote selected; 2026-11-19, later)
    const inQuote = `(() => { const s = window.getSelection(), q = s.focusNode?.parentElement?.closest(".fw-quote");
      return q && q.dataset.pericope === "${B}" ? [s.anchorNode.textContent, s.anchorOffset, s.focusOffset].join("|") : null; })()`;
    const onB = `(() => { const s = window.getSelection(); return document.querySelector(".fw-doc .fw-chosen")?.textContent.trim()
      || (s.anchorNode && !s.anchorNode.parentElement.closest(".fw-quote") ? [s.anchorNode.textContent, s.anchorOffset, s.focusOffset].join("|") : null); })()`;
    const to = async (key, id) => { await t.key(key, 4); await t.until(`window.fw?.editor()?.id === "${id}" && window.fw.settled()`, 5000); };
    await to("[", A);
    t.check("  ⌘[ from the caret it opened at: the caret in the quote, as it was", await t.js(inQuote) === "beta's words|6|6"
      && await t.js(`!!document.querySelector('.fw-doc .fw-quote[data-pericope="${B}"] .fw-here')`), await t.js(inQuote));
    await to("]", B);
    await t.select("words"); await t.settle();
    await to("[", A);
    t.check("  moved on B (text selected), ⌘[: A as it was left, the caret in the quote", await t.js(inQuote) === "beta's words|6|6", await t.js(inQuote));
    await to("]", B);
    t.check("  ⌘]: B as it was left, the text selected", await t.js(onB) === "beta's words|7|12", await t.js(onB));
    await t.key("Escape"); await t.settle();
    await to("[", A);
    await to("]", B);
    t.check("  a block selected whole on B, ⌘[ then ⌘]: that block selected whole", await t.js(onB) === "beta's words", await t.js(onB));
  },

  async motionRepeat(t) {   // (motion on) stepping in and out again and again lands the same each time (2026-11-19, later: the
    // browser's own scroll restoration, and the quote selected only after the step, moved it up the screen each time)
    await t.cdp("Page.navigate", { url: `http://127.0.0.1:${t.port}/?test&motion#/p/${A}` });
    await t.until(`window.fw?.editor()?.id === "${A}"`, 6000);
    await t.settle();
    await t.js(`(() => { const v = window.fw.editor().view; v.focus(); let at = null;
      v.state.doc.descendants((n, pos) => { if (at === null && n.type.name === "quote") at = pos; });
      v.dispatch(v.state.tr.setSelection(window.fw.nodeSel(v.state.doc, at))); return true; })()`);
    const where = `(() => { const q = document.querySelector('.fw-doc .fw-quote[data-pericope="${B}"]'); return q && [Math.round(q.getBoundingClientRect().top), Math.round(scrollY)].join(","); })()`;
    const seen = [], dirs = [];
    for (let k = 0; k < 4; k++) {
      await t.key("o", 4);
      await t.until(`window.fw?.editor()?.id === "${B}" && window.fw.settled()`, 5000);
      dirs.push((await t.js(`window.fw.lastMove()`))?.dir);
      await t.key("[", 4);
      await t.until(`window.fw?.editor()?.id === "${A}" && window.fw.settled()`, 5000);
      dirs.push((await t.js(`window.fw.lastMove()`))?.dir);
      seen.push(await t.js(where));
    }
    t.check("⌘O then ⌘[, four times: each a step, the quote back at the same place on screen, the page scrolled the same (within a pixel: no creeping)",
      dirs.join() === "in,out,in,out,in,out,in,out" && seen[0] && seen.every((s) => s && s.split(",").every((v, k) => Math.abs(v - seen[0].split(",")[k]) <= 1)), `${dirs.join()} · ${seen.join(" | ")}`);
  },

  async blockNav(t) {   // a block selected deliberately: ↑/↓ block to block at its level, flowing out past a container's or
    // quote's end; → (or Enter) in a level, onto text to writing; ← out a level, at the top to writing; a quote only
    // arrowed onto still lets the arrow in (2026-11-19, later)
    const at = `(() => { const c = [...document.querySelectorAll(".fw-doc .fw-chosen")].filter((e) => !e.parentElement.closest(".fw-chosen"));
      const short = (x) => (x || "").replace(/\\s+/g, " ").trim();
      if (c.length) return c.map((e) => e.matches(".fw-quote") ? "quote:" + e.dataset.pericope.slice(-4) : "block:" + short(e.querySelector(".fw-text, .fw-qtext")?.textContent || e.textContent)).join("+");
      const s = window.getSelection(); return "caret:" + short(s.focusNode?.textContent) + "@" + s.focusOffset; })()`;
    const walk = async (keys) => { const out = []; for (const [k, m = 0] of keys) { await t.key(k, m); await t.settle(); out.push(await t.js(at)); } return out; };
    const same = (got, want) => JSON.stringify(got) === JSON.stringify(want);
    await t.open(`#/p/${R}`);
    await t.select("r words", { collapse: true });
    let got = await walk([["Escape"], ["ArrowDown"], ["ArrowDown"], ["ArrowUp"], ["ArrowUp"]]);
    t.check("Esc, then ↓↓↑↑: block to block (quotes whole, not into them)",
      same(got, ["block:r words", "quote:b000", "quote:c000", "quote:b000", "block:r words"]), JSON.stringify(got));
    await walk([["ArrowDown"], ["ArrowDown"], ["ArrowDown"]]);
    t.check("  ↓ past the page's last block: its foot's search (2026-11-20, as from text)", await t.until(`!!document.activeElement?.closest(".fw-on-pericope .fw-suggested")`, 1000));
    await t.select("r words", { collapse: true }); await t.key("Escape"); await t.settle();
    got = await walk([["ArrowDown", 8]]);
    t.check("  Shift+↓ still grows the selection", same(got, ["block:r words+quote:b000"]), JSON.stringify(got));
    await t.key("Escape"); await t.select("r words", { collapse: true }); await t.key("Escape"); await t.settle();
    got = await walk([["Enter"]]);
    t.check("  Enter on a block of text: the caret at its end", same(got, ["caret:r words@7"]), JSON.stringify(got));
    got = await walk([["ArrowDown"], ["ArrowDown"]]);
    t.check("  arrowing from text: a quote reached is gone into, not selected whole (2026-11-20), and on into the next",
      same(got, ["caret:beta's words@0", "caret:the quick brown fox@0"]), JSON.stringify(got));
    await t.open(`#/p/${N}`);
    await t.select("after the quotes", { collapse: true });
    got = await walk([["Escape"], ["ArrowUp"], ["Enter"], ["ArrowDown"], ["ArrowDown"], ["ArrowUp"]]);
    t.check("a quote holding blocks: Enter selects its first block; ↓ along them; past its last, out to the block after it; ↑ the quote whole",
      same(got, ["block:after the quotes", "quote:a000", "block:first words", "quote:b000", "block:after the quotes", "quote:a000"]), JSON.stringify(got));
    got = await walk([["ArrowRight"], ["ArrowLeft"], ["ArrowRight"], ["ArrowRight"]]);
    t.check("  → in a level (its first block), ← out (the quote), → in, → onto text: writing at its start",
      same(got, ["block:first words", "quote:a000", "block:first words", "caret:first words@0"]), JSON.stringify(got));
    got = await walk([["Escape"], ["ArrowLeft"], ["ArrowLeft"]]);
    t.check("  ← out of a block in a quote: the quote; ← at the top level: writing, at the start of its text",
      same(got, ["block:first words", "quote:a000", "caret:first words@0"]), JSON.stringify(got));
    await t.open(`#/p/${S0}`);
    await t.select("the only block", { collapse: true });
    got = await walk([["Escape"], ["Escape"], ["Enter"], ["Enter"]]);
    t.check("a container: Esc out a level, Enter back in (its first block), Enter the caret at its end",
      same(got, ["block:the only block inside", "block:the only block inside", "block:the only block inside", "caret:the only block inside@21"]), JSON.stringify(got));
    const chosen = `[...document.querySelectorAll(".fw-doc .fw-chosen")].map((e) => e.matches(".fw-container") ? "container" : "text").join()`;
    const kinds = [];
    for (const k of ["Escape", "ArrowLeft", "ArrowRight", "ArrowRight"]) { await t.key(k); await t.settle(); kinds.push(await t.js(chosen) || await t.js(at)); }
    t.check("  ← out to the container, → back in (its block), → writing at its start",
      same(kinds, ["text", "container", "text", "caret:the only block inside@0"]), JSON.stringify(kinds));
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
    // (until: between text blocks the browser moves the caret itself, and ProseMirror reads it on a later selectionchange)
    t.check("  ↓ out of its last line into the next block: the cursor still on screen", await t.until(`${onScreen} && window.fw.editor().context().block?.id === "${T2}"`, 2000), await t.js(`JSON.stringify([window.fw.editor().view.coordsAtPos(window.fw.editor().view.state.selection.head), innerHeight, scrollY, document.documentElement.scrollHeight, window.fw.editor().context().block?.id])`));
    await t.key("ArrowUp");
    await t.settle();
    t.check("  ↑ back into it, at its last line: on screen", await t.until(`${onScreen} && window.fw.editor().context().block?.id === "${T1}"`, 2000), await t.js(`JSON.stringify([window.fw.editor().view.coordsAtPos(window.fw.editor().view.state.selection.head), innerHeight, scrollY, document.documentElement.scrollHeight, window.fw.editor().context().block?.id])`));
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

  async arrowFlow(t) {   // the arrows flow through quotes inside quotes, going into each (2026-11-20: never selected whole on the way)
    // (nested: a quote of alpha [first words, a quote of beta [beta's words]], then "after the quotes")
    const at = `(() => { const ch = document.querySelector(".fw-chosen"); const short = (x) => (x || "").replace(/\\s+/g, " ").trim();
      if (ch) return "whole:" + short(ch.querySelector(".fw-qtext, .fw-text")?.textContent);
      return "text:" + short(window.getSelection().focusNode?.textContent); })()`;
    const walk = async (key, n) => { const out = []; for (let k = 0; k < n; k++) { await t.key(key); await t.settle(); out.push(await t.js(at)); } return out; };
    await t.open(`#/p/${N}`);
    await t.select("after the quotes", { collapse: true, start: true });
    const up = await walk("ArrowUp", 2);
    t.check("↑ from below: into the outer quote and on into the inner, at its end; then the outer's text (2026-11-20: gone into, not selected whole)",
      JSON.stringify(up) === JSON.stringify(["text:beta's words", "text:first words"]), JSON.stringify(up));
    await t.key("ArrowUp");
    t.check("  ↑ out of the page's first quote: the header's title, as from text", await t.until(`!!document.activeElement?.matches(".fw-title")`, 1000));
    await t.select("first words", { collapse: true });
    const down = await walk("ArrowDown", 2);
    t.check("↓ back: into the inner quote's text, then out of both (nothing after them inside) to what's below",
      JSON.stringify(down) === JSON.stringify(["text:beta's words", "text:after the quotes"]), JSON.stringify(down));
    await t.select("beta's words", { collapse: true });
    const esc = await walk("Escape", 2);
    t.check("Esc steps out a level each time: the inner quote (its one block is its box), then the outer",
      JSON.stringify(esc) === JSON.stringify(["whole:beta's words", "whole:first words"]), JSON.stringify(esc));
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
    await t.shot("tab-arrow.png", await t.js(`(() => { const r = document.querySelector(".fw-doc .fw-quote > .fw-top > .fw-open").getBoundingClientRect();
      return { x: r.x - 30, y: r.y - 8, width: r.width + 38, height: r.height + 16, scale: 8 }; })()`));
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
    const qTop = `[...document.querySelectorAll(".fw-tabs .fw-tab")].find(e => e.textContent === "1")?.getBoundingClientRect().top`;
    const was = await t.js(qTop);
    await t.key("Escape"); await t.key("Escape");   // (the block whole, then the quote around it)
    // (2026-11-19: placed by the page, not by which tabs show; moved only a little, by its first block's room going)
    t.check("  stepping out to the quote: its tab stays where it was (bar the block's room going)",
      await t.until(`!!document.querySelector(".fw-tab-filled") && document.querySelector(".fw-tab-filled").textContent === "1"`, 1000)
      && Math.abs((await t.js(qTop)) - was) < 4, `${was} → ${await t.js(qTop)}`);
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
    t.check("  the quote around it (the path): faint, not the focus's bright red", await t.until(`getComputedStyle(document.querySelector(".fw-doc > .ProseMirror > .fw-quote")).outlineColor === "rgba(154, 106, 106, 0.38)"`, 1000),
      await t.js(`getComputedStyle(document.querySelector(".fw-doc > .ProseMirror > .fw-quote")).outlineColor`));
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
    t.check("every field shown, an empty one saying none (2026-11-21)", await t.js(`(() => { const h = document.querySelector(".fw-hbox").textContent.replace(/ +/g, " "), flat = h.replace(/ /g, "");
      return ["created ", "updated ", "words ", "last visited ", "backlinks", "tags", "title"].every((f) => h.includes(f))
        && h.includes("last visited none") && !h.includes("paraphrase of") && flat.includes("tagsnone"); })()`),
      await t.js(`document.querySelectorAll(".fw-hbox").length + " " + document.querySelector(".fw-header").outerHTML.slice(0, 1500)`));
  },

  async kinds(t) {
    await t.open(`#/p/${B}@${B1}`);
    await t.key("ArrowUp");
    t.check("↑ from the first line: the title", await t.until(`document.activeElement?.classList.contains("fw-title")`, 1000));
    await t.key("ArrowUp");
    t.check("  ↑ again: the kinds line", await t.until(`document.activeElement?.classList.contains("fw-chip")`, 1000));
    await t.key("h");   // (typing on the line: the picker, with it typed)
    await t.until(`document.querySelector(".fw-menu")?.innerText.includes("tag ›")`, 2000);
    await t.type("aiku");
    t.check("  the picker: + new kind, with what's typed", await t.until(`document.querySelector(".fw-menu")?.innerText.includes("+ new tag “haiku”")`, 2000));
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

  // the kinds view (#/kinds, 2026-11-22): every kind folded, → its members, Enter opens; + new kind; a kind's page lists them
  async kindsview(t) {
    const say = (block, answer) => t.js(`fetch("/api/act", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ do: "kind", block: "${block}", kind: "${K}", answer: ${answer} }) }).then((r) => r.ok)`);
    await t.open("#/");
    await say(A, true); await say(B, true);
    t.check("only a pericope has kinds: a block inside one refused", !(await say(B1, true)));
    await t.key("u", 4 | 8);
    const rows = `[...document.querySelectorAll(".fw-kindsview .fw-row")].map((r) => r.innerText.replace(/\\s+/g, " ").trim()).join(" | ")`;
    t.check("⌘⇧U: the kinds view, each kind folded with its count", await t.until(`location.hash === "#/tags" && ${rows} === "▸ poem 2 + 1 sure + 1 maybe | ▸ no tag 4 | + new tag"`, 3000), await t.js(rows));
    await t.key("ArrowRight");
    t.check("  →: its members, yours newest first, then the model's sure ones, dim, then its maybes",
      await t.until(`${rows}.startsWith("▾ poem 2 + 1 sure + 1 maybe | beta") && ${rows}.includes("| alpha") && ${rows}.includes("| fox")
        && ${rows}.includes("| masker?") && document.querySelectorAll(".fw-member.fw-dim").length === 2 && document.querySelectorAll(".fw-member.fw-maybe").length === 1`, 2000), await t.js(rows));
    await t.key("ArrowDown");
    await t.key("Enter");
    t.check("  Enter on a member: opened", await t.until(`window.fw?.editor()?.id === "${B}"`, 4000));
    await t.key("u", 4 | 8);
    await t.until(`location.hash === "#/tags" && document.querySelector(".fw-kindsview .fw-sel")`, 3000);
    t.check("  back again: still open", await t.until(`document.querySelectorAll(".fw-member").length === 4`, 3000));
    for (let i = 0; i < 3; i++) await t.key("ArrowDown");   // (from the kind: beta, alpha, fox, the sure guess)
    await t.key("y");
    t.check("  Y on a guess: yes, it joins yours, the next selected", await t.until(`${rows}.startsWith("▾ poem 3 + 1 maybe") && document.querySelector(".fw-sel")?.innerText.includes("masker")`, 3000)
      && (await t.get(`/api/pericope/${T}`)).kindTokens.some((x) => x.mark === "yes"), await t.js(rows));
    await t.key("n");
    t.check("  N on a maybe: no, it goes", await t.until(`${rows}.startsWith("▾ poem 3 | ") && !${rows}.includes("masker")`, 3000)
      && (await t.get(`/api/pericope/${M}`)).kindTokens.some((x) => x.mark === "no"), await t.js(rows));
    await say(T, null); await say(M, null);   // (as it was: fox sure, masker maybe)
    t.check("  answered elsewhere: followed", await t.until(`${rows}.startsWith("▾ poem 2 + 1 sure + 1 maybe")`, 3000), await t.js(rows));
    for (let i = 0; i < 4; i++) await t.key("ArrowUp");   // (from + new kind, where N left it: up to beta)
    await t.key("n");
    t.check("  N on one of yours: taken out (a no)", await t.until(`${rows}.startsWith("▾ poem 1 + 1 sure + 1 maybe | alpha")`, 3000)
      && (await t.get(`/api/pericope/${B}`)).kindTokens.some((x) => x.mark === "no"), await t.js(rows));
    await say(B, true);
    await t.until(`${rows}.startsWith("▾ poem 2 + 1 sure + 1 maybe")`, 3000);
    for (let i = 0; i < 5; i++) await t.key("ArrowUp");   // (up to poem)
    await t.key("ArrowLeft"); await t.key("ArrowDown");
    await t.key("ArrowRight");
    t.check("  no kind, last: the pericopes of none (a maybe isn't one), newest first", await t.until(`${rows}.includes("▾ no tag 4 | nested") && ${rows}.includes("| masker")
      && !${rows}.includes("| fox") && !${rows}.includes("| poem ")`, 2000), await t.js(rows));
    await t.key("ArrowLeft"); await t.key("ArrowDown");
    t.check("  ←: folded; ↓ to + new kind", await t.until(`${rows} === "▸ poem 2 + 1 sure + 1 maybe | ▸ no tag 4 | + new tag" && document.querySelector(".fw-sel")?.classList.contains("fw-newkind")`, 2000), await t.js(rows));
    await t.key("Enter");
    await t.until(`document.activeElement?.matches(".fw-newkind .fw-input")`, 2000);
    await t.type("song");
    await t.key("Enter");
    t.check("  + new kind: named, made, selected", await t.until(`${rows}.includes("▸ song 0") && document.querySelector(".fw-sel")?.innerText.includes("song")`, 3000)
      && (await t.get("/api/kinds")).kinds.some((k) => k.name === "song"), await t.js(rows));
    await t.key("Backspace", 4);
    await t.until(`!!document.querySelector(".fw-ask")`, 2000);
    await t.key("y");
    t.check("  ⌘⌫ on a kind, asked, y: deleted", await t.until(`${rows} === "▸ poem 2 + 1 sure + 1 maybe | ▸ no tag 4 | + new tag"`, 3000)
      && !(await t.get("/api/kinds")).kinds.some((k) => k.name === "song"), await t.js(rows));
    await t.key("ArrowUp");
    await t.key("Enter");
    t.check("  Enter on a kind: its page, its members below what it says", await t.until(`window.fw?.editor()?.id === "${K}" && document.querySelectorAll(".fw-members .fw-row").length === 4`, 4000));
    await t.end();
    await t.key("ArrowDown");
    t.check("  ↓ past its last block: into them", await t.until(`document.querySelector(".fw-members .fw-sel")?.innerText.includes("beta")`, 2000));
    await t.key("ArrowUp");
    t.check("  ↑ from the first: back in the kind", await t.until(`!document.querySelector(".fw-members .fw-sel") && window.fw.editor()?.view.hasFocus()`, 2000));
    await t.key("Escape");
  },
};
scenarios.nestback = async (t) => {   // ⌘↵ then ⌫, over and over: never deeper (2026-11-23: in a quote it nested forever)
  await t.open(`#/p/${A}`);
  await t.select("words", { collapse: true, start: true });   // ("first |words")
  await t.key("Enter", 4);
  await t.until(`!!document.querySelector(".fw-doc > .ProseMirror > .fw-container")`, 2000);
  await t.key("Backspace");
  t.check("⌘↵ then ⌫: one block of text again, the cursor where it was", await t.until(`!document.querySelector(".fw-doc > .ProseMirror > .fw-container")
    && document.getSelection().anchorNode?.textContent === "first words" && document.getSelection().anchorOffset === 6`, 2000));
  await t.key("Enter", 4);
  await t.until(`!!document.querySelector(".fw-doc > .ProseMirror > .fw-container")`, 2000);
  await t.select("first ", { collapse: true });   // (the end of the first half: "first |")
  await t.key("Delete");
  t.check("  ⌘↵ then ⌦ at the end of its first half: back too", await t.until(`!document.querySelector(".fw-doc > .ProseMirror > .fw-container")
    && [...document.querySelectorAll(".fw-doc > .ProseMirror > .fw-text")].some((e) => e.innerText === "first words")`, 2000));
  await t.select("first words", { collapse: true });
  await t.key("ArrowDown");   // (into the quote of beta)
  const quote = `(() => { const k = [...window.fw.editor().kids][0]; return k.view.state.doc.toString(); })()`;
  for (let i = 0; i < 4; i++) {
    await t.key("Enter", 4);
    await t.until(`${quote}.startsWith("doc(container")`, 2000);
    await t.key("Backspace");
    await t.until(`!${quote}.includes("container")`, 2000);
  }
  for (let i = 0; i < 3; i++) {   // (⌘ held through both: ⌘↵ then ⌘⌫, the user's way)
    await t.key("Enter", 4);
    await t.until(`${quote}.startsWith("doc(container")`, 2000);
    await t.key("Backspace", 4);
    await t.until(`!${quote}.includes("container")`, 2000);
  }
  t.check("  four times in a quote, three more with ⌘ held: no deeper, one block of text", await t.js(`${quote} === 'doc(text_block("beta\\'s words"))'`), await t.js(quote));
  await t.type("X");
  await t.until(`${quote}.includes("Xbeta")`, 2000);
  await t.settle();
  const kids = await t.kids(B);
  t.check("  saved: beta one block of text again, its own id, typed where the cursor was", kids.length === 1 && kids[0].t === "text" && kids[0].id === B1
    && kids[0].text === "Xbeta's words", JSON.stringify(kids));
};

scenarios.expr = async (t) => {   // the expr branch: an expression block, Hazel's engine, the code on ⌘⇧X
  await t.open(`#/p/${A}`);
  await t.end();
  await t.key("Enter");
  await t.type("/");
  await t.type("expr");
  await t.until(`!!document.querySelector(".fw-slash, .fw-menu")`, 2000);
  await t.key("Enter");
  t.check("/ → Expression: an expression block, its code open to write", await t.until(`!!document.activeElement?.closest(".fw-expr-code")`, 2000));
  t.check("  its caret shows (the block selected whole meanwhile hides the page's)", await t.until(`!!document.querySelector(".fw-expr-code .cm-cursor")`, 2000));
  await t.type('if 3 * 4 > 10 then "big" ++ "!" else "small"');
  t.check("  the engine loads; the result follows the code, dim below it", await t.until(`document.querySelector(".fw-expr-out")?.textContent === '"big!"'`, 8000),
    await t.js(`document.querySelector(".fw-expr-out")?.textContent`));
  await t.shot("expr-coding.png", { x: 0, y: 100, width: 1100, height: 260 });
  await t.key("x", 4 | 8);
  t.check("  a block as any: its number in the gutter, a tab when it's selected", await t.until(`!!document.querySelector(".fw-tab") && [...document.querySelectorAll(".fw-tab")].some((x) => x.textContent.trim() === "3")`, 2000)
    || await t.js(`getComputedStyle(document.querySelector(".fw-expr"), "::before").content !== "none"`), await t.js(`[...document.querySelectorAll(".fw-tab")].map((x) => x.textContent).join()`));
  t.check("  ⌘⇧X: the code hidden, the result shown, the block selected", await t.until(`!document.querySelector(".fw-expr-code") && !!document.querySelector(".fw-expr.ProseMirror-selectednode")`, 2000));
  await t.settle();
  await t.shot("expr-selected.png", { x: 0, y: 0, width: 1100, height: 320 });
  const kid = (await t.kids(A)).find((k) => k.t === "expr");
  t.check("  saved: an expression block, its source", kid?.source === 'if 3 * 4 > 10 then "big" ++ "!" else "small"', JSON.stringify(await t.kids(A)));
  await t.open(`#/p/${B}`);
  await t.open(`#/p/${A}`);
  t.check("  opened again: its result (a String, as Hazel prints it)", await t.until(`document.querySelector(".fw-expr-out")?.textContent === '"big!"'`, 8000));
  const r = await t.js(`(() => { const b = document.querySelector(".fw-expr").getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2]; })()`);
  await t.click(r[0], r[1]);
  await t.until(`!!document.querySelector(".fw-expr.ProseMirror-selectednode")`, 2000);
  await t.key("x", 4 | 8);
  await t.until(`!!document.activeElement?.closest(".fw-expr-code")`, 4000);
  await setCode(t, "1 + 2 +");
  t.check("  unfinished: a hole, the rest worked out", await t.until(`document.querySelector(".fw-expr-out")?.textContent === "3 + ?"`, 5000),
    await t.js(`document.querySelector(".fw-expr-out")?.textContent + " | " + document.querySelector(".fw-expr-codebox")?.fwCode.state.doc.toString()`));
  await t.key("Escape");   // (the code closed: the block selected whole)
  await t.until(`!document.querySelector(".fw-expr-code") && !!document.querySelector(".fw-expr.ProseMirror-selectednode")`, 3000);
  await t.settle();
  await t.key("e", 4);   // (⌘E: Turn into a quote)
  t.check("⌘E on an expression block: a pericope of its own, quoted here, showing its result",
    await t.until(`!!document.querySelector(".fw-quote .fw-expr-out") && document.querySelector(".fw-quote .fw-expr-out").textContent === "3 + ?"`, 5000),
    await t.js(`document.querySelector(".fw-quote")?.innerText`));
  await t.settle();
  const q = (await t.kids(A)).find((k) => k.t === "quote" && k.target !== B);
  t.check("  in the store: a quote here, the expression in its new pericope", !!q && (await t.kids(q.target))[0]?.t === "expr", JSON.stringify(await t.kids(A)));
  await t.open(`#/p/${q.target}`);
  t.check("  its pericope opened: the expression, its result; its type in the header", await t.until(`document.querySelector(".fw-expr-out")?.textContent === "3 + ?"`, 5000)
    && await t.js(`document.querySelector(".fw-label").textContent === "expression"`), await t.js(`document.querySelector(".fw-label").textContent`));

};

/** The open code box's text set to `src` (CodeMirror's own change: told back to the block as typing is). */
const setCode = (t, src) => t.js(`(() => { const v = document.querySelector(".fw-expr-codebox").fwCode;
  v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: ${JSON.stringify(src)} } }); return 1; })()`);

/** An expression block put in at the end of the open pericope, its code `src`, then shown at rest (⌘⇧X). */
async function addExpr(t, src) {
  await t.end();
  await t.key("Enter");
  await t.type("/");
  await t.type("expr");
  await t.until(`!!document.querySelector(".fw-slash, .fw-menu")`, 2000);
  await t.key("Enter");
  await t.until(`!!document.activeElement?.closest(".fw-expr-code")`, 2000);
  await setCode(t, src);
  await t.key("x", 4 | 8);
  await t.until(`!document.querySelector(".fw-expr-code")`, 2000);
  await t.settle();
}
const lastOut = `[...document.querySelectorAll(".fw-doc .fw-expr > .fw-expr-out")].at(-1)`;

scenarios.codebox = async (t) => {   // the code written in CodeMirror (2026-11-24): highlighted; @ opens fw's search; a reference drawn as its title
  await t.open(`#/p/${A}`);
  await t.end();
  await t.key("Enter");
  await t.type("/");
  await t.type("expr");
  await t.until(`!!document.querySelector(".fw-slash, .fw-menu")`, 2000);
  await t.key("Enter");
  await t.until(`!!document.activeElement?.closest(".fw-expr-code")`, 2000);
  await t.type("let n = 3 in ");
  await t.settle();
  await t.type("wordC");
  await t.until(`!!document.querySelector(".cm-tooltip-autocomplete")`, 2000);
  await sleep(150);   // (CodeMirror takes no accept in the first 75 ms of the list: a slip never picks)
  await t.key("Tab");
  t.check("Tab takes the completion offered", await t.until(`document.querySelector(".fw-expr-codebox").fwCode.state.doc.toString().endsWith("wordCount")`, 2000),
    await t.js(`document.querySelector(".fw-expr-codebox").fwCode.state.doc.toString()`));
  await t.js(`(() => { const v = document.querySelector(".fw-expr-codebox").fwCode; v.dispatch({ changes: { from: v.state.doc.length - "wordCount".length, to: v.state.doc.length, insert: "" } }); return 1; })()`);
  await t.settle();
  const caretIn = `(() => { const s = getSelection(); const c = document.querySelector(".fw-expr-code .cm-cursor");
    return !!s.anchorNode && !!s.anchorNode.parentElement?.closest(".cm-content") && s.isCollapsed && !!document.activeElement?.closest(".fw-expr-code")
      && !!c && c.getBoundingClientRect().height > 0 && getComputedStyle(c).borderLeftColor !== "rgba(0, 0, 0, 0)"; })()`;
  t.check("while typing, the caret stays in the code (the page's selection never takes it)", await t.js(caretIn),
    await t.js(`(() => { const s = getSelection(); return (s.anchorNode?.nodeName || "none") + " in " + (s.anchorNode?.parentElement?.className || "") + " · active " + document.activeElement?.className + " · caret " + getComputedStyle(document.querySelector(".fw-expr-code .cm-content")).caretColor; })()`));
  t.check("highlighted: a keyword coloured apart from a name", await t.until(`(() => {
    const spans = [...document.querySelectorAll(".fw-expr-code .cm-line span")];
    const c = (w) => spans.find((x) => x.textContent === w) && getComputedStyle(spans.find((x) => x.textContent === w)).color;
    return c("let") && c("let") !== getComputedStyle(document.querySelector(".fw-expr-code .cm-line")).color; })()`, 2000));
  await t.type("title(");
  await t.type("@");
  t.check("@: fw's search opens at once", await t.until(`!!document.querySelector(".cm-tooltip-autocomplete li")`, 3000));
  await t.type("fox");
  t.check("  typing narrows it: the pericope titled fox offered", await t.until(`[...document.querySelectorAll(".cm-tooltip-autocomplete li")].some((li) => li.textContent.includes("fox"))`, 3000),
    await t.js(`document.querySelector(".cm-tooltip-autocomplete")?.innerText`));
  await t.until(`document.querySelector(".cm-tooltip-autocomplete li[aria-selected]")?.textContent.includes("fox")`, 2000);
  await t.shot("codebox-at.png", { x: 0, y: 0, width: 1100, height: 520 });
  await t.key("Enter");
  await t.type(")");
  const src = () => t.js(`document.querySelector(".fw-expr-codebox").fwCode.state.doc.toString()`);
  t.check("  picked: the source holds its id", (await src()) === `let n = 3 in title(@${T})`, await src());
  t.check("  drawn as its title, a chip", await t.until(`document.querySelector(".fw-expr-code .fw-ref")?.textContent === "fox"`, 2000),
    await t.js(`document.querySelector(".fw-expr-code .cm-line")?.innerHTML`));
  t.check("  the result follows", await t.until(`document.querySelector(".fw-expr-out")?.textContent === '"fox"'`, 5000), await t.js(`document.querySelector(".fw-expr-out")?.textContent`));
  await t.shot("codebox.png", { x: 0, y: 0, width: 1100, height: 400 });
  await t.key("ArrowLeft");
  await t.key("Backspace");
  t.check("  ⌫ just after it deletes it whole", (await src()) === "let n = 3 in title()", await src());
  await t.key("z", 4);
  t.check("  ⌘Z puts it back", (await src()) === `let n = 3 in title(@${T})`, await src());
  await t.key("Escape");
  t.check("Esc: the code closed, the block selected", await t.until(`!document.querySelector(".fw-expr-code") && !!document.querySelector(".fw-expr.ProseMirror-selectednode")`, 2000));
  await t.settle();
  t.check("  saved with the id", (await t.kids(A)).find((k) => k.t === "expr")?.source === `let n = 3 in title(@${T})`, JSON.stringify(await t.kids(A)));
};

scenarios.exprbrowse = async (t) => {   // a value's blocks: moved through as any nesting, at block level; no caret, nothing changes them (2026-11-24)
  await t.open(`#/p/${A}`);
  await addExpr(t, `Blocks([body(@${T}), text("after")])`);
  const out = `[...document.querySelectorAll(".fw-doc .fw-expr > .fw-expr-out")].at(-1)`;
  const val = `${out}?.querySelector(":scope > .fw-body > .ProseMirror")`;
  await t.until(`${val}?.children.length === 2`, 8000);
  const before = await t.js(`${val}.textContent`);
  const chosen = `(() => { const c = [...(${out}?.querySelectorAll(".fw-chosen") || [])].at(-1); return c ? c.textContent : null; })()`;
  const noCaret = `(() => { const s = getSelection(); return !(s.rangeCount && s.isCollapsed && s.anchorNode?.parentElement?.closest(".fw-expr-out")); })()`;
  const FOX = "↗the quick brown foxjumps over the dog";   // (body(@fox): a From, drawn as a quote of fox, its ↗ first)
  await t.select("first words", { collapse: true });
  for (let i = 0; i < 8 && !(await t.js(chosen)); i++) await t.key("ArrowDown");
  t.check("the arrows go into a value: its first block (body(@fox), a green quote) selected whole, no caret", (await t.js(chosen)) === FOX && await t.js(noCaret), String(await t.js(chosen)));
  t.check("  its tabs: the expression's green on the path", await t.until(`!!document.querySelector(".fw-tab.fw-tab-expr")`, 2000));
  await t.type("zz");
  await t.key("Backspace");
  await t.key("Tab");
  t.check("  typing, ⌫ and Tab change nothing", (await t.js(`${val}.textContent`)) === before, await t.js(`${val}.textContent`));
  await t.key("Enter");
  t.check("  Enter: a level in, the quote's first block (as any quote)", (await t.js(chosen)) === "the quick brown fox" && await t.js(noCaret), String(await t.js(chosen)));
  await t.key("ArrowDown");
  t.check("  ↓ the next block", (await t.js(chosen)) === "jumps over the dog", String(await t.js(chosen)));
  await t.key("ArrowDown");
  t.check("  ↓ past the quote's last: the block after it, a level out", (await t.js(chosen)) === "after", String(await t.js(chosen)));
  await t.key("ArrowRight");
  t.check("  → on text: nothing (no caret in a value)", (await t.js(chosen)) === "after" && await t.js(noCaret), String(await t.js(chosen)));
  const r = await t.js(`(() => { const e = ${val}.querySelector(".fw-quote .fw-text"); const b = e.getBoundingClientRect(); return [b.left + 40, b.top + b.height / 2]; })()`);
  await t.click(r[0], r[1]);
  t.check("  a click in its text: that block selected whole, no caret", await t.until(`${chosen} === "the quick brown fox"`, 2000) && await t.js(noCaret),
    String(await t.js(chosen)));
  await t.key("ArrowLeft");
  t.check("  ←: out a level, the quote", (await t.js(chosen)) === FOX, String(await t.js(chosen)));
  await t.key("ArrowLeft");
  t.check("  ← again: out of the value, the expression selected whole", await t.until(`[...document.querySelectorAll(".fw-expr.ProseMirror-selectednode")].length === 1 && ${chosen} === null`, 2000));
  const lit = `getComputedStyle(document.querySelector(".fw-expr.ProseMirror-selectednode")).getPropertyValue("--lit-mid")`;
  t.check("  selected whole, green", await t.until(`${lit} === "rgb(124, 203, 154)"`, 2000), await t.js(lit));
  await t.key("ArrowRight");
  t.check("  →: in a level, its first block", await t.until(`${chosen} === ${JSON.stringify(FOX)}`, 2000), String(await t.js(chosen)));
  await t.key("Enter");
  await t.shot("exprbrowse.png", { x: 0, y: 0, width: 1100, height: 560 });
  await t.settle();
  t.check("  the store: just the expression, its source as written", (await t.kids(A)).filter((k) => k.t === "expr").map((k) => k.source).join() === `Blocks([body(@${T}), text("after")])`,
    JSON.stringify(await t.kids(A)));
};

scenarios.expropen = async (t) => {   // TYPE.md: if you can reference it, you can open it; any @ref is a backlink (2026-11-24)
  await t.open(`#/p/${A}`);
  await addExpr(t, `body(@${T})`);
  await t.until(`!!document.querySelector(".fw-doc .fw-expr .fw-from")`, 8000);
  await t.key("o", 4);
  t.check("⌘O on an expression whose value is one From: its source opens", await t.until(`location.hash.startsWith("#/p/${T}")`, 3000), await t.js("location.hash"));
  await t.open(`#/p/${A}`);
  await addExpr(t, `Blocks([body(@${T}), body(@${B})])`);
  await t.until(`[...document.querySelectorAll(".fw-doc .fw-expr")].at(-1)?.querySelectorAll(".fw-from").length === 2`, 8000);
  await t.key("o", 4);
  const rows = `[...document.querySelectorAll(".fw-menu li, .fw-menu .fw-row, .fw-menu button")].map((x) => x.textContent.trim()).filter(Boolean)`;
  t.check("  two references: ⌘O lists them to pick from", await t.until(`(() => { const r = ${rows}; return r.some((x) => x.startsWith("fox")) && r.some((x) => x.startsWith("beta")); })()`, 2000),
    await t.js(`document.querySelector(".fw-menu")?.innerText`));
  await t.key("Escape");
  await t.key("Escape");
  await t.settle();
  const back = (await t.get(`/api/pericope/${T}`)).backlinkRows || [];
  t.check("any @reference in an expression is a backlink of what it names", back.some((r) => r.kind === "expression" && r.open === A), JSON.stringify(back));
};

scenarios.neighbours = async (t) => {   // above and below: the peer blocks around an expression, where it sits now (2026-11-24)
  await t.open(`#/p/${A}`);
  await t.end();
  await t.type("three little words");
  await addExpr(t, `wordCount(above)`);
  const out = `[...document.querySelectorAll(".fw-doc .fw-expr > .fw-expr-out")].at(-1)`;
  t.check("wordCount(above): the block just above it", await t.until(`${out}?.textContent === "3"`, 8000), await t.js(`${out}?.outerHTML`));
  await t.select("three little words", { collapse: true });
  await t.type(" and two");
  t.check("  live: it follows each key in that block", await t.until(`${out}?.textContent === "5"`, 2000), await t.js(`${out}?.textContent`));
  await addExpr(t, `body(below)`);
  const below = `${out}?.querySelector(".fw-from .fw-text")?.textContent`;
  t.check("body(below): a window on the (empty) block below it", await t.until(`${out}?.querySelector(".fw-from") && ${below} === ""`, 4000), await t.js(`${out}?.outerHTML`));
  await t.key("ArrowDown");   // (into the block below it)
  await t.type("now below");
  t.check("  written in: shown there, live", await t.until(`${below} === "now below"`, 4000), await t.js(`${out}?.outerHTML`));
  const first = `[...document.querySelectorAll(".fw-doc .fw-expr > .fw-expr-out")].at(-2)`;
  t.check("  the first still reads its own neighbour above", await t.js(`${first}?.textContent`) === "5", await t.js(`${first}?.textContent`));
};

scenarios.facts = async (t) => {   // every fact typed, and its own (TYPE.md "Every fact typed", 2026-11-25)
  await t.open(`#/p/${B}`);
  await addExpr(t, `title(pericopeOf(above))`);
  t.check("a block's pericope, and its title", await t.until(`${lastOut}?.textContent === '"beta"'`, 8000), await t.js(`${lastOut}?.textContent`));
  await addExpr(t, `created(@${A})`);
  t.check("  created: a Date, drawn as fw writes dates", await t.until(`${lastOut}?.textContent === '"Oct 1, 2026, 10:00 am"'`, 4000)
    && await t.js(`${lastOut}?.title`) === "Date", await t.js(`${lastOut}?.textContent + " | " + ${lastOut}?.title`));
  await addExpr(t, `(year(created(@${A})), weekday(created(@${A})), daysBetween((created(@${A}), created(@${A}))), isPericope(@${A1}))`);
  t.check("  read with functions: year, weekday, days between; a block isn't a pericope", await t.until(`${lastOut}?.textContent === "(2026, 4, 0, false)"`, 4000),
    await t.js(`${lastOut}?.textContent`));
  await addExpr(t, `[@${A}, @${B}]`);
  t.check("a list: its things, commas between; a Ref drawn as a chip, its title (beta, the pericope it's in: this)", await t.until(`${lastOut}?.textContent === "alpha, this"`, 4000)
    && await t.js(`${lastOut}.querySelectorAll(".fw-ref").length`) === 2 && await t.js(`!!${lastOut}.querySelector(".fw-ref-this")`), await t.js(`${lastOut}?.innerHTML`));
  await t.js(`[...document.querySelectorAll(".fw-doc .fw-expr")].at(-1).fwExpr.showCode()`);
  t.check("  in its code too: @beta drawn as this, @alpha as its title", await t.until(
    `(() => { const c = [...document.querySelectorAll(".fw-expr-codebox .fw-ref")].map((x) => x.textContent); return c.join("|") === "alpha|this"; })()`, 2000),
    await t.js(`[...document.querySelectorAll(".fw-expr-codebox .fw-ref")].map((x) => x.textContent).join("|")`));
  await t.key("x", 4 | 8);
  await t.until(`!document.querySelector(".fw-expr-code")`, 2000);
  await t.settle();
  await addExpr(t, `filter(pericopes, fun p -> false)`);
  t.check("  an empty one: nothing", await t.until(`${lastOut}?.textContent === "nothing"`, 4000), await t.js(`${lastOut}?.textContent`));

  // this: the expression itself, where it sits (2026-11-25)
  await addExpr(t, `(title(pericopeOf(this)), isPericope(this))`);
  t.check("this: the pericope it's in, beta", await t.until(`${lastOut}?.textContent === '("beta", true)'`, 4000), await t.js(`${lastOut}?.textContent`));
  await t.js(`[...document.querySelectorAll(".fw-doc .fw-expr")].at(-1).fwExpr.showCode()`);
  t.check("  in the code: drawn apart (where it sits, like above and below)", await t.until(`[...document.querySelectorAll(".fw-expr-codebox .fw-relative")].some((x) => x.textContent === "this")`, 2000),
    await t.js(`document.querySelector(".fw-expr-codebox")?.innerHTML.slice(0, 600)`));
  await t.key("x", 4 | 8);
  await t.until(`!document.querySelector(".fw-expr-code")`, 2000);
  await t.settle();
  await addExpr(t, `body(this)`);
  t.check("  body(this): its pericope, and in it, its own place: the recursive case, its title and a loop, never a loop forever", await t.until(
    `!!${lastOut}?.querySelector(".fw-from .fw-loop") && ${lastOut}.querySelector(".fw-loop").textContent.endsWith("↻")`, 4000), await t.js(`${lastOut}?.textContent`));
  await addExpr(t, `[pericopeOf(this), @${A}]`);
  t.check("  a reference to the pericope it's in: this; another, a plain chip", await t.until(
    `${lastOut}?.querySelector(".fw-ref-this")?.textContent === "this" && ${lastOut}.textContent === "this, alpha"`, 4000),
    await t.js(`${lastOut}?.innerHTML`));
  await t.end();
  await t.key("Enter");
  await t.type("two - words ? + —");
  await addExpr(t, `wordCount(above)`);
  t.check("  a word is something besides punctuation (the engine's count, as the core's and the page's)", await t.until(`${lastOut}?.textContent === "2"`, 4000), await t.js(`${lastOut}?.textContent`));
  await addExpr(t, `wordCount(this)`);
  t.check("  wordCount(this): its pericope's words, all but its own (\"beta's words\": 2, and the values above it)", await t.until(`/^[0-9]+$/.test(${lastOut}?.textContent || "") && +${lastOut}.textContent >= 2`, 4000), await t.js(`${lastOut}?.textContent`));
  await addExpr(t, `let f = fun x -> f(x + 1) in f(1)`);
  t.check("a program that never ends: stopped, ∞, the page not frozen", await t.until(`${lastOut}?.textContent.startsWith("∞")`, 6000), await t.js(`${lastOut}?.textContent`));
  await addExpr(t, `text("three more words")`);
  await addExpr(t, `wordCount(pericopeOf(this))`);
  t.check("  and the page still answers; its pericope's words: what's written and what its expressions show (\"beta's words\" 2, \"three more words\" 3, the rest's values), never its own",
    await t.until(`/^[0-9]+$/.test(${lastOut}?.textContent || "") && +${lastOut}.textContent >= 5`, 4000), await t.js(`${lastOut}?.textContent`));
};

scenarios.dollar = async (t) => {   // $ in an empty block: an expression; \$ a dollar sign (TYPE.md "Inline", 2026-11-25)
  await t.open(`#/p/${B}`);
  await t.end();
  await t.key("Enter");
  await t.type("$");
  t.check("$ in an empty block: it's an expression, its code open", await t.until(`!!document.activeElement?.closest(".fw-expr-code")`, 2000),
    await t.js(`document.activeElement?.className`));
  await setCode(t, "2 + 3");
  await t.key("x", 4 | 8);
  t.check("  written and closed: its value", await t.until(`${lastOut}?.textContent === "5"`, 4000), await t.js(`${lastOut}?.textContent`));
  await t.settle();
  t.check("  in the store: an expression block", (await t.kids(B)).some((k) => k.t === "expr" && k.source === "2 + 3"), JSON.stringify(await t.kids(B)));
  await t.key("ArrowDown");   // (the empty block below it)
  for (const c of ["\\", "$", "5"]) await t.type(c);
  await t.type(" costs $3");
  await t.settle();
  const texts = (await t.kids(B)).filter((k) => k.t === "text").map((k) => k.text);
  t.check("\\$ in an empty block: a dollar sign (stored \\$, TYPE.md \"Inline\"); a $ within typing, a dollar sign too", texts.includes("\\$5 costs \\$3")
    && await t.js(`document.querySelector(".fw-doc").textContent.includes("$5 costs $3")`), JSON.stringify(texts));
  t.check("  and no second expression", (await t.kids(B)).filter((k) => k.t === "expr").length === 1, JSON.stringify(await t.kids(B)));
};

scenarios.inline = async (t) => {   // inline expressions: $…$ typed in a line, its value shown when the caret's away (TYPE.md "Inline")
  await t.open(`#/p/${B}`);
  const outs = `[...document.querySelectorAll(".fw-doc .fw-icode-out")]`;
  const b1 = async () => (await t.kids(B))[0].text;
  const blocks0 = (await t.kids(B)).length;
  await t.select("beta's words", { collapse: true });
  await t.type(" is ");
  await t.type("$");
  t.check("$ mid-text: two green dollar signs, the caret between them", await t.until(`document.querySelectorAll(".fw-doc .fw-icode-dollar").length === 2`, 2000),
    await t.js(`document.querySelector(".fw-doc")?.innerHTML.slice(0, 600)`));
  await t.type("2 + 3");
  const src = `[...document.querySelectorAll(".fw-doc .fw-icode-src")].map((x) => x.textContent).join("")`;
  t.check("  typed between them: code, mono", await t.until(`${src} === "$2 + 3$"`, 2000), await t.js(src));
  await t.type("$");   // (its closing $: out of it)
  t.check("  the closing $: out, its value in the line, green", await t.until(`${outs}.length === 1 && ${outs}[0].textContent === "5" && !document.querySelector(".fw-doc .fw-icode-src")`, 3000),
    await t.js(`${outs}.map((x) => x.textContent).join("|")`));
  await t.type(" more");
  await t.settle();
  t.check("  stored as $…$ in the text, the writing after it after it; still one block, no new line", (await b1()) === "beta's words is $2 + 3$ more" && (await t.kids(B)).length === blocks0,
    JSON.stringify(await t.kids(B)));
  await t.select("is", { collapse: true, start: true });
  await t.type("X");
  await t.settle();
  t.check("  the caret goes before it, as before any word", (await b1()) === "beta's words Xis $2 + 3$ more", await b1());
  await t.select(" more", { collapse: true, start: true });   // (just after it)
  const caretAfter = `(() => { const s = getSelection(); if (!s.rangeCount || !s.isCollapsed) return false; const c = s.getRangeAt(0).getBoundingClientRect(), v = ${outs}[0].getBoundingClientRect();
    const at = s.getRangeAt(0).startContainer, el = at.nodeType === 1 ? at : at.parentElement;
    return c.height > 0 && Math.abs(c.left - v.right) < 6 && getComputedStyle(el).caretColor !== "rgba(0, 0, 0, 0)"; })()`;
  t.check("  the caret just after it: drawn, just after its value (never lost in its folded code)", await t.until(caretAfter, 1000),
    await t.js(`JSON.stringify([getSelection().getRangeAt(0).getBoundingClientRect(), ${outs}[0].getBoundingClientRect()])`));
  await t.key("ArrowLeft");
  t.check("← onto it: selected, the caret hidden, its code not open", await t.until(`!!document.querySelector(".fw-doc .fw-icode-sel") && !document.querySelector(".fw-doc .fw-icode-src") && !getSelection().isCollapsed`, 1000));
  await t.key("ArrowLeft");
  await t.type("<");
  await t.key("ArrowRight");
  t.check("  → from before it: selected again", await t.until(`!!document.querySelector(".fw-doc .fw-icode-sel")`, 1000));
  await t.key("ArrowRight");
  t.check("  → out of it, selected: after it, the caret drawn (its own colour, not the folded code's)", await t.until(caretAfter, 1000),
    await t.js(`(() => { const s = getSelection(), a = s.getRangeAt(0).startContainer; return (a.nodeType === 1 ? a : a.parentElement).className + " " + getComputedStyle(a.nodeType === 1 ? a : a.parentElement).caretColor; })()`));
  await t.type(">");
  await t.settle();
  t.check("←/→: before it, it selected, after it; never opening it", (await b1()) === "beta's words Xis <$2 + 3$> more" && !(await t.js(`!!document.querySelector(".fw-doc .fw-icode-src")`)), await b1());
  await t.key("Backspace");
  await t.key("ArrowLeft");
  await t.key("ArrowLeft");
  await t.key("Backspace");
  await t.key("ArrowRight");
  await t.key("x", 4 | 8);   // (⌘⇧X on it selected: open)
  t.check("⌘⇧X on it: its code open", await t.until(`!!document.querySelector(".fw-doc .fw-icode-src")`, 2000), await b1());
  for (let n = 0; n < 5; n++) await t.key("Backspace");
  await t.type("10 * 10");
  await t.key("ArrowRight");
  await t.key("ArrowRight");
  t.check("  → out past its $: its value again, changed", await t.until(`${outs}[0]?.textContent === "100" && !document.querySelector(".fw-doc .fw-icode-src")`, 3000), await t.js(`${outs}.map((x) => x.textContent).join("|")`));
  await t.settle();
  t.check("  and stored", (await b1()) === "beta's words Xis $10 * 10$ more", await b1());
  const r = await t.js(`(() => { const b = ${outs}[0].getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2]; })()`);
  await t.click(r[0], r[1]);
  await sleep(200);
  t.check("a click on a value: selected, not in its code; the block still the one you're in", await t.until(`!!document.querySelector(".fw-doc .fw-icode-sel") && !document.querySelector(".fw-doc .fw-icode-src") && !!document.querySelector(".fw-doc .fw-here, .fw-doc .fw-current")`, 2000),
    await t.js(`[...document.querySelectorAll(".fw-doc .fw-text")].map((x) => x.className).join(" | ")`));
  await t.end();
  for (const c of [" costs ", "\\", "$", "7"]) await t.type(c);
  await t.settle();
  t.check("\\$: a dollar sign, stored escaped", (await b1()).endsWith(" costs \\$7") && await t.js(`${outs}.length`) === 1, await b1());
  await t.type(" ");
  await t.type("$");
  await t.type(`body(@${A})`);
  await t.type("$");
  t.check("a value of blocks can't sit in a line: !, with a note", await t.until(`${outs}[1]?.textContent === "!" && /can't sit in a line/.test(${outs}[1].title || "")`, 3000),
    await t.js(`${outs}.map((x) => x.textContent).join("|")`));
  await t.type(" ");
  await t.type("$");
  await t.type(`@${A}`);
  await t.type("$");
  t.check("a reference: its title, green, a little ↗", await t.until(`${outs}[2]?.querySelector(".fw-ref")?.textContent === "alpha"`, 3000), await t.js(`${outs}.map((x) => x.textContent).join("|")`));
  await t.settle();
  const back = (await t.get(`/api/pericope/${A}`)).backlinkRows || [];
  t.check("  and it's a backlink of what it names", back.some((x) => x.open === B), JSON.stringify(back));
  await t.key("Backspace");
  await t.settle();
  t.check("⌫ just after one: it goes whole", await t.js(`${outs}.length`) === 2 && !(await b1()).includes(`$@${A}$`), await b1());

  // @ in a line: sugar for $@p$
  await t.type(" see ");
  await t.type("@");
  t.check("@ after a space: fw's search", await t.until(`document.querySelector(".fw-menu")?.innerText.includes("@ ›")`, 2000));
  await t.type("alpha");
  await t.until(`[...document.querySelectorAll(".fw-menu .fw-row.fw-sel")].some(r => r.innerText.includes("alpha"))`, 2000);
  await t.key("Enter");
  t.check("  ending its line: no empty line under it", await t.until(`(() => { const b = ${outs}.at(-1)?.closest(".fw-text"); return !!b && !b.querySelector("br.ProseMirror-trailingBreak"); })()`, 2000),
    await t.js(`${outs}.at(-1)?.closest(".fw-text")?.innerHTML.slice(-300)`));
  t.check("  a pick: its reference in the line", await t.until(`${outs}.at(-1)?.querySelector(".fw-ref")?.textContent === "alpha"`, 3000), await t.js(`${outs}.map((x) => x.textContent).join("|")`));
  await t.type(" then");
  await t.settle();
  t.check("  stored as $@id$, the typing after it after it", (await b1()).endsWith(` see $@${A}$ then`), await b1());
  await t.type(" ");
  await t.type("@");
  await t.until(`document.querySelector(".fw-menu")?.innerText.includes("@ ›")`, 2000);
  await t.key("Escape");
  await t.type("x");
  await t.type(" ");
  await t.type("\\");
  await t.type("@");
  await t.type(" me");
  await t.type("@");
  await t.type("mail.com");
  await t.settle();
  t.check("  Esc keeps the @; \\@ an @ with no search; an @ mid-word (an address) just an @", (await b1()).endsWith(" then @x @ me@mail.com") && !(await t.js(`!!document.querySelector(".fw-menu")`)), await b1());
};

scenarios.exprleave = async (t) => {   // ↓ out of an expression: nothing of it lit any more, its ƒ tab included (2026-11-25)
  await t.open(`#/p/${B}`);
  await addExpr(t, `1 + 1`);
  await t.key("ArrowDown");
  await t.settle();
  const lit = `[...document.querySelector(".fw-doc .fw-expr").classList].filter((c) => c !== "fw-expr").join(" ")`;
  t.check("↓ out of an expression: it isn't lit (its ƒ tab with it)", await t.until(`!document.querySelector(".fw-doc .fw-expr:is(.fw-here, .fw-chosen, .ProseMirror-selectednode, .fw-expr-coding, :has(.fw-current))")`, 2000),
    await t.js(lit));
  const r = await t.js(`(() => { const b = document.querySelector(".fw-doc .fw-expr").getBoundingClientRect(); return [b.left + 40, b.top + b.height / 2]; })()`);
  await t.click(r[0], r[1]);
  await t.until(`!!document.querySelector(".fw-doc .fw-expr.ProseMirror-selectednode")`, 2000);
  await t.key("ArrowDown");
  await t.settle();
  t.check("  clicked on, then ↓: not lit either", await t.until(`!document.querySelector(".fw-doc .fw-expr:is(.fw-here, .fw-chosen, .ProseMirror-selectednode, .fw-expr-coding, :has(.fw-current))")`, 2000),
    await t.js(lit) + " | active: " + await t.js(`document.activeElement?.className`));
  await t.key("ArrowUp");
  await t.key("ArrowUp");
  await t.key("ArrowDown");
  await t.key("ArrowDown");
  await t.settle();
  t.check("  up through it and down again: not lit", await t.until(`!document.querySelector(".fw-doc .fw-expr:is(.fw-here, .fw-chosen, .ProseMirror-selectednode, .fw-expr-coding, :has(.fw-current))")`, 2000),
    await t.js(lit));
  for (let n = 0; n < 4; n++) {   // (its code changed, Esc, ↓ at once: while its save and the store's follow are still coming)
    await t.js(`document.querySelector(".fw-doc .fw-expr").fwExpr.showCode()`);
    await t.until(`!!document.activeElement?.closest(".fw-expr-code")`, 2000);
    await setCode(t, `1 + ${n + 2}`);
    await t.key("Escape");
    await t.key("ArrowDown");
    await t.settle();
    await sleep(300);
    const on = await t.js(`!!document.querySelector(".fw-doc .fw-expr:is(.fw-here, .fw-chosen, .ProseMirror-selectednode, .fw-expr-coding, :has(.fw-current))")`);
    if (on) { t.check("  its code written, Esc, ↓ at once: not lit", false, await t.js(lit) + ` (try ${n}) sel ` + await t.js(`JSON.stringify(window.fw.editor().view.state.selection.toJSON()) + " expr at " + (() => { let at = null; window.fw.editor().view.state.doc.forEach((n, pos) => { if (n.type.name === "expr") at = pos; }); return at; })() + " views " + document.querySelectorAll(".fw-doc .fw-expr").length + " focus " + document.activeElement?.className`)); return; }
  }
  t.check("  its code written, Esc, ↓ at once: not lit", true);
  const inside = `(() => { const e = document.querySelector(".fw-doc .fw-expr").getBoundingClientRect();
    return [...document.querySelectorAll(".fw-link-line")].filter((l) => { const r = l.getBoundingClientRect(); return r.bottom > e.top + 1 && r.top < e.bottom - 1; }).length; })()`;
  await t.js(`document.querySelector(".fw-doc .fw-expr").fwExpr.showCode()`);
  await t.until(`!!document.activeElement?.closest(".fw-expr-code")`, 2000);
  await sleep(150);
  t.check("  its code open: the lines to the blocks around it outside its box, not where it used to end", await t.until(`${inside} === 0`, 2000), await t.js(String(inside)));
  await setCode(t, `Blocks([text("one"), text("two"), text("three"), text("four")])`);
  await sleep(400);   // (its value drawn a moment later, taller: nothing else changed)
  t.check("  its value grown taller while open: the lines still outside it", await t.until(`${inside} === 0`, 1000), await t.js(String(inside)));
  await t.key("Escape");
  await sleep(150);
  t.check("  closed again: still outside it", await t.until(`${inside} === 0`, 2000), await t.js(String(inside)));
  const lit2 = `document.querySelectorAll(".fw-doc .fw-expr:is(.fw-chosen, .ProseMirror-selectednode, .fw-expr-coding)").length`;
  await t.js(`document.querySelector(".fw-doc .fw-expr").fwExpr.showCode()`);
  await t.until(`!!document.activeElement?.closest(".fw-expr-code")`, 2000);
  await setCode(t, "1 + 1");
  await t.js(`(() => { const v = document.querySelector(".fw-expr-codebox").fwCode; v.dispatch({ selection: { anchor: v.state.doc.length } }); return 1; })()`);
  await t.key("ArrowDown");
  t.check("↓ on its code's last line: closed, out to the block below, nothing of it lit", await t.until(`!document.querySelector(".fw-expr-codebox") && ${lit2} === 0 && !!document.activeElement?.closest(".fw-doc .ProseMirror")`, 2000),
    await t.js(`${lit2} + " " + document.activeElement?.className`));
  await t.js(`document.querySelector(".fw-doc .fw-expr").fwExpr.showCode()`);
  await t.until(`!!document.activeElement?.closest(".fw-expr-code")`, 2000);
  await t.select("beta's words", { collapse: true });   // (a click elsewhere, as good as)
  t.check("  open, then somewhere else in the page: closed, nothing of it left lit", await t.until(`!document.querySelector(".fw-expr-codebox") && ${lit2} === 0`, 2000), await t.js(String(lit2)));
  const fn = `getComputedStyle(document.querySelector(".fw-doc .fw-expr > .fw-fn"))`;
  await t.js(`document.querySelector(".fw-doc .fw-expr").fwExpr.showCode()`);
  await t.until(`!!document.activeElement?.closest(".fw-expr-code")`, 2000);
  await t.key("Escape");
  await t.until(`!!document.querySelector(".fw-doc .fw-expr.fw-chosen")`, 2000);
  t.check("  selected whole: its tab filled", await t.until(`${fn}.opacity === "1" && ${fn}.backgroundColor !== "rgba(0, 0, 0, 0)"`, 2000), await t.js(`${fn}.opacity + " " + ${fn}.backgroundColor`));
  // (the editor left for something else on the page, its selection kept: ↓ past the last block into what's below, say)
  await t.js(`(() => { const b = document.createElement("button"); b.id = "elsewhere"; document.body.append(b); b.focus(); })()`);
  await sleep(250);   // (its fade)
  t.check("  the editor left, the selection kept: its tab not lit (as its box)", await t.until(`${fn}.opacity !== "1" && ${fn}.backgroundColor === "rgba(0, 0, 0, 0)"`, 2000),
    await t.js(`${fn}.opacity + " " + ${fn}.backgroundColor + " | " + [...document.querySelector(".fw-doc .fw-expr").classList].join(" ")`));
};

scenarios.perspective = async (t) => {   // this, here, self: here is where it's viewed from (the user, 2026-11-25)
  await t.open(`#/p/${A}`);
  await addExpr(t, `(title(here), title(this), isPericope(self))`);
  t.check("in its own pericope: here is this", await t.until(`${lastOut}?.textContent === '("alpha", "alpha", false)'`, 8000), await t.js(`${lastOut}?.textContent`));
  await addExpr(t, `(here, this, self)`);
  t.check("  drawn as the words: this (here is this), self", await t.until(`${lastOut}?.textContent === "(this, this, self)"`, 4000), await t.js(`${lastOut}?.textContent`));
  await t.settle();
  await t.open(`#/p/${N}`);   // (nested quotes alpha: the same expressions, seen from nested)
  const seen = `[...document.querySelectorAll(".fw-doc .fw-quote .fw-expr-out")].map((x) => x.textContent)`;
  t.check("seen through a quote from another pericope: here is that one, this still its own", await t.until(`${seen}.includes('("nested", "alpha", false)')`, 8000), await t.js(`JSON.stringify(${seen})`));
  t.check("  drawn as the words: here, this, self", await t.until(`${seen}.includes("(here, this, self)")`, 4000), await t.js(`JSON.stringify(${seen})`));
};

scenarios.exprcall = async (t) => {   // a quote of an expression is a call: evaluated where the quote sits, one red box (2026-11-24)
  await t.open(`#/p/${A}`);
  await t.end();
  await t.type("a pigeon walks by");
  const SHOUT = "let shout = fun b ->\n  case content(body(b))\n  | Text([Plain(s)]) => text(string_uppercase(s))\n  | _ => text(\"?\")\n  end\nin\nshout(above)";
  await addExpr(t, SHOUT);
  await t.until(`[...document.querySelectorAll(".fw-doc .fw-expr .fw-text")].some((x) => x.textContent === "A PIGEON WALKS BY")`, 8000);
  await t.key("e", 4);   // (⌘E: a pericope of its own, quoted here)
  const q = `[...document.querySelectorAll(".fw-doc > .ProseMirror > .fw-quote")].at(-1)`;
  t.check("⌘E on it: the quote left here shows the result, worked out here (above: the pigeon)", await t.until(
    `${q}?.querySelector(".fw-text")?.textContent === "A PIGEON WALKS BY"`, 6000), await t.js(`${q}?.outerHTML`));
  t.check("  one red box: no expression box, no green inside it", await t.js(`!${q}.querySelector(".fw-expr, .fw-from") && !${q}.classList.contains("fw-from")`),
    await t.js(`${q}?.outerHTML`));
  await t.select("a pigeon walks by", { collapse: true });
  await t.key("End");
  await t.key("ArrowDown");
  t.check("  ↓ onto it: the quote selected whole (one block: nothing inside to be half in)", await t.until(
    `${q}?.classList.contains("fw-chosen") && !${q}.querySelector(".fw-chosen, .fw-here")`, 2000),
    await t.js(`${q}?.className + " | " + [...${q}.querySelectorAll(".fw-chosen, .fw-here")].map((x) => x.className).join()`));
  t.check("  its one tab filled red; the block above glows", await t.until(`(() => { const ts = [...document.querySelectorAll(".fw-tab")];
    const above = ${q}.previousElementSibling;
    return ts.length === 1 && ts[0].matches(".fw-tab-filled.fw-tab-quote") && getComputedStyle(above).getPropertyValue("--lit-down") !== "rgba(0, 0, 0, 0)"; })()`, 2000),
    await t.js(`[...document.querySelectorAll(".fw-tab")].map((x) => x.className).join(" | ")`));
  await t.select("a pigeon walks by", { collapse: true });
  const at = await t.js(`(() => { const b = ${q}.querySelector(".fw-text").getBoundingClientRect(); return [b.left + 30, b.top + b.height / 2]; })()`);
  await t.click(at[0], at[1]);
  t.check("  a click in its text: the quote selected whole too", await t.until(`${q}?.classList.contains("fw-chosen") && !${q}.querySelector(".fw-chosen, .fw-here")`, 2000),
    await t.js(`${q}?.className + " | " + [...${q}.querySelectorAll(".fw-chosen, .fw-here")].map((x) => x.className).join()`));
  await t.shot("exprcall.png", { x: 0, y: 0, width: 1100, height: 480 });
  await t.select("a pigeon walks by", { collapse: true });
  await t.type(" slowly");
  t.check("  live: the block above it changed, the call follows", await t.until(`${q}?.querySelector(".fw-text")?.textContent === "A PIGEON WALKS BY SLOWLY"`, 3000),
    await t.js(`${q}?.querySelector(".fw-text")?.textContent`));
  await t.settle();
  const quoted = (await t.kids(A)).find((k) => k.t === "quote" && k.target !== B);
  await t.open(`#/p/${quoted.target}`);
  t.check("its own pericope: nothing above it there, so a ?", await t.until(`[...document.querySelectorAll(".fw-doc .fw-expr .fw-text")].some((x) => x.textContent === "?")`, 6000));
};

scenarios.unwrap = async (t) => {   // a value of one block is unwrapped: its holder's box, never gone into (2026-11-24)
  await t.open(`#/p/${A}`);
  await t.end();
  await t.type("a pigeon walks by");
  await addExpr(t, `text("hello")`);
  const ex = `[...document.querySelectorAll(".fw-doc > .ProseMirror > .fw-expr")].at(-1)`;
  await t.until(`${ex}?.querySelector(".fw-value > .fw-text")?.textContent === "hello"`, 8000);
  await t.select("a pigeon walks by", { collapse: true });
  await t.key("End");
  await t.key("ArrowDown");
  const whole = `${ex}?.classList.contains("ProseMirror-selectednode") && !${ex}.querySelector(".fw-value .fw-chosen, .fw-value .fw-here")`;
  t.check("↓ onto an expression of one block: it, selected whole (nothing inside to be in)", await t.until(whole, 2000),
    await t.js(`${ex}?.className + " | " + [...${ex}.querySelectorAll(".fw-chosen, .fw-here")].map((x) => x.className).join()`));
  t.check("  one tab, filled, green", await t.until(`(() => { const ts = [...document.querySelectorAll(".fw-tab")]; return ts.length === 1 && ts[0].matches(".fw-tab-filled.fw-tab-expr"); })()`, 2000),
    await t.js(`[...document.querySelectorAll(".fw-tab")].map((x) => x.className + ":" + x.textContent).join(" | ")`));
  t.check("  its one block has no box of its own", await t.js(`getComputedStyle(${ex}.querySelector(".fw-value > .fw-text")).borderImageSource === "none"`));
  t.check("  its ƒ tab, filled", await t.until(`getComputedStyle(${ex}.querySelector(".fw-fn")).opacity === "1"`, 2000));
  await t.select("a pigeon walks by", { collapse: true });
  const hit = await t.js(`(() => { const b = ${ex}.querySelector(".fw-value > .fw-text").getBoundingClientRect(); return [b.left + 20, b.top + b.height / 2]; })()`);
  await t.click(hit[0], hit[1]);
  t.check("  a click in its text: it, selected whole", await t.until(whole, 2000), await t.js(`${ex}?.className`));
  await t.key("Enter");
  t.check("  Enter: nothing to go into (still it, selected whole)", await t.until(whole, 1000) || !(await t.js(`!!${ex}.querySelector(".fw-value .fw-chosen")`)));
  await addExpr(t, `body(@${T})`);
  const ex2 = `[...document.querySelectorAll(".fw-doc > .ProseMirror > .fw-expr")].at(-1)`;
  await t.until(`${ex2}?.querySelectorAll(".fw-from .fw-text").length === 2`, 8000);
  await t.key("Enter");
  const chosen = `(() => { const c = [...(${ex2}?.querySelectorAll(".fw-chosen") || [])].at(-1); return c ? c.textContent : null; })()`;
  t.check("an expression of one window (body(@fox)): Enter goes straight to its blocks", await t.until(`${chosen} === "the quick brown fox"`, 2000), String(await t.js(chosen)));
  await t.key("ArrowLeft");
  t.check("  ←: straight back out, the expression selected whole (no unseen level between)", await t.until(
    `${ex2}?.classList.contains("ProseMirror-selectednode") && ${chosen} === null`, 2000), String(await t.js(chosen)));
};

scenarios.exprblocks = async (t) => {   // fw's type is Hazel's: a value of type Block drawn as fw's blocks, the store read through Refs
  await t.open(`#/p/${A}`);
  await addExpr(t, `body(@${B})`);
  const valueDoc = `${lastOut}?.querySelector(":scope > .fw-body > .ProseMirror")`;
  t.check("body(@beta): a From, beta's blocks drawn as a quote of beta, green (TYPE.md: a quote is body(@x))", await t.until(
    `${valueDoc}?.querySelector(":scope > .fw-quote.fw-from .fw-text")?.textContent === "beta's words"`, 8000), await t.js(`${lastOut}?.outerHTML`));
  t.check("  its top line, ↗ and tab green", await t.js(`(() => { const q = ${valueDoc}.querySelector(":scope > .fw-quote.fw-from");
    return getComputedStyle(q.querySelector(".fw-top")).color === "rgb(111, 158, 130)"; })()`));
  await addExpr(t, `Quote(@${T})`);
  t.check("Quote(@fox): no such constructor (body is how a quote is written)", await t.until(
    `${lastOut}?.title.includes("Constructor is not defined")`, 4000), await t.js(`${lastOut}?.outerHTML`));
  await addExpr(t, `From(@${T}, text("forged"))`);
  t.check("From(…) by hand: sealed, refused (no forged quote)", await t.until(
    `${lastOut}?.title.includes("Constructor is not defined") && !${lastOut}.querySelector(".fw-quote")`, 4000), await t.js(`${lastOut}?.outerHTML`));
  await addExpr(t, `Text([Plain("see "), Link("the fox", @${T})])`);
  t.check("a text with a link: the link drawn, pointing at fox", await t.until(
    `${valueDoc}?.querySelector(".fw-link")?.textContent === "the fox"`, 4000), await t.js(`${lastOut}?.outerHTML`));
  await addExpr(t, `Blocks([text(title(@${T})), Paraphrase(@${T}, "a fox jumps"), ?])`);
  t.check("Blocks of a text, a paraphrase and a hole: each drawn, the hole a ?", await t.until(
    `(() => { const c = ${valueDoc}; return c && c.children[0].textContent === "fox" && c.children[1].matches(".fw-para") && c.children[2].textContent === "?"; })()`, 4000),
    await t.js(`${lastOut}?.outerHTML`));
  await addExpr(t, `fun (r : Ref) -> body(r)`);
  t.check("a function alone: its type, dim", await t.until(`${lastOut}?.matches(".fw-expr-fn") && ${lastOut}.textContent === "Ref -> Block"`, 4000),
    await t.js(`${lastOut}?.outerHTML`));
  await addExpr(t, `length(pericopes)`);
  t.check("any other value: printed (pericopes: every pericope)", await t.until(`${lastOut}?.textContent === "8"`, 4000), await t.js(`${lastOut}?.outerHTML`));
  await addExpr(t, `wordCount(@${T})`);
  t.check("a pericope's facts: wordCount", await t.until(`${lastOut}?.textContent === "8"`, 4000), await t.js(`${lastOut}?.outerHTML`));
  await addExpr(t, `created(@${B})`);
  t.check("  created (a Date, drawn as fw writes dates)", await t.until(`${lastOut}?.textContent === '"Oct 1, 2026, 10:00 am"'`, 4000), await t.js(`${lastOut}?.textContent`));
  await addExpr(t, `length(backlinks(@${B}))`);
  t.check("  backlinks (alpha and two quotes quote beta)", await t.until(`${lastOut}?.textContent === "2"`, 4000), await t.js(`${lastOut}?.textContent`));
  await addExpr(t, `visits(@${B})`);
  t.check("  visits (an Int)", await t.until(`/^[0-9]+$/.test(${lastOut}?.textContent || "")`, 4000), await t.js(`${lastOut}?.textContent`));
  await addExpr(t, `body(@${A1})`);
  const lastText = `${lastOut}?.querySelector(".fw-text")?.textContent`;
  t.check("body of a block of the open pericope", await t.until(`${lastText} === "first words"`, 4000), await t.js(`${lastOut}?.outerHTML`));
  await t.select("first words", { collapse: true });
  await t.type(" and more");
  t.check("  live: it follows each key in that block (the snapshot built on the page)", await t.until(`${lastText} === "first words and more"`, 2000),
    await t.js(`${lastOut}?.outerHTML`));
  await t.settle();
  const kinds = (await t.kids(A)).filter((k) => k.t === "expr").map((k) => k.source);
  await t.shot("exprblocks.png");
  t.check("  saved as their sources, @ids and all", kinds.length === 12 && kinds[0] === `body(@${B})`, JSON.stringify(kinds));
  await addExpr(t, `1 + "a"`);
  await t.key("x", 4 | 8);
  t.check("Hazel's own errors, under the code", await t.until(`document.querySelector(".fw-expr-errors")?.textContent.includes("Expecting type Int but got inconsistent type String")`, 4000),
    await t.js(`document.querySelector(".fw-expr-coding")?.outerHTML`));
};

scenarios.twowindows = async (t) => {   // two windows on one store: a source in one, a pericope quoting it in the other
  const other = await tab();
  const ojs = async (e) => (await other.cdp("Runtime.evaluate", { expression: e, returnByValue: true, awaitPromise: true })).result?.result?.value;
  await other.cdp("Page.navigate", { url: `http://127.0.0.1:${t.port}/?test#/p/${B}` });
  for (let n = 0; n < 200 && !(await ojs(`window.fw?.editor()?.id === "${B}"`)); n++) await sleep(25);
  await t.open(`#/p/${R}`);
  const quoted = `[...document.querySelectorAll(".fw-quote")].map((q) => q.textContent).join(" | ")`;
  await ojs(`window.fw.select("beta's words", { collapse: true })`);
  const t0 = Date.now();
  await other.cdp("Input.insertText", { text: " LIVE" });
  const seen = await t.until(`(${quoted}).includes("LIVE")`, 5000);
  t.check(`typed in the source: the quote in the other window follows (${Date.now() - t0} ms)`, seen, await t.js(quoted));
  await t.settle();
  await t.select("beta's words LIVE", { collapse: true });
  const t1 = Date.now();
  await t.type(" BACK");
  const back = await (async () => { for (const end = Date.now() + 5000; Date.now() < end; await sleep(25)) if ((await ojs(`document.querySelector(".fw-doc").textContent`))?.includes("LIVE BACK")) return true; return false; })();
  t.check(`typed through the quote: the source's window follows (${Date.now() - t1} ms)`, back, await ojs(`document.querySelector(".fw-doc").textContent`));
  // (then back in the source's window: the quote, written through a moment ago, its caret still in it, follows too)
  await ojs(`window.fw.select("LIVE BACK", { collapse: true })`);
  const t2 = Date.now();
  await other.cdp("Input.insertText", { text: " AGAIN" });
  const again = await t.until(`(${quoted}).includes("BACK AGAIN")`, 5000);
  t.check(`after writing through it: the source edited elsewhere, the quote follows (${Date.now() - t2} ms)`, again, await t.js(quoted));
  other.close();
};

/** Another window on the same core (the user's two windows): its own tab, at `hash`. */
async function window2(t, hash) {
  const w = await tab();
  const js = async (e) => (await w.cdp("Runtime.evaluate", { expression: e, returnByValue: true, awaitPromise: true })).result?.result?.value;
  const until = async (e, ms = 4000) => { for (const end = Date.now() + ms; Date.now() < end; await sleep(25)) if (await js(e)) return true; return false; };
  const id = hash.match(/^#\/p\/([^@]+)/)[1];
  await w.cdp("Page.navigate", { url: `http://127.0.0.1:${t.port}/?test${hash}` });
  await until(`window.fw?.editor()?.id === "${id}"`, 6000);
  await until(`window.fw?.settled()`);
  return { js, until, close: w.close, type: (text) => w.cdp("Input.insertText", { text }),
    select: (text, o = {}) => js(`window.fw.select(${JSON.stringify(text)}, ${JSON.stringify(o)})`),
    async key(k, mods = 0) {
      const p = { key: k, code: `Key${k.toUpperCase()}`, windowsVirtualKeyCode: k.toUpperCase().charCodeAt(0), modifiers: mods };
      await w.cdp("Input.dispatchKeyEvent", { type: "rawKeyDown", ...p }); await w.cdp("Input.dispatchKeyEvent", { type: "keyUp", ...p });
    } };
}

// Live: every view of a block follows it, wherever it was written (the user, 2026-11-25: "this a is a very fundamental
// idea… not just in this case but in every case… its about live enviroments and dependencies"). Each case: the source
// written in one window, what depends on it seen in another.
const LX = "20261009T100000-c100", LXQ = "20261009T100000-c101", LXE = "20261009T100000-c102";
scenarios.live = async (t) => {
  const text = (sel) => `[...document.querySelectorAll(${JSON.stringify(sel)})].map((q) => q.textContent).join(" | ")`;
  const src = await window2(t, `#/p/${B}`);   // beta, the source, in a window of its own
  const step = async (label, write, seen, detail) => {
    const t0 = Date.now();
    await write();
    const ok = await t.until(seen, 5000);
    t.check(`${label} (${Date.now() - t0} ms)`, ok, await t.js(detail));
  };

  // a quote inside a quote: nested (N quotes alpha, which quotes beta)
  await t.open(`#/p/${N}`);
  await src.select("beta's words", { collapse: true });
  await step("a quote of a quote: the source written, the nested quote follows", () => src.type(" one"),
    `(${text(".fw-quote")}).includes("words one")`, text(".fw-quote"));

  // a masked quote: what shows grows with what's written inside it
  await t.open(`#/p/${LX}`);
  await src.select("beta", { collapse: true });
  await step("a masked quote: written inside what shows, it follows", () => src.type("X"),
    `(${text(".fw-quote")}).includes("betaX's")`, text(".fw-quote"));
  // an expression reading it
  const was = await t.js(text(".fw-expr"));
  await src.select("words one", { collapse: true });
  await step("an expression reading it: its value follows", () => src.type(" two three"),
    `(${text(".fw-expr")}) !== ${JSON.stringify(was)}`, text(".fw-expr"));

  // the caret in the quote, carried: written elsewhere before it, then typing here goes where it was
  await t.open(`#/p/${R}`);
  await t.select("two three", { collapse: true });
  await src.select("betaX's", { collapse: true, start: true });
  await step("the caret in a quote, the source written before it elsewhere: followed", () => src.type("AT START "),
    `(${text(".fw-quote")}).includes("AT START")`, text(".fw-quote"));
  await t.type("!");
  await t.settle();
  const b1 = async () => (await t.kids(B))[0].text;
  t.check("  typing here after it: where the caret was (carried, not reset)", (await b1()) === "AT START betaX's words one two three!", await b1());

  // undo here takes back only what was written here, never what came from elsewhere
  await t.select("r words", { collapse: true });
  await t.type(" mine");
  await t.settle();
  await src.until(`document.querySelector(".fw-doc").textContent.includes("three!")`);   // (the source's window has it: then its caret goes there)
  await src.select("three!", { collapse: true });
  await step("  written here, then the source elsewhere: followed", () => src.type(" theirs"),
    `(${text(".fw-quote")}).includes("theirs")`, text(".fw-quote"));
  await t.select("r words mine", { collapse: true });
  await t.key("z", 4);
  await t.settle();
  const r1 = (await t.kids(R))[0].text;
  t.check("  ⌘Z here: only what was written here taken back", r1 === "r words" && (await b1()).endsWith("theirs"), JSON.stringify([r1, await b1()]));

  // the same pericope in both windows: each follows the other, the caret carried
  await t.open(`#/p/${B}`);
  await t.select("AT START", { collapse: true });
  await src.until(`document.querySelector(".fw-doc").textContent.includes("theirs")`);
  await src.select("AT", { collapse: true, start: true });
  await step("the same pericope in two windows: written in one, the other follows", () => src.type(">> "),
    `document.querySelector(".fw-doc").textContent.includes(">> AT START")`, `document.querySelector(".fw-doc").textContent`);
  await t.type("|");
  await t.settle();
  t.check("  and its caret carried", (await b1()).startsWith(">> AT START|"), await b1());

  // both at once, the same block: neither refused, neither lost, and both windows end up saying the same
  await t.select("AT START|", { collapse: true });
  await src.until(`document.querySelector(".fw-doc").textContent.includes("AT START|")`);
  await src.select("three!", { collapse: true });
  await Promise.all([t.type(" HERE"), src.type(" THERE")]);
  const both = `(() => { const x = document.querySelector(".fw-doc").textContent; return x.includes(" HERE") && x.includes(" THERE"); })()`;
  const merged = await t.until(both, 5000) && await src.until(both, 5000);
  await t.settle();
  t.check("both windows writing the same block at once: merged, both kept, in both windows", merged && (await b1()).includes(" HERE") && (await b1()).includes(" THERE"),
    JSON.stringify([await b1(), await t.js(`document.querySelector(".fw-doc").textContent`), await src.js(`document.querySelector(".fw-doc").textContent`)]));
  t.check("  and neither window is stuck (nothing unsaved, nothing refused)", await t.until(`!window.fw.editor().dirty()`) && await src.until(`!window.fw.editor().dirty() && !/not saved/.test(window.fw.editor().message)`),
    await src.js(`window.fw.editor().message`));
  src.close();
};
scenarios.live.setup = (dir, data) => {   // a pericope with a masked quote of beta (just "beta's") and an expression reading beta
  const like = (id, content, extra = {}) => ({ ...data.blocks.find((b) => b.id === B1), id, content, title: null, ...extra });
  data.blocks.push(like(LX, [LXQ, LXE], { entry: true, title: "watcher" }),
    like(LXQ, { quote: B, mask: { [B1]: [[0, 6]] } }), like(LXE, { expr: `wordCount(@${B})` }));
  writeFileSync(join(dir, "freewrites.json"), JSON.stringify(data));
};

// An expression's code is written like anything else (Hazel: every editor state means something): what shows it
// follows each change elsewhere, unfinished states included, in its own pericope and through a quote of it (a call).
const EP = "20261009T100000-c200", EE = "20261009T100000-c201", EC = "20261009T100000-c202", ECQ = "20261009T100000-c203";
scenarios.liveexpr = async (t) => {
  const out = `document.querySelector(".fw-doc .fw-expr-out, .fw-doc .fw-quote .fw-body")?.textContent`;
  const src = await window2(t, `#/p/${EP}`);
  await src.js(`document.querySelector(".fw-expr").fwExpr.showCode()`);
  await src.until(`!!document.querySelector(".fw-expr-codebox")`);
  const write = (code) => src.js(`(() => { const v = document.querySelector(".fw-expr-codebox").fwCode;
    v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: ${JSON.stringify(code)} } }); return 1; })()`);
  const step = async (label, code, seen) => {
    await write(code);
    const t0 = Date.now(), ok = await t.until(`${out} === ${JSON.stringify(seen)}`, 5000);
    t.check(`${label} (${Date.now() - t0} ms)`, ok, await t.js(out));
  };
  await t.open(`#/p/${EP}`);
  t.check("its own pericope, both windows: the value", await t.until(`${out} === "4"`, 5000), await t.js(out));
  await step("  its code written in the other window: followed", "2 + 2 + 1", "5");
  await step("  unfinished there: a hole here, the rest worked out", "2 + 2 +", "4 + ?");
  await t.open(`#/p/${EC}`);
  t.check("a quote of it (a call): its value", await t.until(`${out} === "4 + ?"`, 5000), await t.js(out));
  await step("  its code written in the other window: the call follows", "10 * 10", "100");
  await step("  this, in a call: the quote, where it sits (its pericope: caller)", "title(pericopeOf(this))", '"caller"');
  await write("10 * 10");
  await t.until(`${out} === "100"`, 5000);

  // ⌘⇧X on the quote: its expression's code, written through to it (and the other window follows)
  await t.js(`document.querySelector(".fw-quote").fwCall.showCode()`);
  await t.key("x", 4 | 8);   // (closed: the quote left selected)
  t.check("⌘⇧X on a quote of an expression: closes its code, the quote selected", await t.until(`!document.querySelector(".fw-expr-codebox") && !!document.querySelector(".fw-quote.ProseMirror-selectednode")`, 2000));
  await t.key("x", 4 | 8);
  t.check("  and opens it again", await t.until(`!!document.activeElement?.closest(".fw-quote .fw-expr-codebox")`, 2000));
  await t.type(" + 1");
  t.check("  written in it here: the call's result follows the key", await t.until(`${out}.endsWith("101")`, 2000), await t.js(out));
  t.check("  written through: the expression in its own pericope, other window", await src.until(`document.querySelector(".fw-expr-codebox").fwCode.state.doc.toString() === "10 * 10 + 1"`, 5000)
    && await src.until(`document.querySelector(".fw-expr-out")?.textContent === "101"`, 5000), await src.js(`document.querySelector(".fw-expr-out")?.textContent`));
  await t.settle();
  t.check("  in the store", (await t.kids(EP))[0]?.source === "10 * 10 + 1", JSON.stringify(await t.kids(EP)));
  await t.key("x", 4 | 8);
  t.check("  ⌘⇧X: closed, the quote selected, the result still there", await t.until(`!document.querySelector(".fw-expr-codebox") && !!document.querySelector(".fw-quote.ProseMirror-selectednode") && ${out}.endsWith("101")`, 2000), await t.js(out));
  src.close();
};
scenarios.liveexpr.setup = (dir, data) => {
  const like = (id, content, extra = {}) => ({ ...data.blocks.find((b) => b.id === B1), id, content, title: null, ...extra });
  data.blocks.push(like(EP, [EE], { entry: true, title: "sum" }), like(EE, { expr: "2 + 2" }),
    like(EC, [ECQ], { entry: true, title: "caller" }), like(ECQ, { quote: EP }));
  writeFileSync(join(dir, "freewrites.json"), JSON.stringify(data));
};

scenarios.livetype = async (t) => {   // the header's type follows what's written, on the key (2026-11-23)
  await t.open(`#/p/${B}`);
  const type = `document.querySelector(".fw-label").textContent`;
  t.check("one block of text: text", await t.until(`${type} === "text"`, 2000), await t.js(type));
  await t.end();
  await t.key("Enter");
  t.check("  Enter, a second block: pericope, at once", await t.until(`${type} === "pericope"`, 500), await t.js(type));
  await t.key("Backspace");
  t.check("  ⌫, one again: text", await t.until(`${type} === "text"`, 500), await t.js(type));
};

scenarios.onebox = async (t) => {   // a quote showing one block draws one box: the block's own (its border-image too) never shows
  await t.open(`#/p/${A}`);
  const inner = `getComputedStyle(document.querySelector(".fw-quote > .fw-body .fw-text")).borderImageSource`;
  t.check("a quote of a pericope of one block, at rest: no box inside", await t.js(`${inner} === "none"`), await t.js(inner));
  await t.select("beta's words"); await t.settle();
  t.check("  in it: still none (the glow's gradient off too)", await t.js(`${inner} === "none" && document.querySelector(".fw-quote > .fw-body .fw-text.fw-here") !== null`), await t.js(inner));
  await t.key("Escape"); await t.settle();
  t.check("  selected whole: none", await t.js(`${inner} === "none" && !!document.querySelector(".fw-quote.fw-chosen")`), await t.js(inner));
};

scenarios.backlinks = async (t) => {   // the backlinks above the header (2026-11-23): a sliver at the window's top, ↑ into them
  await t.open(`#/p/${B}`);
  const rect = (sel) => `(() => { const r = document.querySelector("${sel}")?.getBoundingClientRect(); return r && [Math.round(r.top), Math.round(r.bottom)]; })()`;
  t.check("beta: its backlinks above its header, the newest nearest (alpha quotes it, then two quotes)",
    await t.until(`[...document.querySelectorAll(".fw-back")].map((r) => r.dataset.pericope).join() === "${A},${R}"`, 3000),
    await t.js(`[...document.querySelectorAll(".fw-back")].map((r) => r.innerText).join(" | ")`));
  const [top, bottom] = await t.js(rect(".fw-back:last-child"));
  t.check("  a sliver of the nearest at the window's top, cut off; the page can't scroll up to them", top < 0 && bottom > 0 && bottom < 20
    && await t.js(`scrollY === 0`), JSON.stringify([top, bottom]));
  await t.shot("backs-rest.png", { x: 0, y: 0, width: 1000, height: 260 });
  const head = await t.js(rect(".fw-header"));
  for (let i = 0; i < 3; i++) await t.key("ArrowUp");   // (the writing → the title → the kinds line → the backlinks line)
  t.check("  ↑ up the header: its backlinks line", await t.until(`document.activeElement?.matches(".fw-chip-backs")`, 2000));
  await t.key("ArrowUp");
  t.check("  ↑ again: into them, the nearest selected; short, the whole list shown, room above it (scrolling.js PAD)",
    await t.until(`document.querySelector(".fw-backs-open .fw-sel")?.dataset.pericope === "${R}"
      && Math.abs(document.querySelector(".fw-back").getBoundingClientRect().top - 56) < 2`, 2000), JSON.stringify([head, await t.js(rect(".fw-header"))]));
  await t.key("ArrowUp"); await t.shot("backs-open.png", { x: 0, y: 0, width: 1000, height: 260 }); await t.key("ArrowDown");
  await t.key("ArrowDown");
  t.check("  ↓ past the nearest: back on the backlinks line, hung up again, the header where it was",
    await t.until(`document.activeElement?.matches(".fw-chip-backs") && !document.querySelector(".fw-backs-open")`, 2000)
    && (await t.js(rect(".fw-header")))[0] === head[0], JSON.stringify(await t.js(rect(".fw-header"))));
  t.check("  the go-to list turned over: a rule, then 'links to this', then the header", await t.js(`document.querySelector(".fw-go-up")?.innerText === "links to this"
    && document.querySelector(".fw-go-up").getBoundingClientRect().bottom <= document.querySelector(".fw-header").getBoundingClientRect().top`));
  const wheel = (deltaY) => t.cdp("Input.dispatchMouseEvent", { type: "mouseWheel", x: 500, y: 300, deltaX: 0, deltaY });
  await t.js(`document.activeElement?.blur(); 1`);
  await wheel(-200); await wheel(-400);   // (in, then on up to them: they have room above them, scrolling.js)
  t.check("  scrolling up at the page's top: they come in, scrolled to", await t.until(`!!document.querySelector(".fw-backs-open") && document.querySelector(".fw-back").getBoundingClientRect().top >= 0`, 2000),
    JSON.stringify(await t.js(rect(".fw-back"))));
  for (let i = 0; i < 4; i++) await wheel(200);
  t.check("  scrolled back down past them: hung off the top again, the header where it was", await t.until(`!document.querySelector(".fw-backs-open") && scrollY === 0`, 3000)
    && (await t.js(rect(".fw-header")))[0] === head[0], JSON.stringify([head, await t.js(rect(".fw-header")), await t.js("scrollY")]));
  await wheel(-200);
  await t.until(`!!document.querySelector(".fw-backs-open")`, 2000);
  t.check("  left alone in them a while: back by themselves, the pericope at the top", await t.until(`!document.querySelector(".fw-backs-open") && scrollY === 0`, 3000)
    && (await t.js(rect(".fw-header")))[0] === head[0], JSON.stringify([head, await t.js(rect(".fw-header"))]));
  await wheel(-200);
  await t.until(`!!document.querySelector(".fw-backs-open")`, 2000);
  await t.cdp("Input.dispatchMouseEvent", { type: "mouseMoved", x: 300, y: 20 });
  await t.cdp("Input.dispatchMouseEvent", { type: "mouseMoved", x: 300, y: 700 });
  t.check("  the mouse in them and out again: back soon after", await t.until(`!document.querySelector(".fw-backs-open") && scrollY === 0`, 2000));
  await t.select("beta's words", { collapse: true, start: true });
  for (let i = 0; i < 3; i++) await t.key("ArrowUp");
  await t.key("Enter"); await t.key("ArrowUp");
  t.check("  ↵ on it: into them too; ↑ the one above", await t.until(`document.querySelector(".fw-backs-open .fw-sel")?.dataset.pericope === "${A}"`, 2000));
  await t.key("Enter");
  t.check("  ↵ opens it where it points: alpha, at its quote of beta", await t.until(`window.fw?.editor()?.id === "${A}" && location.hash.includes("@${QA}")`, 4000));
  await t.key("[", 4);
  t.check("  ⌘[ back to beta", await t.until(`window.fw?.editor()?.id === "${B}"`, 4000));
};

scenarios.kindtree = async (t) => {   // kinds of kinds (2026-11-23): nested in each kind they're of, roots at the top, ↻ for a loop
  const act = (body) => t.js(`fetch("/api/act", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(${JSON.stringify(body)}) }).then((r) => r.json())`);
  await t.open("#/");
  const F = (await act({ do: "newkind", name: "form" })).kind, S = (await act({ do: "newkind", name: "sonnet" })).kind;
  await act({ do: "kind", block: S, kind: K, answer: true });
  await act({ do: "kind", block: S, kind: F, answer: true });
  await act({ do: "kind", block: K, kind: F, answer: true });
  await act({ do: "kind", block: A, kind: S, answer: true });
  await t.key("u", 4 | 8);
  const rows = `[...document.querySelectorAll(".fw-kindsview .fw-row")].map((r) => r.innerText.replace(/\\s+/g, " ").trim()).join(" | ")`;
  t.check("only the kinds of no kind at the top: form", await t.until(`${rows}.startsWith("▸ form 2 | ▸ no tag")`, 3000), await t.js(rows));
  await t.key("ArrowRight");
  t.check("  → form: poem and sonnet nested in it, as kinds", await t.until(`${rows}.startsWith("▾ form 2 | ▸ sonnet 1 | ▸ poem 1 | ▸ no tag")`, 2000), await t.js(rows));
  await t.key("ArrowDown"); await t.key("ArrowDown"); await t.key("ArrowRight");
  t.check("  → poem: sonnet again inside it, a level further in (in every place it's of)", await t.until(`${rows}.startsWith("▾ form 2 | ▸ sonnet 1 | ▾ poem 1 | ▸ sonnet 1 | ▸ no tag")
    && document.querySelectorAll('.fw-kindsview [data-kind="${S}"]').length === 2`, 2000), await t.js(rows));
  await t.key("ArrowDown"); await t.key("ArrowRight");
  t.check("  → sonnet there: its own member", await t.until(`${rows}.includes("▾ sonnet 1 | alpha")`, 2000), await t.js(rows));
  await t.key("ArrowLeft"); await t.key("ArrowLeft");
  t.check("  ← ←: sonnet folded, then out to poem, folded", await t.until(`${rows}.startsWith("▾ form 2 | ▸ sonnet 1 | ▸ poem 1 | ▸ no tag")
    && document.querySelector(".fw-sel")?.dataset.kind === "${K}"`, 2000), await t.js(rows));
  await t.key("ArrowRight"); await t.key("ArrowDown"); await t.key("n");
  t.check("  N on sonnet in poem: taken out of poem (form keeps it)", await t.until(`${rows}.startsWith("▾ form 2 | ▸ sonnet 1 | ▾ poem 0 | ▸ no tag")`, 3000), await t.js(rows));
  await act({ do: "kind", block: F, kind: S, answer: true });   // (a loop: form is a sonnet, a sonnet is a form)
  const tops = `[...document.querySelectorAll(".fw-kindsview .fw-kind:not(.fw-nested):not(.fw-nokind)")].map((r) => r.dataset.kind).join(",")`;
  t.check("  a loop: every kind of some kind; the oldest (poem) at the top, then the first the loop would hide (made the same second: either)",
    await t.until(`["${K},${F}", "${K},${S}"].includes(${tops})`, 3000), await t.js(rows));
  const second = (await t.js(tops)).split(",")[1];
  for (let i = 0; i < 9; i++) await t.key("ArrowUp");
  await t.key("ArrowDown");
  if (!(await t.js(`document.querySelector(".fw-sel")?.dataset.kind === "${second}" && document.querySelector(".fw-sel").innerText.startsWith("▾")`))) await t.key("ArrowRight");
  await t.key("ArrowDown"); await t.key("ArrowRight");
  t.check("  the other opened inside it: it met again inside itself, ↻", await t.until(`[...document.querySelectorAll(".fw-loop")].some((r) => r.dataset.kind === "${second}")`, 3000), await t.js(rows));
};

scenarios.kindsview.setup = (dir, data) => {   // guesses (current): fox is a poem (sure), masker maybe
  const at = Object.fromEntries(data.blocks.map((b) => [b.id, b.updated]));
  writeFileSync(join(dir, "kind-guesses.json"), JSON.stringify({ model: "test", guesses: { [K]: { [T]: [0.95, at[K], at[T]], [M]: [0.7, at[K], at[M]] } } }));
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
    const before = await storedIn(t.dir);
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
    await t.settle();
    const after = await storedIn(t.dir);
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
