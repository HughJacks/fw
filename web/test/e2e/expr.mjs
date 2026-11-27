import { A, A1, B, K, R, T, addExpr, lastOut, setCode, sleep } from "./fixture.mjs";

export const scenarios = {};

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
  t.check("  the engine loads; the result follows the code, dim below it (a String its words, TYPE.md \"Casting\")", await t.until(`document.querySelector(".fw-expr-out")?.textContent === 'big!'`, 8000),
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
  t.check("  opened again: its result (a String: its words)", await t.until(`document.querySelector(".fw-expr-out")?.textContent === 'big!'`, 8000));
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

scenarios.codebox = async (t) => {   // the code written in CodeMirror: highlighted; @ opens fw's search; a reference drawn as its title
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
  t.check("  the result follows", await t.until(`document.querySelector(".fw-expr-out")?.textContent === 'fox'`, 5000), await t.js(`document.querySelector(".fw-expr-out")?.textContent`));
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

scenarios.exprbrowse = async (t) => {   // a value's blocks: moved through as any nesting, at block level; no caret, nothing changes them
  await t.open(`#/p/${A}`);
  await addExpr(t, `Blocks([body(@${T}), text("after")])`);
  const out = `[...document.querySelectorAll(".fw-doc .fw-expr > .fw-expr-out")].at(-1)`;
  const val = `${out}?.querySelector(":scope > .fw-body > .ProseMirror")`;
  await t.until(`${val}?.children.length === 2`, 8000);
  const before = await t.js(`${val}.textContent`);
  const chosen = `(() => { const c = [...(${out}?.querySelectorAll(".fw-chosen") || [])].at(-1); if (!c) return null; const k = c.cloneNode(true); k.querySelectorAll(".fw-open-name").forEach((x) => x.remove()); return k.textContent; })()`;   // (its text, not the hover names)
  const noCaret = `(() => { const s = getSelection(); return !(s.rangeCount && s.isCollapsed && s.anchorNode?.parentElement?.closest(".fw-expr-out")); })()`;
  const FOX = "↗the quick brown foxjumps over the dog";   // (body(@fox): a From, drawn as a quote of fox, its ↗ first)
  await t.select("first words", { collapse: true });
  for (let i = 0; i < 8 && !(await t.js(chosen)); i++) await t.key("ArrowDown");
  t.check("the arrows go into a value: its first block (body(@fox), a green quote) selected whole, no caret", (await t.js(chosen)) === FOX && await t.js(noCaret), String(await t.js(chosen)));
  t.check("  its tabs: red on the path, its value a window (colour by what it is)", await t.until(`!!document.querySelector(".fw-tab.fw-tab-quote")`, 2000));
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
  t.check("  selected whole, the text's colour: its value is several blocks (one of them a window), not a window", await t.until(`${lit} === "rgb(221, 218, 211)"`, 2000), await t.js(lit));
  await t.key("ArrowRight");
  t.check("  →: in a level, its first block", await t.until(`${chosen} === ${JSON.stringify(FOX)}`, 2000), String(await t.js(chosen)));
  await t.key("Enter");
  await t.shot("exprbrowse.png", { x: 0, y: 0, width: 1100, height: 560 });
  await t.settle();
  t.check("  the store: just the expression, its source as written", (await t.kids(A)).filter((k) => k.t === "expr").map((k) => k.source).join() === `Blocks([body(@${T}), text("after")])`,
    JSON.stringify(await t.kids(A)));
};

scenarios.expropen = async (t) => {   // TYPE.md: if you can reference it, you can open it; any @ref is a backlink
  await t.open(`#/p/${A}`);
  await addExpr(t, `body(@${T})`);
  await t.until(`!!document.querySelector(".fw-doc .fw-expr .fw-from")`, 8000);
  await t.key("o", 4);
  t.check("⌘O on an expression whose value is one From: its source opens", await t.until(`location.hash.startsWith("#/p/${T}")`, 3000), await t.js("location.hash"));
  await t.open(`#/p/${A}`);
  await addExpr(t, `Blocks([body(@${T}), body(@${B})])`);
  await t.until(`[...document.querySelectorAll(".fw-doc .fw-expr")].at(-1)?.querySelectorAll(".fw-from").length === 2`, 8000);
  await t.key("o", 4);
  await sleep(300);
  t.check("  a value of two windows: ⌘O on it whole opens nothing (not what its code names)", (await t.js("location.hash")).startsWith(`#/p/${A}`) && !(await t.js(`!!document.querySelector(".fw-menu")`)),
    await t.js("location.hash"));
  await t.key("ArrowRight");
  await t.key("o", 4);
  t.check("  → into it, its first window: ⌘O opens that one", await t.until(`location.hash.startsWith("#/p/${T}")`, 3000), await t.js("location.hash"));
  await t.open(`#/p/${R}`);   // (a pericope of its own: nothing left where the caret was)
  await addExpr(t, `backlinks(@${B})`);
  const items = `[...([...document.querySelectorAll(".fw-doc .fw-expr")].at(-1)?.querySelectorAll(".fw-expr-out > .fw-item") || [])]`;
  await t.until(`${items}.length >= 2`, 8000);
  const names = await t.js(`${items}.map((x) => x.textContent)`);
  await t.key("o", 4);
  await sleep(300);
  t.check("a list of references: ⌘O on it whole doesn't open beta, what its code reads", (await t.js("location.hash")).startsWith(`#/p/${R}`), await t.js("location.hash"));
  await t.key("Enter");
  await t.settle();
  t.check("  Enter on it selected whole: a new block after it, the caret in it, as on any block (not into its list)", await t.js(`(() => {
    const st = window.fw.editor().view.state, sel = st.selection, $f = sel.$from;
    const before = $f.depth ? st.doc.resolve($f.before($f.depth)).nodeBefore : null;
    return sel.empty && $f.parent.type.name === "text_block" && $f.parent.content.size === 0 && before?.type.name === "expr"; })()`)
    && !(await t.js(`${items}.some((x) => x.classList.contains("fw-item-sel"))`)), await t.js(`JSON.stringify(window.fw.editor().view.state.selection.toJSON())`));
  await t.key("ArrowUp");
  await t.until(`[...document.querySelectorAll(".fw-doc .fw-expr")].at(-1)?.classList.contains("ProseMirror-selectednode")`, 2000);
  await t.key("ArrowLeft");
  t.check("  ← onto its last item", await t.until(`${items}.findIndex((x) => x.classList.contains("fw-item-sel")) === ${items}.length - 1`, 1000));
  await t.key("Escape");
  await t.key("ArrowRight");
  await t.key("ArrowRight");
  t.check("  → onto its items, one at a time", await t.until(`${items}.findIndex((x) => x.classList.contains("fw-item-sel")) === 1`, 1000), JSON.stringify(names));
  t.check("  on an item: the expression where you are (as a block with the caret in it: its box, its lines, its room), the item lit, its tab not filled", await t.until(`(() => {
    const ex = [...document.querySelectorAll(".fw-doc .fw-expr")].at(-1);
    return ex.matches(".fw-here.fw-in-item:not(.fw-chosen)") && !document.querySelector(".fw-tab.fw-tab-filled") && document.querySelectorAll(".fw-link-line").length > 0; })()`, 1000),
    await t.js(`[...document.querySelectorAll(".fw-doc .fw-expr")].at(-1).className + " | " + [...document.querySelectorAll(".fw-tab")].map((x) => x.className).join(" | ")`));
  const second = await t.js(`${items}[1].querySelector(".fw-ref")?.title.slice(1, 21)`);
  await t.key("o", 4);   // (on its second)
  t.check("  ⌘O on an item: that one opens", await t.until(`location.hash.startsWith("#/p/${"${second}"}")`.replace("${second}", second), 3000), await t.js("location.hash") + " " + JSON.stringify(names) + " " + second);
  await t.open(`#/p/${A}`);
  await t.settle();
  const back = (await t.get(`/api/pericope/${T}`)).backlinkRows || [];
  t.check("any @reference in an expression is a backlink of what it names", back.some((r) => r.kind === "expression" && r.open === A), JSON.stringify(back));
  // the same, the expression seen through a quote (alpha quotes beta; beta holds it): its item lit there too
  await t.open(`#/p/${B}`);
  await addExpr(t, `backlinks(@${B})`);
  await t.settle();
  await t.open(`#/p/${A}`);
  await t.select("beta's words", { collapse: true });
  await t.key("ArrowDown");
  const qex = `document.querySelector(".fw-doc .fw-quote .fw-expr")`;
  await t.until(`${qex}?.classList.contains("ProseMirror-selectednode")`, 2000);
  const qgo = `${qex}.closest(".fw-quote").querySelector(":scope > .fw-top > .fw-open")`;
  const seen = `(() => { let o = 1; for (let e = ${qgo}; e && e !== document.body; e = e.parentElement) o *= +getComputedStyle(e).opacity; return o; })()`;
  t.check("  an expression in a quote selected: the quote's ↗ not lit (⌘O opens what the expression is, not the quote): as at rest, faint, no line (one look for not lit)",
    await t.until(`getComputedStyle(${qgo}).outlineStyle === "none" && Math.abs(${seen} - 0.45) < 0.02`, 1000),
    await t.js(`getComputedStyle(${qgo}).outlineStyle + " " + ${seen}`));
  await t.key("ArrowRight");
  await sleep(300);
  t.check("  through a quote: → onto its first item, lit (and still lit after the page redraws it)", await t.until(`!!${qex}?.querySelector(".fw-item.fw-item-sel")`, 1000),
    await t.js(`(${qex}?.className || "none") + " | " + (${qex}?.querySelector(".fw-expr-out")?.innerHTML || "").slice(0, 300)`));
};

scenarios.neighbours = async (t) => {   // above and below: the peer blocks around an expression, where it sits now
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

scenarios.facts = async (t) => {   // every fact typed, and its own (TYPE.md "Every fact typed")
  await t.open(`#/p/${B}`);
  await addExpr(t, `title(pericopeOf(above))`);
  t.check("a block's pericope, and its title", await t.until(`${lastOut}?.textContent === 'beta'`, 8000), await t.js(`${lastOut}?.textContent`));
  await addExpr(t, `created(@${A})`);
  t.check("  created: a Date, drawn as fw writes dates", await t.until(`${lastOut}?.textContent === 'Oct 1, 2026, 10:00 am'`, 4000)
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

  // this: the expression itself, where it sits
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

scenarios.dollar = async (t) => {   // $ in an empty block: an expression; \$ a dollar sign (TYPE.md "Inline")
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

scenarios.exprcall = async (t) => {   // a quote of an expression is a call: evaluated where the quote sits, one red box
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

scenarios.unwrap = async (t) => {   // a value of one block is unwrapped: its holder's box, never gone into
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
  t.check("  one tab, filled, the text's own colour (its value's text)", await t.until(`(() => { const ts = [...document.querySelectorAll(".fw-tab")]; return ts.length === 1 && ts[0].matches(".fw-tab-filled") && !ts[0].matches(".fw-tab-expr, .fw-tab-quote"); })()`, 2000),
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
  const chosen = `(() => { const c = [...(${ex2}?.querySelectorAll(".fw-chosen") || [])].at(-1); if (!c) return null; const k = c.cloneNode(true); k.querySelectorAll(".fw-open-name").forEach((x) => x.remove()); return k.textContent; })()`;   // (its text, not the hover names)
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
  t.check("  its top line as any quote's: a window is a window, however it was made", await t.js(`(() => { const q = ${valueDoc}.querySelector(":scope > .fw-quote.fw-from");
    const plain = document.querySelector(".fw-doc > .ProseMirror > .fw-quote:not(.fw-from) > .fw-top");
    return getComputedStyle(q.querySelector(".fw-top")).color === getComputedStyle(plain).color; })()`));
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
  t.check("  created (a Date, drawn as fw writes dates)", await t.until(`${lastOut}?.textContent === 'Oct 1, 2026, 10:00 am'`, 4000), await t.js(`${lastOut}?.textContent`));
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

scenarios.tuples = async (t) => {   // a mixed tuple: each part its own colour, by its own evaluated type
  await t.open(`#/p/${R}`);
  await addExpr(t, `(1, "a", @${T}, @${K}, ?)`);
  const tones = (sel) => `[...(${sel}?.querySelectorAll(".fw-part") || [])].map((x) => [...x.classList].find((c) => c.startsWith("fw-tone-")).slice(8) + ":" + x.textContent).join(" ")`;
  t.check("a tuple: its parts, each its type's tone (data, text, a Ref red, a tag blue, a hole amber)", await t.until(`${tones(lastOut)} === "data:1 text:a ref:fox tag:poem hole:?"`, 4000), await t.js(tones(lastOut)));
  t.check("  coloured so: a number green, a tag blue, a hole amber", await t.js(`(() => { const p = [...${lastOut}.querySelectorAll(".fw-part")].map((x) => getComputedStyle(x).color);
    return new Set(p).size >= 4; })()`), await t.js(`[...${lastOut}.querySelectorAll(".fw-part")].map((x) => getComputedStyle(x).color).join(" ")`));
  t.check("  its parts stepped through as a list's items", await t.js(`${lastOut}.querySelectorAll(":scope > .fw-item").length === 5`));
  await t.select("r words", { collapse: true });
  await t.type(" ");
  await t.type("$");
  await t.type(`(2, @${T})`);
  await t.type("$");
  await t.settle();
  const inl = `[...document.querySelectorAll(".fw-doc .fw-icode-out")].at(-1)`;
  t.check("  inline too", await t.until(`${tones(inl)} === "data:2 ref:fox"`, 4000), await t.js(`${inl}?.outerHTML`));
};

scenarios.unicode = async (t) => {   // a value's links after text that isn't ASCII: on their own words (offsets as the page counts them)
  await t.open(`#/p/${R}`);
  await addExpr(t, `Text([Plain("é😀 wörd "), Link(("fox", @${T})), Plain(" ü")])`);
  const link = `${lastOut}?.querySelector(".fw-link")?.textContent`;
  t.check("its link on just its words", await t.until(`${link} === "fox"`, 4000), await t.js(`${lastOut}?.outerHTML`));
};
