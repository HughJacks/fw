// e2e.mjs — the web editor end to end: real keys into the real page, the store checked through the core.
//   node test/e2e.mjs [scenario …] [--shots DIR] [--jobs N] [--sweep DIR]   (from web/; build first; VERBOSE=1 every check)
// Each scenario (test/e2e/*.mjs, by subject) gets a store of its own, its own core on its own port, and its own tab in
// one headless Chrome, driven over the DevTools protocol (Node's own WebSocket); --jobs of them at once (default 4).
// The page is opened with ?test (its timers quick) and says when it has settled (window.fw.settled()), so the tests
// wait on that, never on fixed sleeps; window.fw.select puts the cursor where a test wants it. Keys are real key
// events (Input.dispatchKeyEvent): what's tested is the page's own handling of them.
import { spawn, execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, writeFileSync, readFileSync, rmSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { STORE, sleep, storedIn } from "./e2e/fixture.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const FW = resolve(HERE, "../..");
const PY = process.env.FW_PYTHON || join(FW, ".venv/bin/python");
// the core: the fw.web package, run as a module from the repo's root (an older checkout: its script)
const CORE = existsSync(join(FW, "fw/web/__main__.py")) ? ["-m", "fw.web"] : [join(FW, "fw/web.py")];
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const argv = process.argv.slice(2);
const opt = (name, dflt) => (argv.includes(name) ? argv[argv.indexOf(name) + 1] : dflt);
const SHOTS = opt("--shots", null), JOBS = +opt("--jobs", 4);
const ONLY = argv.filter((a, n) => !a.startsWith("--") && !["--shots", "--jobs", "--sweep"].includes(argv[n - 1]));
const scenarios = {};
for (const f of readdirSync(join(HERE, "e2e")).filter((f) => f.endsWith(".mjs") && f !== "fixture.mjs").sort()) {
  Object.assign(scenarios, (await import(join(HERE, "e2e", f))).scenarios);
}

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
  const env = { ...process.env, PYTHONPATH: FW, FW_DATA: store, FW_MEANING_URL: "off", FW_WEB_WATCH: "0" };   // (never rebuilt or restarted mid-test)
  execFileSync(PY, ["-m", "fw.store", "migrate"], { env, cwd: FW, stdio: "ignore" });
  if (fn.setup) fn.setup(dir, JSON.parse(readFileSync(store, "utf8")));   // (what a scenario needs beside its store)
  const port = 20000 + Math.floor(Math.random() * 20000);
  const server = spawn(PY, [...CORE, "--port", String(port), "--no-open"], { env, cwd: FW, stdio: "ignore" });
  const out = [];
  let ok = true;
  const { cdp, thrown, close } = await tab();
  const js = async (expr) => (await cdp("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true })).result?.result?.value;
  const until = async (expr, ms = 4000) => { for (const end = Date.now() + ms; Date.now() < end; await sleep(25)) if (await js(expr)) return true; return false; };
  const t = {
    js, until, cdp, port, dir, tab,
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
    async hover(x, y) { await cdp("Input.dispatchMouseEvent", { type: "mouseMoved", x, y }); },
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
    /** The cursor at the very end of the open pericope (a pericope opens at its top). */
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
