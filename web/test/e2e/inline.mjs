import { join } from "node:path";
import { writeFileSync } from "node:fs";
import { A, B, B1, N, R, T, addExpr, lastOut, setCode, sleep, window2 } from "./fixture.mjs";

export const scenarios = {};

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
  await t.key("ArrowDown");
  t.check("  ↑/↓ from it selected: the caret moves on a line, nothing left selected", await t.until(`!document.querySelector(".fw-doc .fw-icode-sel") && getSelection().isCollapsed`, 1000),
    await t.js(`document.querySelectorAll(".fw-doc .fw-icode-sel").length + " " + getSelection().isCollapsed`));
  await t.select(" more", { collapse: true, start: true });
  await t.key("ArrowLeft");
  await t.key("ArrowLeft");
  await t.key("ArrowRight");
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
  // a bare reference computes nothing: no ƒ; @ in open code searches and puts the reference in the code; ⌘O on one
  // selected opens what it is
  const lastOut = `${outs}.at(-1)`;
  t.check("a bare @reference: no ƒ (nothing computed)", await t.js(`(() => { const o = [...document.querySelectorAll(".fw-doc .fw-icode-out")].find((x) => x.querySelector(".fw-ref")?.textContent === "alpha");
    return !!o && o.classList.contains("fw-bare") && getComputedStyle(o, "::after").content === "none"; })()`));
  await t.end();
  await t.type(" ");
  await t.type("$");
  await t.type("wordCount(");
  await t.type("@");
  t.check("@ in open code: fw's search", await t.until(`document.querySelector(".fw-menu")?.innerText.includes("@ ›")`, 2000));
  await t.type("alpha");
  await t.until(`[...document.querySelectorAll(".fw-menu .fw-row.fw-sel")].some(r => r.innerText.includes("alpha"))`, 2000);
  await t.key("Enter");
  await t.type(")");
  await t.type("$");
  await t.settle();
  t.check("  the pick in the code, @id; closed, its value, with its ƒ (it computes)", (await b1()).endsWith(`$wordCount(@${A})$`)
    && await t.until(`/^[0-9]+$/.test(${lastOut}?.textContent || "") && getComputedStyle(${lastOut}, "::after").content !== "none"`, 3000), await b1());
  await t.select(" then", { collapse: true, start: true });   // (just after the bare alpha)
  await t.key("ArrowLeft");
  await t.until(`!!document.querySelector(".fw-doc .fw-icode-sel .fw-ref")`, 1000);
  await t.key("o", 4);
  t.check("⌘O on a reference selected: it opens", await t.until(`location.hash.startsWith("#/p/${A}")`, 3000), await t.js("location.hash"));
  // an inline list of references: ⌘O on it selected lists just their titles; Enter opens the one chosen
  await t.open(`#/p/${B}`);
  await t.open(`#/p/${A}`);   // (opened afresh: arriving by ⌘O is quiet, its first key held)
  await t.end();
  await t.type(" ");
  await t.type("$");
  await t.type(`[@${A}, @${B}]`);
  await t.type("$");
  await t.key("ArrowLeft");
  await t.until(`document.querySelectorAll(".fw-doc .fw-icode-sel .fw-ref").length === 2`, 4000);   // (its value worked out)
  await t.key("o", 4);
  const rows = `[...document.querySelectorAll(".fw-menu .fw-row")].map((x) => x.textContent)`;
  const here0 = await t.js("location.hash");
  t.check("⌘O on an inline list selected: its references listed, titles only", await t.until(`${rows}.length === 2 && !document.querySelector(".fw-menu .fw-foot")`, 2000),
    await t.js(`(document.querySelector(".fw-menu")?.outerHTML.slice(0, 200) || "no menu") + " | sel " + document.querySelectorAll(".fw-doc .fw-icode-sel").length + " | refs-in-sel " + document.querySelectorAll(".fw-doc .fw-icode-sel .fw-ref").length + " | outs " + [...document.querySelectorAll(".fw-doc .fw-icode-out")].map((x) => x.className + ":" + x.textContent).slice(-3).join(" ; ") + " | selection " + JSON.stringify(window.fw.editor()?.view.state.selection.toJSON()) + " | " + location.hash`));
  await t.key("ArrowDown");
  await t.key("Enter");
  t.check("  ↓, Enter: that one opens", await t.until(`location.hash !== ${JSON.stringify("")} && location.hash !== "${"HERE0"}"`.replace("HERE0", here0), 3000), await t.js("location.hash"));
};

scenarios.projection = async (t) => {   // x.f written for f(x) (TYPE.md "Projection")
  await t.open(`#/p/${B}`);
  await addExpr(t, `@${B}.wordCount + @${A}.title.string_length`);
  t.check("x.f is f(x): beta's words (2) and alpha's title's length (5)", await t.until(`${lastOut}?.textContent === "7"`, 8000), await t.js(`${lastOut}?.textContent`));
  await addExpr(t, `this.created.daysBetween(now) >= 0`);
  t.check("  chained, with an argument (x.f(a) is f((x, a)))", await t.until(`${lastOut}?.textContent === "true"`, 4000), await t.js(`${lastOut}?.textContent`));
  // the code box: after a dot, what can be projected, what fits first
  await t.js(`[...document.querySelectorAll(".fw-doc .fw-expr")].at(-1).fwExpr.showCode()`);
  await t.until(`!!document.activeElement?.closest(".fw-expr-code")`, 2000);
  await setCode(t, "");
  await t.type("this");
  await t.type(".");
  const labels = `[...document.querySelectorAll(".cm-tooltip-autocomplete li .cm-completionLabel")].map((x) => x.textContent)`;
  t.check("after a dot in the code: what can be projected, a Ref's first (wordCount before year)", await t.until(`(() => { const l = ${labels}; return l.includes("wordCount") && l.includes("year") && l.indexOf("wordCount") < l.indexOf("year"); })()`, 2000),
    await t.js(`JSON.stringify(${labels}.slice(0, 12))`));
  await t.type("wordC");
  await sleep(150);
  await t.key("Tab");
  t.check("  Tab takes it", await t.until(`document.querySelector(".fw-expr-codebox").fwCode.state.doc.toString() === "this.wordCount"`, 2000),
    await t.js(`document.querySelector(".fw-expr-codebox").fwCode.state.doc.toString()`));
  const before = (a, b) => `(() => { const l = ${labels}; return l.includes("${a}") && l.includes("${b}") && l.indexOf("${a}") < l.indexOf("${b}"); })()`;
  for (const [x, a, b, what] of [['"ab"', "string_trim", "wordCount", "a String's: Hazel's string functions"], ["pericopes", "map", "wordCount", "a list's: Hazel's list functions"]]) {
    await setCode(t, "");
    await t.type(x);
    await t.type(".");
    t.check(`  ${what} first (${a} before ${b})`, await t.until(before(a, b), 2000), await t.js(`JSON.stringify(${labels}.slice(0, 12))`));
  }
  await t.key("x", 4 | 8);
  await t.until(`!document.querySelector(".fw-expr-code")`, 2000);
  await t.settle();
  // inline code: the same list, at the dot
  await t.select("beta's words", { collapse: true });
  await t.type(" has ");
  await t.type("$");
  await t.type("this.");
  t.check("after a dot in inline code: the list, at the dot", await t.until(`[...document.querySelectorAll(".fw-menu .fw-row")].some((r) => r.textContent === "wordCount")`, 2000),
    await t.js(`document.querySelector(".fw-menu")?.innerText.slice(0, 200)`));
  await t.type("wordC");
  await t.key("Enter");
  await t.type("$");
  await t.settle();
  const b1 = (await t.kids(B))[0].text;
  t.check("  Enter takes it; closed, its value", b1 === "beta's words has $this.wordCount$" && await t.until(`/^[0-9]+$/.test([...document.querySelectorAll(".fw-doc .fw-icode-out")].at(-1)?.textContent.replace(/ƒ$/, "") || "")`, 3000), b1);
};

scenarios.deptabs = async (t) => {   // an expression's dependencies, a tab each down its right side
  await t.open(`#/p/${R}`);
  const tabs = `[...([...document.querySelectorAll(".fw-doc .fw-expr")].at(-1)?.querySelectorAll(".fw-deps > .fw-dep") || [])]`;
  const names = `${tabs}.map((x) => (x.classList.contains("fw-dep-more") ? x.querySelector(".fw-dep-mark").textContent + ":" : "") + x.querySelector(".fw-dep-name").textContent)`;
  await addExpr(t, `wordCount(@${T})`);
  t.check("one dependency: one tab, its name in it (shown as it's hovered)", await t.until(`JSON.stringify(${names}) === '["fox"]'`, 4000), await t.js(`JSON.stringify(${names})`));
  const ex = `[...document.querySelectorAll(".fw-doc .fw-expr")].at(-1)`;
  t.check("  the block active: shown, the ƒ's square exactly (its line just outside, as the lit ƒ's)", await t.until(`(() => {
    const f = ${ex}.querySelector(".fw-fn").getBoundingClientRect(), d = ${ex}.querySelector(".fw-dep")?.getBoundingClientRect();
    return !!d && d.width > 0 && Math.abs(d.height - (f.height + 2)) < 0.6 && Math.abs(d.left - (f.left - 1)) < 0.6; })()`, 2000),
    await t.js(`JSON.stringify([${ex}.querySelector(".fw-fn").getBoundingClientRect(), ${ex}.querySelector(".fw-dep")?.getBoundingClientRect()])`));
  t.check("  a dependency, not a reference: ↙, dim, never lit (⌘O doesn't open it)", await t.js(`(() => { const d = ${ex}.querySelector(".fw-dep"), m = d.querySelector(".fw-dep-mark");
    return getComputedStyle(m).transform !== "none" && +getComputedStyle(d).opacity < 1; })()`));
  await t.select("r words", { collapse: true });
  t.check("  not active: not shown (the ƒ alone)", await t.until(`!${ex}.querySelector(".fw-dep")?.getBoundingClientRect().width`, 2000));
  await addExpr(t, `Blocks([text("one"), text("two"), text("three"), text("four"), text(@${A}.title ++ @${B}.title ++ @${A}.title ++ @${R}.title)])`);
  t.check("  a tall one naming alpha (twice), beta and the page you're on: alpha, beta (each once; not here)", await t.until(`JSON.stringify(${names}) === '["alpha","beta"]'`, 4000), await t.js(`JSON.stringify(${names})`));
  await t.shot("deptabs.png", { x: 0, y: 100, width: 1100, height: 360, scale: 2 });
  await t.js(`${tabs}[1].dispatchEvent(new MouseEvent("mousedown", { bubbles: true }))`);
  t.check("  a click on one: it opens", await t.until(`location.hash.startsWith("#/p/${B}")`, 3000), await t.js("location.hash"));
  await t.open(`#/p/${R}`);
  await addExpr(t, `wordCount(@${A}) + wordCount(@${B}) + wordCount(@${T})`);
  t.check("  more than its height has room for: the rest behind +n, all of them named there", await t.until(`(() => { const n = ${names}; return n.length >= 1 && n.at(-1).startsWith("+") && n.join(",").includes("fox"); })()`, 4000),
    await t.js(`JSON.stringify(${names})`));

  // live: they follow the code as it's written, a rename made elsewhere, a reference taken out
  await t.open(`#/p/${R}`);
  await addExpr(t, `Blocks([text("one"), text("two"), text("three"), text("four"), text(@${A}.title)])`);
  await t.until(`JSON.stringify(${names}) === '["alpha"]'`, 4000);
  await t.js(`[...document.querySelectorAll(".fw-doc .fw-expr")].at(-1).fwExpr.showCode()`);
  await t.until(`!!document.activeElement?.closest(".fw-expr-code")`, 2000);
  await setCode(t, `Blocks([text("one"), text("two"), text("three"), text("four"), text(@${A}.title ++ @${B}.title)])`);
  t.check("live: a reference written into its code, its tab there at once (the code still open)", await t.until(`JSON.stringify(${names}) === '["alpha","beta"]'`, 2000), await t.js(`JSON.stringify(${names})`));
  const other = await window2(t, `#/p/${B}`);
  await other.js(`(() => { const i = document.querySelector(".fw-title"); i.focus(); i.value = "gamma"; i.dispatchEvent(new Event("input", { bubbles: true })); i.blur(); return 1; })()`);
  t.check("  beta renamed in another window: its tab says the new name", await t.until(`JSON.stringify(${names}) === '["alpha","gamma"]'`, 5000), await t.js(`JSON.stringify(${names})`));
  other.close();
  await setCode(t, `Blocks([text("one"), text("two"), text("three"), text("four"), text(@${B}.title)])`);
  t.check("  a reference taken out: its tab goes", await t.until(`JSON.stringify(${names}) === '["gamma"]'`, 2000), await t.js(`JSON.stringify(${names})`));

  // from what its run reads, not what its code names: a branch not taken, no tab; every pericope (*), none
  await setCode(t, `Blocks([text("one"), text("two"), text("three"), text("four"), text(if true then @${T}.title else @${A}.title)])`);
  t.check("from what it reads: a branch not taken gives no tab", await t.until(`JSON.stringify(${names}) === '["fox"]'`, 2000), await t.js(`JSON.stringify(${names})`));
  await setCode(t, `Blocks([text("one"), text("two"), text("three"), text("four"), text(asText(wordCount(@${A})))])`);
  t.check("  what it reads through a quote: alpha, and beta that alpha quotes", await t.until(`JSON.stringify(${names}) === '["alpha","gamma"]'`, 2000), await t.js(`JSON.stringify(${names})`));
  await setCode(t, `length(pericopes)`);
  t.check("  every pericope read (*): no tabs", await t.until(`JSON.stringify(${names}) === '[]'`, 2000), await t.js(`JSON.stringify(${names})`));
  // a block of text's inline expressions give it tabs too, while the caret's in it
  await t.open(`#/p/${N}`);
  await t.select("after the quotes", { collapse: true });
  await t.type(" ");
  await t.type("$");
  await t.type(`wordCount(@${T}) + wordCount(@${B})`);
  await t.type("$");
  await t.settle();
  const inames = `[...(document.querySelector(".fw-doc .fw-text.fw-here > .fw-ideps")?.querySelectorAll(".fw-dep-name") || [])].map((x) => x.textContent)`;
  t.check("  inline: the block's tabs, from what its expressions read, in the code's order", await t.until(`JSON.stringify(${inames}) === '["fox","gamma"]'`, 4000),
    await t.js(`JSON.stringify(${inames}) + " " + document.querySelector(".fw-doc .fw-here")?.outerHTML.slice(0, 300)`));
  t.check("  shown, under nothing: visible", await t.js(`document.querySelector(".fw-doc .fw-text.fw-here > .fw-ideps .fw-dep").getBoundingClientRect().width > 0`));

  // every right-side reference tab grows out with its name when hovered: a quote's ↗ too
  await t.open(`#/p/${A}`);
  const go = `document.querySelector(".fw-doc .fw-quote > .fw-top > .fw-open")`;
  const at = await t.js(`(() => { const b = ${go}.getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2]; })()`);
  await t.hover(at[0], at[1]);
  await sleep(300);
  t.check("a quote's ↗ hovered: the name of what it opens (beta, renamed gamma above), grown out to the right", await t.until(`(() => { const n = ${go}.querySelector(".fw-open-name");
    return n?.textContent === "gamma" && n.getBoundingClientRect().width > 20 && n.getBoundingClientRect().left >= ${go}.getBoundingClientRect().right - 2; })()`, 2000),
    await t.js(`(() => { const n = ${go}.querySelector(".fw-open-name"); return n ? n.textContent + " " + n.getBoundingClientRect().width : "none"; })()`));
  await sleep(400);
  t.check("  its name's box on the tab's own line, top and bottom (one shape)", await t.js(`(() => { const g = ${go}.getBoundingClientRect(), n = ${go}.querySelector(".fw-open-name").getBoundingClientRect();
    return Math.abs(n.top - (g.top - 1)) < 0.6 && Math.abs(n.bottom - (g.bottom + 1)) < 0.6 && Math.abs(n.left - g.right) < 0.6; })()`),
    await t.js(`JSON.stringify([${go}.getBoundingClientRect(), ${go}.querySelector(".fw-open-name").getBoundingClientRect()])`));
  t.check("  hovered, at full strength (not the faint tab at rest), its row too", await t.js(`getComputedStyle(${go}).opacity === "1" && getComputedStyle(${go}.parentElement).opacity === "1"`),
    await t.js(`getComputedStyle(${go}).opacity + " " + getComputedStyle(${go}.parentElement).opacity`));
  await t.shot("quote-hover.png", { x: Math.round(at[0]) - 400, y: Math.round(at[1]) - 40, width: 560, height: 90, scale: 2 });
};

scenarios.evalcache = async (t) => {   // a value worked out again only when something it read changed
  await t.open(`#/p/${R}`);
  await addExpr(t, `wordCount(@${T})`);
  await addExpr(t, `wordCount(this)`);
  await t.until(`/^[0-9]+$/.test([...document.querySelectorAll(".fw-doc .fw-expr > .fw-expr-out")].at(-1)?.textContent || "")`, 6000);
  await t.select("r words", { collapse: true });
  await t.settle();
  await t.js(`globalThis.fwRuns = []; 1`);
  await t.type(" and more");
  await t.settle();
  const runs = await t.js(`globalThis.fwRuns || []`);
  t.check("typing here: wordCount(this) worked out again (it reads this pericope)", runs.includes("wordCount(this)"), JSON.stringify(runs));
  t.check("  wordCount(@fox) not (it reads only fox)", !runs.some((x) => x.includes(`@${T}`)), JSON.stringify(runs));
  t.check("  and still right: this pericope's words now", await t.until(`+[...document.querySelectorAll(".fw-doc .fw-expr > .fw-expr-out")].at(-1).textContent >= 4`, 3000));
  const other = await window2(t, `#/p/${T}`);
  await t.js(`globalThis.fwRuns = []; 1`);
  const was = await t.js(`[...document.querySelectorAll(".fw-doc .fw-expr > .fw-expr-out")].at(-2).textContent`);
  await other.select("the quick brown fox", { collapse: true });
  await other.type(" leaps");
  const fox = `[...document.querySelectorAll(".fw-doc .fw-expr > .fw-expr-out")].at(-2)?.textContent`;
  t.check("fox written in another window: wordCount(@fox) follows, from a patch of just what changed (the store not read whole)", await t.until(`${fox} === String(+${JSON.stringify(was)} + 1)`, 5000)
    && !(await t.js(`globalThis.fwRuns || []`)).some((x) => x.startsWith("(read whole")), JSON.stringify(await t.js(`[${fox}, globalThis.fwRuns]`)));
  const runs2 = await t.js(`globalThis.fwRuns || []`);
  t.check("  wordCount(this) worked out again too: this pericope quotes fox, so its words changed", runs2.includes("wordCount(this)"), JSON.stringify(runs2));
  other.close();
};

scenarios.exprleave = async (t) => {   // ↓ out of an expression: nothing of it lit any more, its ƒ tab included
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

scenarios.perspective = async (t) => {   // this, here, self: here is where it's viewed from
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

scenarios.casting = async (t) => {   // automatic casting (TYPE.md "Casting"): what a place wants, a value cast to it
  await t.open(`#/p/${B}`);
  await addExpr(t, `text(created(@${A}))`);
  t.check("text(created(@alpha)): a Date where text is wanted, cast (as fw writes dates)", await t.until(`${lastOut}?.querySelector(".fw-text")?.textContent === "Oct 1, 2026, 10:00 am"`, 8000),
    await t.js(`${lastOut}?.textContent`));
  await addExpr(t, `wordCount(@${A}) ++ " words"`);
  t.check("wordCount(@alpha) ++ \" words\": a number where text is wanted, cast; its words, no quotes", await t.until(`/^[0-9]+ words$/.test(${lastOut}?.textContent || "")`, 4000),
    await t.js(`${lastOut}?.textContent`));
  t.check("  the cast said: in its tooltip", await t.js(`${lastOut}.title`).then((x) => /cast: Int → String \(asText\)/.test(x || "")), await t.js(`${lastOut}.title`));
  await t.js(`[...document.querySelectorAll(".fw-doc .fw-expr")].at(-1).fwExpr.showCode()`);
  t.check("  and under its code while it's open", await t.until(`[...document.querySelectorAll(".fw-expr-cast")].some((x) => x.textContent === "asText: Int → String")`, 2000),
    await t.js(`document.querySelector(".fw-expr-errors")?.textContent`));
  await t.key("x", 4 | 8);
  await t.until(`!document.querySelector(".fw-expr-code")`, 2000);
  await t.settle();
  await addExpr(t, `"see " ++ @${A}`);
  t.check("a reference where text is wanted: its title", await t.until(`${lastOut}?.textContent === "see alpha"`, 4000), await t.js(`${lastOut}?.textContent`));
  await addExpr(t, `Blocks([@${A}, text("after")])`);
  t.check("a reference where a block is wanted: its window (body)", await t.until(`!!${lastOut}?.querySelector(".fw-from") && ${lastOut}.textContent.includes("after")`, 4000),
    await t.js(`${lastOut}?.textContent`));
  await addExpr(t, `wordCount("x")`);
  t.check("a mismatch fw has no way across: still Hazel's error, never a wrong value", await t.until(`${lastOut}?.classList.contains("fw-expr-holes")`, 4000),
    await t.js(`${lastOut}?.className + " " + ${lastOut}?.textContent`));
  await t.select("beta's words", { collapse: true });
  await t.type(" ");
  await t.type("$");
  await t.type(`wordCount(@${A}) ++ " w"`);
  await t.type("$");
  const inl = `[...document.querySelectorAll(".fw-doc .fw-icode-out")].at(-1)`;
  t.check("inline: cast the same way, its words in the line", await t.until(`/^[0-9]+ w$/.test(${inl}?.textContent || "")`, 3000), await t.js(`${inl}?.textContent`));
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
  await step("  this, in a call: the quote, where it sits (its pericope: caller)", "title(pericopeOf(this))", "caller");   // (a String: its words, TYPE.md "Casting")
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

scenarios.backslash = async (t) => {   // a backslash written just before an inline expression: kept a backslash, the expression still one
  await t.open(`#/p/${B}`);
  await t.select("beta's words", { collapse: true });
  await t.type(" ab");
  await t.type("$");
  await t.type("1 + 1");
  await t.type("$");
  await t.type(" c:\\dir");
  await t.select(" ab", { collapse: true });
  await t.type("\\");
  await t.settle();
  const b1 = (await t.kids(B))[0].text;
  t.check("stored with the backslash before it doubled; one elsewhere as written", b1 === "beta's words ab\\\\$1 + 1$ c:\\dir", b1);
  await t.open(`#/p/${A}`);
  await t.open(`#/p/${B}`);
  const line = `document.querySelector(".fw-doc .fw-text")?.innerText`;
  t.check("  read back: the backslash, then its value", await t.until(`${line}?.replace(/[ƒ$]/g, "") === "beta's words ab\\\\2 c:\\\\dir"`, 4000), await t.js(line));
};
