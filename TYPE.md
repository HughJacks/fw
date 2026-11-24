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
  Hazel's type error (automatic casting, agreed, isn't built yet).
- An expression read through `body` has its own above and below (where it sits), not the reader's.
- `this` (the expression block itself) is for later.
- The page keeps an empty block after a pericope's last block, so an expression at the end has an empty block below,
  not a hole.

Agreed with it, not built yet: automatic casting (the result first, then arguments), and identity all the way down
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
