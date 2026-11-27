import { A, A1, B, B1, K, M, QA, QM, QR1, R, R1, T, T1, storedIn } from "./fixture.mjs";

export const scenarios = {};

scenarios.typing = async (t) => {
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
};

scenarios.through = async (t) => {
  await t.open(`#/p/${A}`);
  await t.end();
  await t.key("ArrowUp");   // (from the block below it)
  t.check("edit-through: the arrow goes into the quote, not selecting it whole first", await t.until(`!!document.querySelector(".fw-quote.fw-in") && !document.querySelector(".fw-quote.ProseMirror-selectednode")`, 1000));
  await t.type(" and more");
  await t.settle();
  t.check("  typed there: saved into the quoted pericope", (await t.kids(B))[0].text === "beta's words and more");
  await t.key("Escape");
  t.check("  Esc: out a level, the quote selected whole (it shows one block: that block's box is the quote's)",
    await t.until(`!document.querySelector(".fw-quote.fw-in") && !!document.querySelector(".fw-quote.ProseMirror-selectednode")`, 1000));
  await t.key("Enter");
  t.check("  Enter on it (selected by Esc: block level): in a level, the caret at the end of its text",
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
};

scenarios.slash = async (t) => {
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
};

scenarios.actions = async (t) => {
  await t.open(`#/p/${A}@${A1}`);
  await t.select("first wo", { collapse: true });
  // where the cursor is: the text it's in, how far in, and whether that's inside a quote (a pop out kept it)
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
};

scenarios.links = async (t) => {
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
};

scenarios.blocks = async (t) => {
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
};

scenarios.paraphrase = async (t) => {
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
  t.check("  in the store, a block of its own (v18): {paraphrase, text}", JSON.stringify(stored) === JSON.stringify({ paraphrase: T, text: "a fox, quick" }), JSON.stringify(stored));
  // found in the search: never opened itself, its original is
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
};

scenarios.nesting = async (t) => {
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
};

scenarios.selectionQuote = async (t) => {
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
};

scenarios.clipboard = async (t) => {   // (headless Chrome has no system clipboard: real copy, cut and paste events, each with its own data)
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
};

scenarios.nestback = async (t) => {   // ⌘↵ then ⌫, over and over: never deeper (in a quote it nested forever)
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
