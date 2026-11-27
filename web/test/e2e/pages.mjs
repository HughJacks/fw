import { join } from "node:path";
import { readFileSync } from "node:fs";
import { A, A1, B, B1, QA, R, S0, S1, S2, T, T1, sleep } from "./fixture.mjs";

export const scenarios = {};

scenarios.visit = async (t) => {   // opening a pericope and leaving it changes nothing (the sweep found it could:)
  await t.open(`#/p/${S0}`);
  await t.open("#/");
  const c = (await t.kids(S0))[0];
  t.check("a pericope visited and left: unchanged (a container holding one block kept, its ids)", c.t === "container" && c.id === S1 && c.children[0].id === S2,
    JSON.stringify(c));
};

scenarios.deleting = async (t) => {   // a pericope deleted, from home and from inside it; asked first, in the page
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
};

scenarios.bindings = async (t) => {   // the keys page: a command given other keys, which then work; the browser's own refused; the default back
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
};

scenarios.home = async (t) => {
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
  t.check("  in the list itself, no menu over it: what doesn't match gone",
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
};

scenarios.visits = async (t) => {   // your attention told to the core, written as visits (the web editor recorded none)
  await t.open(`#/p/${B}@${B1}`);
  await t.type("x");
  t.check("opened, written in: told", await t.until(`(window.fwVisits || []).some(v => v.pericope === "${B}")
    && (window.fwVisits || []).some(v => v.block === "${B1}" && v.flags.includes("w"))`, 2000), await t.js(`JSON.stringify(window.fwVisits)`));
  await t.open("#/");
  t.check("  left: written into the store", await t.until(`(window.fwVisits || []).some(v => v.flush)`, 2000)
    && await (async () => { for (let n = 0; n < 40; n++) { const d = JSON.parse(readFileSync(join(t.dir, "freewrites.json"), "utf8"));
      if (d.blocks.find((b) => b.id === B1)?.visits?.recent?.some(([, f]) => f.includes("w"))) return true; await sleep(50); } return false; })());
};

scenarios.exits = async (t) => {   // the foot of every page: the same as home's, the search and the suggestions from here
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
  // following what's written: a suggestion quoted here leaves the suggestions once it's saved, the page not opened again
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
};

scenarios.onepage = async (t) => {   // one page: one header and one body for every pericope; moving changes what they show
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
};

scenarios.waiting = async (t) => {   // home: a waiting pericope in the middle, the search and the list below it; typed in, it's made
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
  t.check("typed in: no longer waiting, the suggestions kept below it", await t.js(`!document.querySelector(".fw-waiting") && !!document.querySelector(".fw-centre + .fw-suggested .fw-library .fw-row")`));
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
};

scenarios.away = async (t) => {   // send it away (⌘⇧↵): from a pericope, saved and home; ⌘[ reaches it; a blank one: nothing
  await t.open(`#/p/${T}`);
  await t.end();
  await t.type(" and away");
  await t.js(`window.__foot = document.querySelector(".fw-suggested"); 1`);
  await t.key("Enter", 12);   // (at once: nothing waited for)
  t.check("a pericope sent away (⌘⇧↵): home", await t.until(`window.fw.home() && !window.fw.editor()?.id && location.hash === "#/"`, 3000));
  await t.settle();
  const k = await t.kids(T);
  t.check("  what was typed just before, saved", k[1].text === "jumps over the dog and away", JSON.stringify(k));
  t.check("  only the pericope went: the suggestions stayed on the page", await t.js(`document.querySelector(".fw-suggested") === window.__foot`));
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
};

scenarios.title = async (t) => {   // a title typed slowly, saves and the header's redraws landing between the keys: every key kept, the cursor never taken
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
};

scenarios.trail = async (t) => {   // ⌘O steps into a quote's source, ⌘[ steps out again, ⌘] back in; ⌘[ never leaves fw
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
};

scenarios.liveHeader = async (t) => {   // the header's words and updated change as you type, before any save
  await t.open(`#/p/${T}@${T1}`);
  const words = `+document.querySelector(".fw-hbox").innerText.match(/words (\\d+)/)[1]`;
  const before = await t.js(words);
  await t.select("the quick brown fox", { collapse: true });
  await t.type(" and two more");
  t.check("typing: the word count up at once (before the save)", (await t.js(words)) === before + 3, `${before} -> ${await t.js(words)}`);
  t.check("  updated: just now", await t.js(`document.querySelector(".fw-hbox").innerText.includes("updated just now")`));
  await t.settle();
  t.check("  saved: the store's count agrees", (await t.get(`/api/pericope/${T}`)).words === before + 3);
  t.check("every field shown, an empty one saying none", await t.js(`(() => { const h = document.querySelector(".fw-hbox").textContent.replace(/ +/g, " "), flat = h.replace(/ /g, "");
    return ["created ", "updated ", "words ", "last visited ", "backlinks", "tags", "title"].every((f) => h.includes(f))
      && h.includes("last visited none") && !h.includes("paraphrase of") && flat.includes("tagsnone"); })()`),
    await t.js(`document.querySelectorAll(".fw-hbox").length + " " + document.querySelector(".fw-header").outerHTML.slice(0, 1500)`));
};

scenarios.livetype = async (t) => {   // the header's type follows what's written, on the key
  await t.open(`#/p/${B}`);
  const type = `document.querySelector(".fw-label").textContent`;
  t.check("one block of text: text", await t.until(`${type} === "text"`, 2000), await t.js(type));
  await t.end();
  await t.key("Enter");
  t.check("  Enter, a second block: pericope, at once", await t.until(`${type} === "pericope"`, 500), await t.js(type));
  await t.key("Backspace");
  t.check("  ⌫, one again: text", await t.until(`${type} === "text"`, 500), await t.js(type));
};

scenarios.backlinks = async (t) => {   // the backlinks above the header: a sliver at the window's top, ↑ into them
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
