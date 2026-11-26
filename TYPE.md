# fw's type (agreed 2026-11-23)

The user: "what is a block? the main data type is a pericope, which is a recursive option type so lets clarify that …
we just want to make the type as clear as possible." Confirmed: "this is correct".

The theory first, for fw as an extension of Hazel. Nothing is built from this yet.

```
Pericope = {                      -- the whole: identity, facts, a body; the only thing with a page of its own
  id       : Id,
  title    : String?,
  created, updated, visits,
  kinds    : {Kind → Bool},       -- the user's answers (only a pericope has them)
  role     : Plain | Kind(name),  -- a kind is a pericope with a name
  body     : Body
}

Body =
  | Picture(File)                 -- a picture is always a pericope of its own
  | Blocks([Block])               -- everything else: a sequence of blocks

Block = { id : Id, created, updated, case : Case }   -- a part; every part has an id

Case =
  | Text(String, links : [Link])  -- base case
  | Expr(Source)                  -- base case in the store; its value is a shown Block
  | Quote(Ref, Mask?)             -- base case: points into the graph
  | Paraphrase(Ref, String)       -- base case: points, plus the user's words
  | Blocks([Block])               -- the one recursive case (⌘↵)

Ref  = Id                         -- any pericope or block
Link = { to : Ref, at : (start, end) }
```

- **Two levels.** "Pericope" is the whole; "block" is always a part, never the whole.
- **Two recursions.** The tree: `Blocks` in `Blocks`, finite, one parent each. The graph: `Quote`, `Paraphrase` and
  links, shared, may cycle, followed lazily to a depth limit.
- **Stored vs shown.** Shown `Case` = stored `Case` with each `Expr` replaced by its value. The header names the shown
  type: one `Text` → "text", one `Quote` → "quote", several → "pericope", a picture → "picture", one `Expr` → its value's.
- **No subtyping** (Hazel has none): sums and records only.

## Live: the rule (the user, 2026-11-25)

"this is the rule not a hard coded in anyway, this is the point of hazel, and the point of loro … all other forms of
dependence and linking follow this."

**What's written is the only source; everything else is a function of it, kept current wherever it's seen.**

- **Sources** are what someone wrote: a block's text, its links, an expression's source, a quote's target and mask,
  titles, tags answered. They live once, in the store.
- **Everything else is derived**, never a second copy: what a quote shows, an expression's value, backlinks, a
  pericope's type, word counts, a quote's top line, a tag's members, search and home's order.
- **Never stale.** When a source changes, anywhere (this window, another window, the other machine, a friend later),
  every view depending on it follows, including the one you're in, with your caret carried along.
- **Never refused.** Two writers at once are merged, not turned away. A write is made on what its writer saw and merged
  with everything since.
- **Never meaningless.** A view of something missing, cyclic, too deep or unfinished shows that (a hole, ↻, ⋯), never
  an error or a stale copy.

Hazel and Loro are the two halves of this rule. They meet only at the store.

| | Hazel | Loro |
|---|---|---|
| live in | computation: what a source *means* | time and place: who wrote what, where, when |
| its promise | every program state has a meaning and a value (holes) | every replica converges; every edit is kept (no conflicts) |
| in fw | every view is a function of the store, total, recomputed on change | the store: one document, every writer a peer, writes merged |

Neither knows about the other. Loro says what the store holds now, and Hazel-style evaluation says what that means
wherever it's shown. So a new kind of dependence (a new view, a new link, a new built-in) gets liveness by being a
function of the store. A new kind of writer (a window, another machine, a friend) gets merging by being a Loro peer. Nothing
is special-cased.

How far the code is there: the rule holds today and is enforced by tests (e2e `live`). In the
code, the page hears of every change one way (`web/src/live.js`: the core pushes the store's stamp, GET
/api/live), and each view refetches what it shows; not yet each view saying what it reads, and the core still
rereads the whole store per request.

**There is no "saved"** (the user, 2026-11-26: "the idea of SAVED is not real, we are always saving every keystroke,
just like hazel every editor state is meaningful"). What the page holds is what's written, now; the core's word on it
follows a moment later, never a state you wait in. Nothing is drawn or described as unsaved; facts about a block
just written are the page's own until the core's arrive (`liveFacts`); a core that doesn't answer is said as that
("your writing is here, and goes through when it does"), not as something unsaved.

## Projection: `x.f` as sugar (agreed 2026-11-25, built 2026-11-26)

The user: "because this is simultaneously a live code notebook and a personal database, they sort of ARE fields, so i
think we should lean on the syntactic sugar method". `x.f` is written for `f(x)`, for any function (fw's and your
own), rewritten before typing, never resolved by x's type: so a hole stays meaningful (`?.wordCount` is
`wordCount(?)`), no overloading. `@p.wordCount + @p2.wordCount`, `@p.title.length`. Against it, weighed: it reads as
stored data when facts are computed (and depend on `here`); two ways to write the same thing; a clash if pericopes
ever get labelled fields. Pays off once completion after the dot lists what can be projected (the code-writing
experience).

Built (2026-11-26): rewritten on the parsed term, in the bridge's `run_source` before typing (and before casting,
which then sees `f(x)`), not as a text rewrite: Hazel's own parser has already found x there (its precedence: `@p.
wordCount + 1` is `(wordCount(@p)) + 1`; `@p.title.length` a chain), and Hazel already reads `.` as a labeled tuple's
projection, `Dot(x, Label(f))`. Lexical, not by type: rewritten when f is a function in scope (fw's or Hazel's
built-ins, or a name the code binds); anything else stays Hazel's label projection (`(a=1, b=2).b` is 2). Arguments by
Hazel's convention, a function of several taking one tuple: `x.f(a, b)` is `f((x, a, b))`, `x.f()` is `f(x)`. A
number's dot is a number (`1.5`; `21.double` doesn't tokenize: `(21).double`). After a dot, completion lists the
functions whose first argument fits x's type first (its static type, asked of the engine: a hole has one), then the
rest: in the code box (CodeMirror's list, Tab takes it) and in an inline expression's open code (the / menu's list at
the dot, ↑/↓, Enter or Tab, Esc); `web/src/projections.js`.

## Casting (built 2026-11-26)

The user: "a broad approach to autocasting for our context … these are first hazel problems then UI ones". Agreed
earlier: the result first, then arguments.

- **Arguments (and anywhere a type is wanted):** after Hazel's checker runs, wherever it finds a value of one type where
  another is wanted (its `ExpectationMismatch`) and fw knows the way, the term is wrapped in an ordinary call and the
  program checked again (a few rounds: one cast can make the next checkable). The casts are functions you could write
  yourself, so nothing is hidden:

  | from → to | cast | gives |
  |---|---|---|
  | Int, Float, Bool → String | `asText` | its digits, `true` |
  | Date → String | `asText` | as fw writes dates: "Nov 25, 2026, 3:12 pm" |
  | Ref → String | `asText` | its title |
  | a list → String | `asText` | its things as text, commas between |
  | String → Block | `text` | a block of text |
  | Ref → Block | `body` | its window |
  | Int, Float, Bool, Date, a list → Block | `asBlock` | a list its things as blocks, the rest its text in a block |

  So `text(created(@x))`, `wordCount(@x) ++ " words"`, `"see " ++ @x`, `Blocks([@x, text("…")])` just work.
- **The result** (what the place wants): an expression block shows blocks, or anything else as its text; an inline
  expression only text (blocks there are `!`). A String or a Date shows as its words, never its quotes.
- **Holes stay holes:** a hole's type is unknown, which is never a mismatch, so it's never cast (`wordCount(@x) ++ ?`
  is `"12" ++ ?`); a cast given a hole gives a hole. A mismatch fw has no way across (`wordCount("x")`, a String where
  a Ref is wanted) stays Hazel's error.
- **Visible:** every run reports the casts it put in (`casts: [{cast, from, to}]`); the page says them in a value's
  tooltip and, while the code is open, under it ("⤷ asText: Int → String").
- Not cast (yet): branches of differing types (`if … then 3 else "x"`), an Option (`firstVisit`), tuples.

## Inline: mentions and inline expressions (agreed 2026-11-25; inline expressions built the same day)

Text is `[Inline]`; two new cases, the same ideas as a quote and an expression block one level down:

```
Inline = + Plain(String) + Link(String, Ref)
         + Code(source)      -- $ 5 + 5 $ in text: drawn as its value, live
```

`@` in text is sugar for `$ @p $` (the user, 2026-11-25): an inline expression whose value is a Ref, drawn as the grey
chip a Ref is; no Mention case of its own. A link keeps your words and stays separate.

**The ƒ marks computation** (the user, 2026-11-25: "if we @ insert a reference it shouldnt have an F until we explode
it to treat it as a formula … we need to make things consistent"): a bare reference (`$@p$`) computes nothing, so
no ƒ; opened (⌘⇧X) and made more than a reference (`wordCount(@p)`), it computes, and carries its ƒ. One rule
everywhere: ⌘O on a thing selected opens what its value is (a reference's pericope, a window's source), never what
its code reads; ⌘⇧X shows the code, references drawn as their titles there; `@` in code (the code box, an inline
expression's open code) opens fw's search and puts the reference in the code.

**Editing an inline expression** (the user, 2026-11-25: "insert 2 green dollar signs in the text and we type between
them … cursor out of the dollar signs like normal, and the result should just be in mono and highlighted green"): it's
text. `$` in a line puts two dollar signs (green) with the caret between; what's typed between them is code (mono,
coloured as code, references drawn as their titles); with the caret anywhere else its code folds away and its value
shows, mono and green, a reference green with a small ↗. Closed, the caret crosses it in three stops (the user,
2026-11-25): before it, it selected (lit, the caret hidden; a click lands here too), after it; never opening it.
Only a key opens it (⌘⇧X, selected or against it; typing `$` opens the new one); the closing `$`, Esc, ⌘⇧X or the
caret leaving close it. ⌫ takes it whole; left empty, it goes. Its closing `$` stays in the line but takes no room, so
the caret after it is drawn after its value. In the editor it's text marked as code (the `icode` mark, inlinecode.js), so
pasting `$…$` makes code too and copying gives the `$…$` back. An expression block keeps its code box (⌘⇧X).

- `$` at the start of an empty block makes it an expression block (its code box open); mid-text, `$ … $` is an inline
  expression; `\$` is a literal dollar sign.
- **An inline expression's value must be inline**: text, or anything cast to text (a number, a date, a list, a
  chip). A value of blocks draws as `!` with a note saying blocks can't sit in a line (the user: "having the visual
  blocks stray from data blocks will cause problems"). Drawn boxes stay one to one with written blocks for now.
  Talked through, put aside: a written block drawn as several boxes (its value), the pieces addressed as spans;
  "eventually we might not need this kind of thing".
- **Stored in the text itself** (the user chose it, 2026-11-25): a block of text is a string with code spliced in,
  `the train $wordCount(@x)$ arrives`, string interpolation. `$…$` closed on its line is code; `\$` a dollar sign, and
  so is a `$` with no partner on its line (the store's two old dollars stayed text, no migration). Every character
  merges through Loro as now; no schema change; the terminal and search see the code as text. An inline
  expression is a span of its block (addressed by position), not its own id. Worked out where its block sits (`self`
  is the block: `this` its pericope, `above`/`below` its peers). Its @references are backlinks; a title reads it with
  references named (fw_block.readable).
- **In the engine** (2026-11-25): a text's `$…$` is worked out while the text is shown, where its block sits, and
  its value goes into the line as ordinary Inlines, so what a block shows is a value (no Code case in `Inline`): a
  Ref as `Link(title, ref)` (it stays a reference), a string its words, anything else as fw prints it (a list its
  things, a Ref in it its title, a date pretty), blocks `!`, a hole `?`. Adjacent plain words are one `Plain`, so
  `Text([Plain(s)])` still matches. Words count what's shown; a block counting itself (its code reading its own
  block, `wordCount(this)` inside it) leaves its inline expressions out, the recursive case. A value's text is
  handed to the page with each `$` as `\$`, so a value is never read as code again. The core's stored count (it
  can't run Hazel) counts each inline expression as one word, never its code.
- Masks stay spans of someone else's text: a sealed `Span` (Loro cursors), `mask(body(@x), [spans])`.

## Right-side tabs: the rule (2026-11-26)

The user: "for stacked tabs … we need a clear rule"; "the borders should match … showing the name is enough of a hover
state"; "it doesnt need to show here while inactive … there will be many cases where there isnt enough space".

1. Every right-side tab is the same square: 1.2rem, its 1px line just outside it (the ƒ, a quote's and a paraphrase's
   ↗, a dependency's ↗).
2. One primary tab per block (its ƒ, or its ↗), joined to the block by its line, there at rest (faint).
3. Its dependency tabs only while the block is active, stacked under the primary, not joined.
4. Room: from under the primary down to where the next block's primary tab sits (at the page's end, all of them); what
   doesn't fit is a last "+n" slot, a click listing the rest (titles only).
5. Hovering only reveals the name, in a box on the tab's own line (one shape), cut at about 20 characters with "…".
6. One tab lit at a time: the one ⌘O opens (the user: "it needs to be clear when we use command O what we are
   targeting"). Two looks only, never a third (the user: "there should be only one" inactive state): at rest (faint,
   no line) or lit (its line; filled when selected whole). A dependency is opened by a click, never ⌘O, so it's never
   lit: it looks as any tab at rest, its arrow ↙ (this draws from that), where a reference's ↗ is this points to that.
   A quote's ↗ while an expression inside it is selected: at rest, though its row is bright. Hovered, any tab: its line
   and its name.

## Every fact typed (built 2026-11-25)

The user: "all meta data should be well typed in hazel and should have functions"; a block's facts are its own (the
same function means the same thing at every level). On dates: "in the spirit of our auto casting everything should
try to be pretty".

```
title : Ref -> String            writtenTitle : Ref -> Option(String)
created, updated : Ref -> Date   now : Date
visits : Ref -> Int              firstVisit, lastVisit : Ref -> Option(Date)     recentVisits : Ref -> [Visit]
tags, notTags : Ref -> [Ref]     isPericope : Ref -> Bool    pericopeOf : Ref -> Ref    backlinks : Ref -> [Ref]
Date   sealed (only fw makes one), drawn "Nov 25, 2026, 3:12 pm"; year, month, day, hour, minute, weekday,
       showDate, before, daysBetween, minutesBetween
Visit  = + Visit((Date, [Attention]))     Attention = + Opened + Stayed + Wrote + Through
```

Printed values: a list is its things with commas between ("nothing" when empty), a Ref a chip with its title.

## Changes from schema v19/v20

1. Kind leaves the content cases: a pericope's `role`.
2. A picture is only a pericope's body (already enforced: `pictures_apart`).
3. A paraphrase is only a block inside (already enforced).
4. A bare-string pericope becomes `Blocks([Text])`.

## What opens on its own page

Only a pericope opens. A picture opens because a picture is always a pericope, not because it's a base case.

- Pictures are made pericopes **eagerly**: when one is added, it becomes a pericope at once, and where it sits there's a
  `Quote` of it.
- Text, expressions and containers are made pericopes **lazily**: when you pop one out, or quote a block from the search,
  it's promoted then, and a `Quote` is left in its place.

Why pictures are eager: a picture has nothing to write in, so the only thing a holder ever does with one is show it
whole, which is exactly a quote. Its title (a model's picture titles, when there are any), its kinds and its backlinks only make sense on a
pericope. Text is where you write, so it stays a block until you ask for it to stand alone.

So the rule is one rule: **an open page is a pericope; anything shown whole elsewhere is a `Quote` of it.** Opening a
block inside a pericope (⌘O on a quote, or inside one) goes to the pericope it's in, at that block.

## As Hazel

See "Every block in the dialect" below: Hazel's `Block` (with `From`), `Ref`, and the store's lookups as fw built-ins.

## References in an expression (agreed 2026-11-23; theory, not to be built yet)

The user: "yes, but we dont need to build this part yet"; then agreed to each point below.

1. **Written by id, drawn as the title.** The source holds `@<id>` (renames never break it); the code view draws it as
   the pericope's title, as a link is stored by id and shown as words. Made like a link: `@`, search, pick.
2. **A reference is a `Ref`, not its content.** `@x : Ref`. Content is asked for with fw built-ins:
   ```
   body    : Ref -> Block       -- From(@x, what x shows): its own Exprs evaluated (see the dialect below)
   title   : Ref -> String
   tags    : Ref -> [Ref]       -- a tag is a pericope, so a Ref (the store's kinds: called tags, 2026-11-24)
   tagged  : Ref -> [Ref]       -- a tag's pericopes
   pericopes : [Ref]            -- every pericope (`all` is Hazel's own)
   wordCount : Ref -> Int       -- as the header counts them, live
   created, updated : Ref -> String   -- ISO 8601 (Hazel has no dates)
   visits  : Ref -> Int
   backlinks : Ref -> [Ref]     -- the pericopes pointing at it
   ```
   A block's facts (title, kinds, created, …) are its pericope's (the user, 2026-11-24: "we need to be able to access
   all pericopes meta data, for example wordCount(@pericope)").
   (Superseded 2026-11-24: `body(@x)` keeps identity through `From`; a value computed from it has none. See below.)
3. **"Every pericope in scope"** means reachable (by `@`, `all`, `members`), not a variable per pericope. Names you
   bind are Hazel's `let`.
4. **Expressions reading expressions.** `body(@x)` evaluates x's Exprs first. A cycle's closing read is a hole drawn ↻;
   depth limited as quotes are.
5. **Live.** An expression is a pure function of the store: the Refs it reads are recorded, and a change to any of them
   reruns it at once. Its value is never stored.
6. **Backlinks.** Any Ref in an expression's source is a backlink of its target: computing over a pericope counts, not
   only quoting it (the user's call).
7. **Deleted targets.** A Ref to a deleted pericope is a hole ("this pericope was deleted"); the id stays in the source,
   so undoing the delete brings it back.

## Expressions are self-contained (2026-11-24)

The user: "i think we should walk this back a bit do expressions are completely contained withing an expression block,
this removes application".

An expression is a whole program inside its one block. Functions are defined and applied inside it, with Hazel's own
`fun` and `let`. No block is applied to another block. `Apply(Block, [Block])` was built in a day
(2026-11-23) and then taken out; schema v21 turns any Apply left into a plain container of its blocks. `@` references
inside an expression's code stay.

## Every block in the dialect (agreed 2026-11-24; theory, not built yet)

**Where this is going** (the user, 2026-11-25): "the goal is eventually to basically have our entire store written in
our extended version of hazel (or elm ig), and how our editor use hazel and render and write to those programs". The
store is one program; showing a pericope is evaluating it; writing in the editor is editing that program (as Hazel's
structure editor does), never a separate data model with a language beside it. Every step (typed facts, `this`, Loop,
calls, windows) should move toward that, not around it. Not to be built in one go: think, then build in steps.

Agreed (2026-11-25, talking it through): **the program holds what's written**; what fw observes (created, updated,
visits, backlinks) stays beside it, read through the typed functions, so a visit never rewrites the program. Later
(the user: "i would like to be able to reference anything visible but i dont think we need this now"): a way to refer
to anything on screen; the suggestions below a pericope stay apart from the program.

Agreed (2026-11-25): **every block has its name in the program** (`@b1 = …`), always there and never shown, as ids
are now. The user: "if we pop something out it should already have an id ready for it": turning a block into a
pericope of its own, quoting it, linking to it never has to invent identity, it's already written.

The user: "a quote is just syntactic sugar for a referencing and calling body on that reference, we should rewrite it
that way, and we should i think treat equivalent results with the same treatment"; "what im sure of is that other
blocks need to be written in our dialect of hazel"; then, of the proposal below, "okay i trust you, lets go ahead".

**Every block is an expression.** A text block is a literal, a quote is `body(@x)`, an expression block is code written
by hand. What the store keeps per case (Text, Quote, Paraphrase, Blocks, Expr) is that expression's normal form.

### Hazel's Block

```
Block =
  + Text([Inline])              -- your words; Inline = + Plain(String) + Link(String, Ref): links survive computation
  + Paraphrase(Ref, String)     -- points, plus your words
  + Blocks([Block])             -- the one recursive case
  + From(Ref, Block)            -- these blocks came from that pericope or block, unchanged: identity kept

body    : Ref -> Block          -- body(@x) = From(@x, what x shows)
mask    : (Block, Mask) -> Block   -- narrows a From (only ever narrows); Mask is opaque, made in the masking view
text    : String -> Block       -- text("hi") = Text([Plain("hi")])
origin  : Block -> Option(Ref)  -- where a block came from, if it's a From
content : Block -> Block        -- what a From holds (anything else: itself)
```

- **`From` replaces `Quote(Ref)`** as the one case carrying identity, and `body(@x)` is how a quote is written (no
  `Quote` constructor: one way to say it).
- **`From` is sealed**, as `Ref` is: its constructor isn't in the context. Only `body` makes one and `mask` narrows one,
  so a `From` always tells the truth (no forged quote: other words shown under a pericope's ↗, its backlinks, its ⌘O).
  It's read with `origin` and `content`, never built by hand.
- Anything computed from a source (`text(title(p))`, a filtered list) is a new block with no `From`: a changed copy
  isn't the original, so it doesn't open.

### Each block written out

```
pericope { title = "South Station", kinds = [@poem], body = [ … ] }   -- title left out: from the first line
pericope { role = Kind("poem"), body = [ … ] }                        -- a kind: its body is its description

"Hi Liam,"                                                 -- text (sugar for Text([Plain("Hi Liam,")]))
Text([Plain("see "), Link("South Station", @f4f0)])        -- text with a link
Blocks(["first thought", "second thought"])                -- a container (⌘↵)
body(@f4f0)                                                -- a quote
mask(body(@f4f0), ⟨mask⟩)                                  -- a masked quote
Paraphrase(@f4f0, "a poem about waiting in a station")     -- a paraphrase
picture("ab12cd.jpg")                                      -- a picture: only a pericope's body
body(@pic)                                                 -- a picture anywhere else (a quote of its pericope)
Blocks(map(tagged(@poem), body))                          -- an expression: each poem, each openable
```

Outside the expression, as attributes of the block: its id, dates and visits, a quote's top line (`show`) and its lock.
They say how a block is held and seen, not what it is.

### Equal results, equal treatment; colour says who wrote it

- A stored quote and a hand-written `body(@x)` are the same value, `From(@x, …)`. Both get the ↗, ⌘O, a tab of their
  own and a place in x's backlinks, at any depth in a result.
- **Red: a quote. Green: written by hand.** That's the only difference.

### Opening: if you can reference it, you can open it

⌘O acts on what's selected:

| selected | ⌘O opens |
|---|---|
| a block inside a result that is a `From(@x, …)` | x, at that block |
| the expression, its value one `From(@x, …)` | x |
| the expression, several references in its source (including ones only computed over, `wordCount(@a)`) | a short list of them to pick from (as the backlinks list); one: opens it |
| a computed block (no `From`) | as the expression: its references |

So two references are never ambiguous: each `From` box opens its own source, and the expression as a whole offers its
references.

### By hand, the honest routes to links

| you want | you write |
|---|---|
| the thing itself, openable | `body(@x)` |
| words pointing somewhere | `Text([Plain("see "), Link("South Station", @x)])` |
| each pericope with a tag, openable | `Blocks(map(tagged(@poem), body))` |
| your own words about it | `Paraphrase(@x, "my words")` |

### Later, noted (2026-11-24)

- **Writing through a result.** Eventually an evaluated expression should be written through, as a quote is (the user:
  "eventually we should have a way to write through an evaluated expression but for now lets not do that"). For now a
  result is block level only: moved through, selected, copied, never written in.
- **Re-presenting vs duplicating.** A result can hold existing blocks in two ways:
  - `body(@x)` re-presents x: a `From`, a window on x itself.
  - `content(body(@x))`, or anything computed from it, duplicates x's words into new blocks.

  Both are live (rerun whenever x changes), and they look nearly the same. That should be made clear on the page; how
  is undecided.

## Where an expression sits: above and below (built 2026-11-24)

The user: "i would like to be able to define an expression which uses above, below, and this to define where it sits
at the moment of viewing … maybe for now just use above and below limit it to only peer blocks".

```
above : Ref        -- the peer block just before this expression (same parent)
below : Ref        -- the peer block just after it
```

- **Live.** Worked out every time the expression is viewed, wherever the block is now. Moving the block changes them,
  and an edit to a neighbour reruns it on the key.
- **Peers only:** the blocks before and after it in the same container or pericope.
- **None there: a hole**, so `f(below)` is f applied to a hole and shows `?` where it can't finish. A wrong type is
  Hazel's type error, unless fw can cast it ("Casting").
- An expression read through `body` has its own above and below (where it sits), not the reader's.
- `this : Ref` (built 2026-11-25; the user: "this should be the current pericope, we dont need a word for self
  yet"): the pericope the expression is in, where it sits now (a call's: the quote's pericope). Read from inside, the
  expression's own place in it is the recursive case: `body(this)` shows the pericope with that place as its loop,
  and `wordCount(this)` counts everything but it ("render recursively as much as it can"). While it runs, the
  expression counts as being read, so nothing loops forever. `this`, `above` and `below` are drawn apart in the code
  (amber, outlined: relative to where it sits, worked out as it's viewed). A reference to the pericope it's in, in
  its code or in what it shows, is drawn as `this` too (the user: "any self referential references should render as
  'this'"); a reference to anything else it's seen through keeps its title, with ↻.
- **Three self-references** (built 2026-11-25; the user: "one to reference the pericope, one to reference the pericope
  where the expression is currently being viewed from, one to reference the block … two people can look at one value
  from two perspectives and the value is different"):
  - `this`: the pericope it's written in (lexical: wherever it's seen);
  - `here`: the pericope it's viewed from, the one open on the page; seen through a quote, the quoting one; in its own
    pericope, the same as `this`. Passed inward: an expression read through another has the reader's `here` (the
    person looking). No one looking (the core's counts, search, backlinks): `here` is `this`. Values were never stored,
    each page works its own out, so two windows on two pericopes see two values, both live; a cache would have to be
    per view;
  - `self`: the block itself (an expression block, an inline expression's block, a call's quote); read from inside,
    a loop (`body(self)`, `wordCount(self)` ↻).
  A reference to one of them is drawn as its word, in results and in code (`this` when `here` is `this`).
- **The recursive case** (the user, 2026-11-25: "if we are ever going to render a block while looking through it,
  that is the recursive case, so we render the title and a loop … in the case we render the reference while in the
  current pericope … we show this with a little loop"). A block met again while showing it is `Loop(@x)`, a sealed
  Block case (only fw makes one, as `From`): drawn as a dashed window on x, its title and ↻ (↗ still opens it).
  A printed `Ref` to anything the value is seen from inside (the expression, its pericope, every quote it's looked
  through) is a chip with ↻. Too deep (past the nesting cap) is still a hole.
- **Words of what's shown** (2026-11-25): an expression's words are the words of what it shows, worked out where it
  sits, so `wordCount` of a pericope counts its expressions' results. Counting from inside (`wordCount(this)`)
  counts everything but the expression itself (the user: "show 2": as much as can be worked out; the loop counts
  none). An expression's own words, asked for while it's being made (its id), are ↻.
- **What a word is** (2026-11-25; the user: count real words, "not hard code it, only … an elegant solution that
  applies to all situations"): a run without spaces with something in it besides punctuation (ASCII's, and the
  typographic dashes, quotes and dots). One rule wherever fw counts: the core (`fw_block.is_word`), the page's live
  count (`editor.js` `isWord`), the engine (`FwPrelude.is_word`). So an unfinished value's `31 + ?` is one word, a
  bullet `-` or a lone `—` none.
- **Runaway evaluation** (2026-11-25): Hazel allows recursion with no end; every run has a step budget (100,000 steps,
  ~75 ms: "a relatively short step limit", the user), and one that runs out shows "∞ ran too long", never freezing
  the page. Each expression read through another gets its own budget.
- The page keeps an empty block after a pericope's last block, so an expression at the end has an empty block below,
  not a hole.

Agreed with it, not built yet: identity all the way down
(`body` gives windows inside windows; a new block only when the words change).

## A quote of an expression is a call (built 2026-11-24)

The user: "quoting an expression gives a red quote block, then a green expression block, then a white block as a hole.
it should just be a red block which caries the result of the evaluated thing, the whole point of defining functions
like this is to allow them to work in this way … this is extremely important".

- A quote whose target is one expression (the expression block itself, or a pericope holding just it) **evaluates
  that expression where the quote sits**: its `above` and `below` are the quote's neighbours. Define `shout(above)`
  once, quote it anywhere, and each quote shouts what's above it.
- It's drawn as **one red quote box holding the result's blocks**, as any quote holds its target's: no green
  expression box, no code. It has a ↗ (⌘O opens the expression's own pericope), and you move through it at block level,
  not writing in it.
- In its own pericope the expression sits where it is (there, with nothing above it, `shout(above)` is `?`).
- In the engine: `shown(Quote)` of one expression is `From(target, the expression evaluated at the quote's id)`. The
  page draws it from the core's `expr` on the quote (`fw_web.quoted_expr`).
- An expression among other blocks in a quoted pericope keeps its own place there (that's re-presenting the pericope,
  not calling the expression).

## One block is unwrapped; the ƒ tab (built 2026-11-24)

The user: "an expression … after evaluating … should we wrap the evaluation in a green or should we unwrap it as simply
what it returns … stylistically i think unwrap … we need something which indicates to the user they can edit it"; "we
should always unwrap wrappings with just one block".

- **An expression is its result.** A value of one block is drawn as its holder's own box: an expression's in place
  (green), a call's (red), a window's. That block has no box or tab of its own, and nothing to go into: arrowing onto
  it selects the holder whole (the bright, filled state, with its neighbours' glow). Several blocks: the holder holds
  them, as a container does.
- **One container or window** is unwrapped too: Enter (or →, or the arrows) goes straight to its blocks, and ← comes
  straight back out, with no unseen level between.
- **The ƒ tab:** an expression's tab in the right margin, where link tabs go. It's faint at rest, drawn when you're on
  it, and filled when it's selected whole; a click on it, or ⌘⇧X, shows its code. Its number in the gutter is dim green,
  at rest too.
