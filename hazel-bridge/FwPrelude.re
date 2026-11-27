/* FwPrelude: fw's context for Hazel (fw extends Hazel: fw-expr's TYPE.md).

   Two types:
     Ref    opaque: a pericope's or a block's id. Made only by `ref` (what `@<id>` in a source becomes) and by the
            built-ins below; its constructor isn't in the context, so a program can't take one apart or forge one
            except through `ref`.
     Inline = + Plain(String) + Link((String, Ref))      a text's words, and its links
     Block  = + Text([Inline]) + Paraphrase((Ref, String)) + Blocks([Block]) + From((Ref, Block)) + Loop(Ref)
            the shown block (fw-expr TYPE.md, "Every block in the dialect"): a quote is body(@x), a From, the blocks
            that came from x unchanged. From is sealed, as Ref is: its constructor isn't in the context, so only body
            makes one (no forged quote); origin and content read one. Loop(@x) is x met again while showing x (the
            user, 2026-11-25: "if we are ever going to render a block while looking through it, that is the recursive
            case, so we render the title and a loop"): sealed too, only fw makes one.

   Built-ins over a snapshot of the store, set per run by the bridge (src/fwbridge):
     ref     : String -> Ref
     body    : Ref -> Block        From(@x, what x shows): its own expressions evaluated (a cycle, or too deep: a hole)
     text    : String -> Block     Text([Plain(s)])
     origin  : Block -> Option(Ref)   where a From came from
     content : Block -> Block      what a From holds (anything else: itself)
     title   : Ref -> String
     pericopes : [Ref]             every pericope (TYPE.md's `all`: Hazel's List `all` has the name). Its value
                                   is the bridge's: bound in the env it evaluates with
     tagged  : Ref -> [Ref]        a tag's pericopes (the store's kinds: called tags, 2026-11-24)
     wordCount : Ref -> Int        its words, as the header counts them (live: from the snapshot's text)
     created, updated : Ref -> String   ISO 8601 (Hazel has no dates)
     visits  : Ref -> Int          how many times it's been visited
     backlinks : Ref -> [Ref]      the pericopes pointing at it
     tags    : Ref -> [Ref]        its tags (yes answers)
   Every fact is typed and its own (TYPE.md, "Every fact typed": a block's facts are the block's, the same function
   meaning the same thing at every level), read from the snapshot's `facts`:
     title : Ref -> String  ·  writtenTitle : Ref -> Option(String)
     created, updated : Ref -> Date  ·  now : Date
     visits : Ref -> Int  ·  firstVisit, lastVisit : Ref -> Option(Date)  ·  recentVisits : Ref -> [Visit]
     this : Ref (the pericope it's in, where it sits now; its own place in it, read from inside, is Loop)
     here : Ref (the pericope it's viewed from: the page's, passed inward; no one looking, this)
     self : Ref (the block itself; read from inside, Loop)
     tags, notTags : Ref -> [Ref]  ·  isPericope : Ref -> Bool  ·  pericopeOf : Ref -> Ref  ·  backlinks : Ref -> [Ref]
   Date is sealed, as Ref is (only fw makes one), drawn pretty ("Nov 25, 2026, 3:12 pm"), read with
     year, month, day, hour, minute, weekday (1 Monday … 7 Sunday) : Date -> Int  ·  showDate : Date -> String
     before : (Date, Date) -> Bool  ·  minutesBetween, daysBetween : (Date, Date) -> Int (the second less the first)
   Visit = + Visit((Date, [Attention])), Attention = + Opened + Stayed + Wrote + Through (how it was attended to).

   Nothing here parses or evaluates: the bridge hands in `eval_source` (haz3lcore's pipeline lives
   above this library). */

open BuiltinsUtil;
module Fresh = IdTagged.FreshGrammar;

/* --- the snapshot: fw's stored cases, as the page sends them ------------- */

type node = {
  id: string,
  case,
}
and case =
  | Text(string, list((string, int, int))) /* its text, and its links: (to, start, end) */
  | Quote(string)
  | Paraphrase(string, string)
  | Blocks(list(node))
  | Expr(string)
  | Picture(string)
  | Unknown;

type pericope = {
  pid: string,
  title: string,
  kinds: list(string),
  body: node,
  created: string, /* ISO 8601, as the store keeps it (Hazel has no dates) */
  updated: string,
  visits: int, /* how many times it's been visited */
  backlinks: list(string) /* the pericopes pointing at it (quotes, links, paraphrases) */
};

/* A block's own facts, as the core sends them (fw_web.snapshot_json): dates ISO 8601, as the store keeps them. */
type facts = {
  ftitle: string,
  written: option(string),
  fcreated: string,
  fupdated: string,
  fvisits: int,
  first: option(string),
  recent: list((string, string)), /* (when, how: o opened, c stayed, w wrote, q through a quote) */
  answers: list((string, bool)), /* its tags, as answered */
  fhome: string,
  entry: bool,
  fbacklinks: list(string),
};

type snapshot = {
  pericopes: list(pericope),
  facts: Stdlib.Hashtbl.t(string, facts), /* every block's own, by id */
  now: string,
  nodes: Stdlib.Hashtbl.t(string, node), /* every block and pericope body, by id */
  titles: Stdlib.Hashtbl.t(string, string),
  kinds_of: Stdlib.Hashtbl.t(string, list(string)),
  meta: Stdlib.Hashtbl.t(string, pericope), /* each pericope's facts, by its id */
  home: Stdlib.Hashtbl.t(string, string), /* a block's id -> its pericope's (a block's facts are its pericope's) */
  peers: Stdlib.Hashtbl.t(string, list(string)) /* a block's id -> its parent's blocks, in order (above, below) */
};

let empty_snapshot = (): snapshot => {
  pericopes: [],
  facts: Stdlib.Hashtbl.create(256),
  now: "",
  nodes: Stdlib.Hashtbl.create(64),
  titles: Stdlib.Hashtbl.create(64),
  kinds_of: Stdlib.Hashtbl.create(64),
  meta: Stdlib.Hashtbl.create(64),
  home: Stdlib.Hashtbl.create(256),
  peers: Stdlib.Hashtbl.create(256),
};

let snapshot: ref(snapshot) = ref(empty_snapshot());

/* What a run read (the page's cache: a value is worked out again only when something it read changed; 2026-11-26):
   each block, pericope or fact looked up, by id; "*" for the set of pericopes (every one, tagged); "now". Cleared by
   the bridge at each run's start; nested runs (an expression read through another) add to the outer one's. */
let reads: ref(list(string)) = ref([]);
let seen = (id: string) => reads := [id, ...reads^];
let look = (tbl, id: string) => {
  seen(id);
  Stdlib.Hashtbl.find_opt(tbl, id);
};

let make_snapshot = (pericopes: list(pericope)): snapshot => {
  let s = {...empty_snapshot(), pericopes};
  let rec index = (pid: string, n: node) => {
    if (!String.is_empty(n.id)) {
      Stdlib.Hashtbl.replace(s.nodes, n.id, n);
      Stdlib.Hashtbl.replace(s.home, n.id, pid);
    };
    switch (n.case) {
    | Blocks(kids) =>
      let ids = List.map(~f=(k: node) => k.id, kids);
      List.iter(~f=(k: node) => if (!String.is_empty(k.id)) { Stdlib.Hashtbl.replace(s.peers, k.id, ids) }, kids);
      List.iter(~f=index(pid), kids);
    | _ => ()
    };
  };
  List.iter(
    ~f=
      p => {
        index(p.pid, p.body);
        Stdlib.Hashtbl.replace(s.meta, p.pid, p);
        Stdlib.Hashtbl.replace(s.home, p.pid, p.pid);
        Stdlib.Hashtbl.replace(s.nodes, p.pid, {...p.body, id: p.pid});
        Stdlib.Hashtbl.replace(s.titles, p.pid, p.title);
        Stdlib.Hashtbl.replace(s.kinds_of, p.pid, p.kinds);
      },
    pericopes,
  );
  s;
};

/* --- the types ------------------------------------------------------------ */

let ref_t: Typ.t =
  BuiltinsADT.sum_type([("Ref", Some(Fresh.Typ.string()))]);
let ref_var: Typ.t = Fresh.Typ.var("Ref");
let block_var: Typ.t = Fresh.Typ.var("Block");
let inline_var: Typ.t = Fresh.Typ.var("Inline");
let inline_t: Typ.t =
  BuiltinsADT.sum_type([
    ("Plain", Some(Fresh.Typ.string())),
    ("Link", Some(Fresh.Typ.prod([Fresh.Typ.string(), ref_var]))),
  ]);
let block_t: Typ.t =
  Fresh.Typ.(
    rec_(
      Fresh.TPat.var("Block"),
      BuiltinsADT.sum_type([
        ("Text", Some(list(inline_var))),
        ("Paraphrase", Some(prod([ref_var, string()]))),
        ("Blocks", Some(list(block_var))),
        ("From", Some(prod([ref_var, block_var]))),
        ("Loop", Some(ref_var)),
      ]),
    )
  );

let date_t: Typ.t =
  BuiltinsADT.sum_type([("Date", Some(Fresh.Typ.string()))]);
let date_var: Typ.t = Fresh.Typ.var("Date");
let attention_t: Typ.t =
  BuiltinsADT.sum_type([("Opened", None), ("Stayed", None), ("Wrote", None), ("Through", None)]);
let attention_var: Typ.t = Fresh.Typ.var("Attention");
let visit_t: Typ.t =
  BuiltinsADT.sum_type([("Visit", Some(Fresh.Typ.prod([date_var, Fresh.Typ.list(attention_var)])))]);
let visit_var: Typ.t = Fresh.Typ.var("Visit");
let ctrs_of = (t: Typ.t) =>
  switch (Typ.term_of(t)) {
  | Sum(m) => m
  | _ => failwith("FwPrelude: a sum expected")
  };

/* Ref's constructor is left out of the context (opaque), and Block's From (sealed); Block's others and Inline's are in it. */
let constructor_entries: list(Ctx.entry) = {
  let ctrs =
    switch (Typ.term_of(block_t)) {
    | Rec(_, body) =>
      switch (Typ.term_of(body)) {
      | Sum(m) => m
      | _ => failwith("FwPrelude: Block must be a sum")
      }
    | _ => failwith("FwPrelude: Block must be recursive")
    };
  let open_ =
    List.filter(
      ~f=
        fun
        | ConstructorMap.Variant("From", _, _)
        | ConstructorMap.Variant("Loop", _, _) => false
        | _ => true,
      ctrs,
    );
  let inlines =
    switch (Typ.term_of(inline_t)) {
    | Sum(m) => m
    | _ => failwith("FwPrelude: Inline must be a sum")
    };
  Ctx.add_ctrs(Ctx.empty, "Block", open_).entries
  @ Ctx.add_ctrs(Ctx.empty, "Inline", inlines).entries
  @ Ctx.add_ctrs(Ctx.empty, "Attention", ctrs_of(attention_t)).entries
  @ Ctx.add_ctrs(Ctx.empty, "Visit", ctrs_of(visit_t)).entries
  @ [
    BuiltinsADT.create_type_alias("Date", date_t),
    BuiltinsADT.create_type_alias("Attention", attention_t),
    BuiltinsADT.create_type_alias("Visit", visit_t),
    BuiltinsADT.create_type_alias("Ref", ref_t),
    BuiltinsADT.create_type_alias("Inline", inline_t),
    BuiltinsADT.create_type_alias("Block", block_t),
  ];
};

/* --- values ---------------------------------------------------------------- */

let ctr = (name, arg_t) =>
  Fresh.Exp.constructor(name, Some(Some(Fresh.Typ.arrow(arg_t, block_t))));
let mk_ref = (id: string): DHExp.t =>
  Fresh.Exp.(
    ap(
      Forward,
      constructor(
        "Ref",
        Some(Some(Fresh.Typ.arrow(Fresh.Typ.string(), ref_t))),
      ),
      string(id),
    )
  );
let inline_ctr = (name, arg_t) =>
  Fresh.Exp.constructor(name, Some(Some(Fresh.Typ.arrow(arg_t, inline_t))));
let plain = s => Fresh.Exp.(ap(Forward, inline_ctr("Plain", Fresh.Typ.string()), string(s)));
let link = (s, id) =>
  Fresh.Exp.(
    ap(
      Forward,
      inline_ctr("Link", Fresh.Typ.prod([Fresh.Typ.string(), ref_t])),
      tuple([string(s), mk_ref(id)]),
    )
  );
let text_of_inlines = (l: list(DHExp.t)) =>
  Fresh.Exp.(ap(Forward, ctr("Text", Fresh.Typ.list(inline_t)), list_lit(l)));
let text = s => text_of_inlines([plain(s)]);
/* A stored text's inline expressions (TYPE.md "Inline": a text is a string with code spliced in), as web/src/draft.js
   `units` reads them: `$…$` closed on its line is code; `\$` a dollar sign, and so is a `$` with no partner on its
   line. Each unit (from, to, what), offsets into the stored text. */
type text_unit =
  | Chr(char)
  | Code(string);
let units = (s: string): list((int, int, text_unit)) => {
  let n = String.length(s);
  let rec close = j =>
    if (j >= n || Char.equal(s.[j], '\n')) {
      None;
    } else if (Char.equal(s.[j], '$') && !Char.equal(s.[j - 1], '\\')) {
      Some(j);
    } else {
      close(j + 1);
    };
  let rec go = (i, acc) =>
    if (i >= n) {
      List.rev(acc);
    } else if (Char.equal(s.[i], '\\') && i + 1 < n && Char.equal(s.[i + 1], '$')) {
      go(i + 2, [(i, i + 2, Chr('$')), ...acc]);
    } else if (Char.equal(s.[i], '$')) {
      switch (close(i + 1)) {
      | Some(j) => go(j + 1, [(i, j + 1, Code(String.sub(s, ~pos=i + 1, ~len=j - i - 1))), ...acc])
      | None => go(i + 1, [(i, i + 1, Chr('$')), ...acc])
      };
    } else {
      go(i + 1, [(i, i + 1, Chr(s.[i])), ...acc]);
    };
  go(0, []);
};

/* An inline expression's value as it sits in a line (TYPE.md "Inline": inline values only), set by the bridge: its
   words (a string its words, a number, a date, a list as fw prints them; blocks "!"; can't be worked out "?"), or a
   Ref (its title, and the Ref: a Link, so it stays a reference in the value). */
type inline_piece =
  | Words(string)
  | Refer(string, string);
let inline_value: ref((string, string) => inline_piece) = ref((_, _) => Words("?"));

/* A stored text as its line shows it, worked out where block `self` sits: (words, the Ref they link to) runs, in
   order; with `codes` false, its inline expressions left out (the recursive case: a block counting itself). */
let text_runs = (~self: string, ~codes=true, s: string, links: list((string, int, int))) => {
  let link_at = (a, e) =>
    List.find(links, ~f=((_, la, le)) => la <= a && e <= le) |> Option.map(~f=((to_, _, _)) => to_);
  let pieces =
    List.concat_map(units(s), ~f=((a, e, u)) =>
      switch (u) {
      | Chr(c) => [(String.make(1, c), link_at(a, e))]
      | Code(_) when !codes => []
      | Code(src) =>
        switch (inline_value^(self, src)) {
        | Words(w) => [(w, link_at(a, e))]
        | Refer(title, id) => [(title, Some(id))]
        }
      }
    );
  List.fold_right(pieces, ~init=[], ~f=((w, l), acc) =>
    switch (acc) {
    | [(w2, l2), ...rest] when Option.equal(String.equal, l, l2) => [(w ++ w2, l), ...rest]
    | _ => [(w, l), ...acc]
    }
  );
};
let text_shown = (~self, ~codes=true, s) =>
  String.contains(s, '$')   /* (most texts have no code: as they are) */
    ? String.concat(~sep="", List.map(text_runs(~self, ~codes, s, []), ~f=fst)) : s;

/* A text and its links (to, start, end) as Inlines: plain stretches and linked ones, in order; its inline
   expressions worked out where block `self` sits, their values in the line (a Ref's: a Link). */
/* A text with no inline expressions and its links (to, start, end) as Inlines: plain stretches and linked ones. */
let _text_with_links = (s: string, links: list((string, int, int))) => {
  let n = String.length(s);
  let links =
    List.filter(~f=((_, a, e)) => 0 <= a && a < e && e <= n, links)
    |> List.sort(~compare=((_, a, _), (_, b, _)) => Int.compare(a, b));
  let rec go = (at, links, acc) =>
    switch (links) {
    | [(to_, a, e), ...rest] when a >= at =>
      let acc = a > at ? [plain(String.sub(s, ~pos=at, ~len=a - at)), ...acc] : acc;
      go(e, rest, [link(String.sub(s, ~pos=a, ~len=e - a), to_), ...acc]);
    | [_, ...rest] => go(at, rest, acc) /* (overlapping: the first kept) */
    | [] => List.rev(at < n ? [plain(String.sub(s, ~pos=at, ~len=n - at)), ...acc] : acc)
    };
  text_of_inlines(go(0, links, []));
};
let text_with = (~self: string="", s: string, links: list((string, int, int))) =>
  !String.contains(s, '$')
    ? _text_with_links(s, links)   /* (most texts have no code: their links as they are) */
    : text_of_inlines(
    List.map(text_runs(~self, s, links), ~f=((w, l)) =>
      switch (l) {
      | Some(to_) => link(w, to_)
      | None => plain(w)
      }
    ),
  );
let from = (id, b) =>
  Fresh.Exp.(
    ap(
      Forward,
      ctr("From", Fresh.Typ.prod([ref_t, block_t])),
      tuple([mk_ref(id), b]),
    )
  );
let loop = id => Fresh.Exp.(ap(Forward, ctr("Loop", ref_t), mk_ref(id)));
let paraphrase = (id, s) =>
  Fresh.Exp.(
    ap(
      Forward,
      ctr("Paraphrase", Fresh.Typ.prod([ref_t, Fresh.Typ.string()])),
      tuple([mk_ref(id), string(s)]),
    )
  );
let blocks = (l: list(DHExp.t)) =>
  Fresh.Exp.(
    ap(Forward, ctr("Blocks", Fresh.Typ.list(block_t)), list_lit(l))
  );
let hole = () => Fresh.Exp.empty_hole();

/* --- dates: ISO 8601 inside, read as numbers; days from the civil calendar (H. Hinnant's) ----------------------- */
let mk_date = (iso: string): DHExp.t =>
  Fresh.Exp.(ap(Forward, constructor("Date", Some(Some(Fresh.Typ.arrow(Fresh.Typ.string(), date_t)))), string(iso)));
let num = (iso, pos, len) =>
  String.length(iso) >= pos + len ? Stdlib.int_of_string_opt(String.sub(iso, ~pos, ~len)) : None;
/* (year, month, day, hour, minute, its offset from UTC in minutes) as written */
let date_parts = (iso: string) =>
  switch (num(iso, 0, 4), num(iso, 5, 2), num(iso, 8, 2), num(iso, 11, 2), num(iso, 14, 2)) {
  | (Some(y), Some(mo), Some(d), Some(h), Some(mi)) =>
    let off =
      switch (num(iso, 20, 2), num(iso, 23, 2)) {
      | (Some(oh), Some(om)) => (Char.equal(iso.[19], '-') ? (-1) : 1) * (oh * 60 + om)
      | _ => 0
      };
    Some((y, mo, d, h, mi, off));
  | _ => None
  };
let days_from_civil = (y, m, d) => {
  let y = m <= 2 ? y - 1 : y;
  let era = (y >= 0 ? y : y - 399) / 400;
  let yoe = y - era * 400;
  let doy = (153 * ((m + 9) % 12) + 2) / 5 + d - 1;
  era * 146097 + yoe * 365 + yoe / 4 - yoe / 100 + doy - 719468;
};
let epoch_minutes = iso =>
  switch (date_parts(iso)) {
  | Some((y, mo, d, h, mi, off)) => Some(days_from_civil(y, mo, d) * 1440 + h * 60 + mi - off)
  | None => None
  };
let months = [|"Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"|];
/* As fw's header writes a date: "Nov 25, 2026, 3:12 pm" */
let show_date = iso =>
  switch (date_parts(iso)) {
  | Some((y, mo, d, h, mi, _)) when mo >= 1 && mo <= 12 =>
    Printf.sprintf("%s %d, %d, %d:%02d %s", months[mo - 1], d, y, h % 12 == 0 ? 12 : h % 12, mi, h < 12 ? "am" : "pm")
  | _ => iso
  };
/* A Date value's ISO text, if it is one. */
let iso_of_date = (d: DHExp.t): option(string) =>
  switch (Unboxing.unbox(SumWithArg("Date"), d)) {
  | Matches(arg) =>
    switch (Unboxing.unbox(Atom(String), arg)) {
    | Matches(s) => Some(s)
    | _ => None
    }
  | _ => None
  };
let attention = (c: char): option(DHExp.t) =>
  switch (c) {
  | 'o' => Some("Opened")
  | 'c' => Some("Stayed")
  | 'w' => Some("Wrote")
  | 'q' => Some("Through")
  | _ => None
  }
  |> Option.map(~f=name => Fresh.Exp.constructor(name, Some(Some(attention_t))));
let mk_visit = ((iso, flags)) =>
  Fresh.Exp.(
    ap(
      Forward,
      constructor("Visit", Some(Some(Fresh.Typ.arrow(Fresh.Typ.prod([date_t, Fresh.Typ.list(attention_t)]), visit_t)))),
      tuple([mk_date(iso), list_lit(List.filter_map(String.to_list(flags), ~f=attention))]),
    )
  );
let some = x => Fresh.Exp.ap(Forward, BuiltinsADT.Option.some, x);
let opt = (f, o) =>
  switch (o) {
  | Some(x) => some(f(x))
  | None => BuiltinsADT.Option.none
  };
let refs = ids => Fresh.Exp.list_lit(List.map(~f=mk_ref, ids));

/* A Ref value's id, if it is one. */
let id_of_ref = (d: DHExp.t): option(string) =>
  switch (Unboxing.unbox(SumWithArg("Ref"), d)) {
  | Matches(arg) =>
    switch (Unboxing.unbox(Atom(String), arg)) {
    | Matches(s) => Some(s)
    | _ => None
    }
  | _ => None
  };

/* --- evaluating the store's own expressions --------------------------------- */

/* How deep one expression may read another's (as quotes are followed: fw_block.MAX_DEPTH is 8). */
let max_depth = 8;
/* The ids being shown right now, outermost last: a read of one of them is a cycle. */
let reading: ref(list(string)) = ref([]);
/* Set by the bridge: the expression block `id`'s source evaluated to a Block value (None when it isn't one); `id` is
   where it sits, for above and below. */
let eval_source: ref((string, string) => option(DHExp.t)) = ref((_, _) => None);

/* A node as shown: a Block value. Expressions are evaluated (through the bridge); a cycle or too deep is a hole. */
let rec shown = (n: node): DHExp.t =>
  if (!String.is_empty(n.id) && List.mem(reading^, n.id, ~equal=String.equal)) {
    loop(n.id); /* (x met again while showing x: the recursive case, Loop(@x)) */
  } else if (List.length(reading^) >= max_depth) {
    hole();
  } else {
    let saved = reading^;
    reading := [n.id, ...saved];
    let v =
      switch (n.case) {
      | Text(s, links) => text_with(~self=n.id, s, links)
      | Quote(id) => quoted(n.id, id) /* a quote is body(@id); of one expression, a call where the quote sits */
      | Paraphrase(id, s) => paraphrase(id, s)
      | Blocks(kids) => blocks(List.map(~f=shown, kids))
      | Picture(_) => blocks([]) /* (a picture: nothing to compute over; a From of its pericope draws it) */
      | Expr(src) =>
        switch (eval_source^(n.id, src)) {
        | Some(v) => v
        | None => hole()
        }
      | Unknown => hole()
      };
    reading := saved;
    v;
  }
/* A quote (its own block `qid`) of `id`: of one expression (the expression block, or a pericope holding just it), a
   call: that expression evaluated where the quote sits (its above and below the quote's; the user, 2026-11-24: "it
   should just be a red block which caries the result of the evaluated thing"); anything else, body(@id). */
and quoted = (qid: string, id: string): DHExp.t =>
  switch (look(snapshot^.nodes, id)) {
  | Some({case: Expr(src), _})
  | Some({case: Blocks([{case: Expr(src), _}]), _}) =>
    from(
      id,
      switch (eval_source^(qid, src)) {
      | Some(v) => v
      | None => hole()
      },
    )
  | _ => from_id(id)
  }
/* body(@id): From(@id, what it shows); a Ref to nothing, a hole ("this pericope was deleted" is for later). */
and from_id = (id: string): DHExp.t =>
  switch (look(snapshot^.nodes, id)) {
  | Some(n) => from(id, shown(n))
  | None => hole()
  };

let body_of = from_id;

let members_of = (kid: string): list(string) =>
  List.filter_map(
    ~f=p => List.mem(p.kinds, kid, ~equal=String.equal) ? Some(p.pid) : None,
    {
      seen("*");
      snapshot^.pericopes;
    },
  );

/* The pericope a Ref's facts are read from: its own, or (a block's) the pericope it's in. */
let meta_of = (id: string): option(pericope) =>
  switch (look(snapshot^.home, id)) {
  | Some(pid) => look(snapshot^.meta, pid)
  | None => None
  };

/* A Ref's own facts (a block's, a pericope's): the snapshot's. */
let facts_of = (id: string): option(facts) => look(snapshot^.facts, id);

/* Set when a run met itself where a number was wanted (wordCount(this)): its holes are drawn ↻ (fwbridge). */
let looped = ref(false);
/* Set by the bridge: the words expression block `id` (source `src`) shows, worked out where it sits; None when it
   can't be (unparsable, ran too long). */
let expr_words: ref((string, string) => option(int)) = ref((_, _) => None);

/* A word: a run without spaces with something in it besides punctuation (fw_block.is_word, the page's isWord: one rule
   wherever fw counts; the user, 2026-11-25: the `+` and `?` of an unfinished value aren't words). The typographic marks
   are UTF-8 byte strings here, taken out first; then any byte that isn't ASCII punctuation is something. */
let typographic = ["–", "—", "…", "“", "”", "‘", "’", "«", "»", "•", "·"];
let is_word = (w: string): bool => {
  let w = List.fold(typographic, ~init=w, ~f=(w, t) => String.substr_replace_all(w, ~pattern=t, ~with_=""));
  String.exists(w, ~f=c => !String.mem("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~", c));
};
/* Words in a text as fw counts them (the header's count). */
let words_of_text = (s: string): int =>
  String.split_on_chars(s, ~on=[' ', '\n', '\t', '\r'])
  |> List.count(~f=w => !String.is_empty(w) && is_word(w));

/* Words in a Block value, as they'd show: a Loop counts none (the recursive case: everything but itself). */
let rec value_words = (d: DHExp.t): int => {
  let str = x =>
    switch (Unboxing.unbox(Atom(String), x)) {
    | Matches(s) => s
    | _ => ""
    };
  let inline = x =>
    switch (Unboxing.unbox(SumWithArg("Plain"), x)) {
    | Matches(p) => str(p)
    | _ =>
      switch (Unboxing.unbox(SumWithArg("Link"), x)) {
      | Matches(l) =>
        switch (Unboxing.unbox(Tuple(2), l)) {
        | Matches([w, _]) => str(w)
        | _ => ""
        }
      | _ => ""
      }
    };
  let words = words_of_text;
  switch (Unboxing.unbox(SumWithArg("Text"), d)) {
  | Matches(a) =>
    switch (Unboxing.unbox(ListLit, a)) {
    | Matches(parts) => words(String.concat(~sep="", List.map(~f=inline, parts)))
    | _ => 0
    }
  | _ =>
    switch (Unboxing.unbox(SumWithArg("Paraphrase"), d)) {
    | Matches(p) =>
      switch (Unboxing.unbox(Tuple(2), p)) {
      | Matches([_, t]) => words(str(t))
      | _ => 0
      }
    | _ =>
      switch (Unboxing.unbox(SumWithArg("Blocks"), d)) {
      | Matches(l) =>
        switch (Unboxing.unbox(ListLit, l)) {
        | Matches(kids) => List.fold(kids, ~init=0, ~f=(a, k) => a + value_words(k))
        | _ => 0
        }
      | _ =>
        switch (Unboxing.unbox(SumWithArg("From"), d)) {
        | Matches(arg) =>
          switch (Unboxing.unbox(Tuple(2), arg)) {
          | Matches([_, b]) => value_words(b)
          | _ => 0
          }
        | _ => 0
        }
      }
    }
  };
};


let words_in = (n: node): int => {
  let seen = Stdlib.Hashtbl.create(16);
  let rec go = (n: node): int =>
    if (!String.is_empty(n.id) && Stdlib.Hashtbl.mem(seen, n.id)) {
      0;
    } else {
      if (!String.is_empty(n.id)) {
        Stdlib.Hashtbl.replace(seen, n.id, ());
      };
      switch (n.case) {
      | Text(t, _)
      | Paraphrase(_, t) =>
        /* the words it shows: its inline expressions' values (TYPE.md "Inline"), never their code; one being worked
           out now (reading itself): those left out, the recursive case */
        words_of_text(text_shown(~self=n.id, ~codes=!List.mem(reading^, n.id, ~equal=String.equal), t))
      | Blocks(kids) => List.fold(kids, ~init=0, ~f=(a, k) => a + go(k))
      | Quote(id) =>
        switch (look(snapshot^.nodes, id)) {
        | Some(t) => go(t)
        | None => 0
        }
      | Expr(src) =>
        /* what it shows, worked out where it sits; one being worked out now (this, or one reading this one): the
           recursive case, counted as none (a pericope's count is everything but it) */
        if (List.mem(reading^, n.id, ~equal=String.equal)) {
          0;
        } else {
          Option.value(expr_words^(n.id, src), ~default=0);
        }
      | Picture(_)
      | Unknown => 0
      };
    };
  go(n);
};

/* --- the built-ins ------------------------------------------------------------ */

let on_ref = (f: string => DHExp.t, d: DHExp.t): option(DHExp.t) =>
  switch (id_of_ref(d)) {
  | Some(id) => Some(f(id))
  | None => None
  };

/* A fact of a Ref (its own: a block's, a pericope's); a Ref the snapshot doesn't know (just written), a hole. */
let fact = (f: facts => DHExp.t) =>
  on_ref(id =>
    switch (facts_of(id)) {
    | Some(x) => f(x)
    | None => hole()
    }
  );
/* A Date's ISO text and another's, for the two-Date built-ins. */
let two_dates = (f: (string, string) => option(DHExp.t), d: DHExp.t): option(DHExp.t) =>
  switch (Unboxing.unbox(Tuple(2), d)) {
  | Matches([a, b]) =>
    switch (iso_of_date(a), iso_of_date(b)) {
    | (Some(a), Some(b)) => f(a, b)
    | _ => None
    }
  | _ => None
  };
let on_date = (f: string => DHExp.t, d: DHExp.t): option(DHExp.t) =>
  switch (iso_of_date(d)) {
  | Some(iso) => Some(f(iso))
  | None => None
  };
let part = (pick: ((int, int, int, int, int, int)) => int) =>
  on_date(iso =>
    switch (date_parts(iso)) {
    | Some(p) => Fresh.Exp.int(pick(p))
    | None => hole()
    }
  );
let between = (per: int) =>
  two_dates((a, b) =>
    switch (epoch_minutes(a), epoch_minutes(b)) {
    | (Some(x), Some(y)) => Some(Fresh.Exp.int((y - x) / per))
    | _ => None
    }
  );
let date_fn = (name, pick) => {name, arg: Typ.term_of(date_var), ret: Atom(Int), imp: part(pick), custom_statics: None};
let date_ty = Typ.term_of(date_var);
let ref_ty = Typ.term_of(ref_var);
let option_of = (t: Typ.t): Typ.term => Typ.term_of(BuiltinsADT.sum_type([("None", None), ("Some", Some(t))]));

/* A From's parts (Ref, Block), if `d` is one. */
let from_parts = (d: DHExp.t): option((DHExp.t, DHExp.t)) =>
  switch (Unboxing.unbox(SumWithArg("From"), d)) {
  | Matches(arg) =>
    switch (Unboxing.unbox(Tuple(2), arg)) {
    | Matches([r, b]) => Some((r, b))
    | _ => None
    }
  | _ => None
  };

/* --- casts (TYPE.md "Casting"): ordinary functions, so an inserted one is a call you could have written, and the
   page can show it. The bridge puts one in wherever Hazel's checker finds a value of one type where another is
   wanted and fw knows the way (fwbridge `cast_for`); a hole is never cast (its type is unknown: no mismatch), and a
   cast given a hole gives a hole. */
/* Set by the bridge: a value as text, as fw writes it (a date pretty, a reference its title, a list its things with
   commas between, a string its words). */
let value_text: ref(DHExp.t => string) = ref(_ => "");
let is_hole = (d: DHExp.t): bool =>
  switch (Exp.term_of(d)) {
  | EmptyHole
  | MultiHole(_) => true
  | _ => false
  };
/* A reference's title, as the title built-in gives it ("?" for one that's gone). */
let title_of = (id: string): string =>
  switch (facts_of(id), meta_of(id)) {
  | (Some(f), _) => f.ftitle
  | (None, Some(p)) when String.equal(p.pid, id) => p.title
  | _ => "?"
  };
/* A value as blocks: a reference its window (body), text a block of text, a list its things as blocks; anything
   else its text in a block. */
let rec as_block = (d: DHExp.t): DHExp.t =>
  if (is_hole(d)) {
    hole();
  } else {
    switch (id_of_ref(d)) {
    | Some(id) => from_id(id)
    | None =>
      switch (Unboxing.unbox(Atom(String), d)) {
      | Matches(s) => text(s)
      | _ =>
        switch (Exp.term_of(d)) {
        | ListLit(l) => blocks(List.map(~f=as_block, l))
        | _ => text(value_text^(d))
        }
      }
    };
  };

let fns: list(fn) = [
  {
    name: "asText",
    arg: Unknown(Internal),
    ret: Atom(String),
    imp: d => Some(is_hole(d) ? hole() : Fresh.Exp.string(value_text^(d))),
    custom_statics: None,
  },
  {name: "asBlock", arg: Unknown(Internal), ret: Typ.term_of(block_var), imp: d => Some(as_block(d)), custom_statics: None},
  {
    name: "text",
    arg: Atom(String),
    ret: Typ.term_of(block_var),
    imp: d => {
      let-unbox s = (Atom(String), d);
      Some(text(s));
    },
    custom_statics: None,
  },
  {
    name: "origin",
    arg: Typ.term_of(block_var),
    ret: option_of(ref_var),
    imp: d =>
      Some(
        switch (from_parts(d)) {
        | Some((r, _)) => Fresh.Exp.ap(Forward, BuiltinsADT.Option.some, r)
        | None => BuiltinsADT.Option.none
        },
      ),
    custom_statics: None,
  },
  {
    name: "content",
    arg: Typ.term_of(block_var),
    ret: Typ.term_of(block_var),
    imp: d =>
      Some(
        switch (from_parts(d)) {
        | Some((_, b)) => b
        | None => d
        },
      ),
    custom_statics: None,
  },
  {
    name: "ref",
    arg: Atom(String),
    ret: Typ.term_of(ref_var),
    imp: d => {
      let-unbox s = (Atom(String), d);
      Some(mk_ref(s));
    },
    custom_statics: None,
  },
  {
    name: "body",
    arg: Typ.term_of(ref_var),
    ret: Typ.term_of(block_var),
    imp: on_ref(body_of),
    custom_statics: None,
  },
  {
    name: "title",
    arg: Typ.term_of(ref_var),
    ret: Atom(String),
    imp:
      on_ref(id =>
        switch (facts_of(id), meta_of(id)) {
        | (Some(f), _) => Fresh.Exp.string(f.ftitle)
        | (None, Some(p)) when String.equal(p.pid, id) => Fresh.Exp.string(p.title)
        | _ => hole()
        }
      ),
    custom_statics: None,
  },
  {
    name: "tagged",
    arg: Typ.term_of(ref_var),
    ret: List(ref_var),
    imp: on_ref(id => refs(members_of(id))),
    custom_statics: None,
  },
  {
    name: "tags",
    arg: Typ.term_of(ref_var),
    ret: List(ref_var),
    imp:
      on_ref(id =>
        refs(
          switch (facts_of(id), meta_of(id)) {
          | (Some(f), _) => List.filter_map(f.answers, ~f=((k, yes)) => yes ? Some(k) : None)
          | (None, Some(p)) when String.equal(p.pid, id) => p.kinds
          | _ => []
          },
        )
      ),
    custom_statics: None,
  },
  {
    name: "wordCount",
    arg: Typ.term_of(ref_var),
    ret: Atom(Int),
    imp:
      on_ref(id =>
        if (List.mem(reading^, id, ~equal=String.equal)) {
          looped := true; /* (its own words, while it's being made: ↻) */
          hole();
        } else {
          switch (look(snapshot^.nodes, id)) {
          | Some(n) => Fresh.Exp.int(words_in(n))
          | None => hole()
          };
        }
      ),
    custom_statics: None,
  },
  {name: "created", arg: ref_ty, ret: date_ty, imp: fact(f => mk_date(f.fcreated)), custom_statics: None},
  {name: "updated", arg: ref_ty, ret: date_ty, imp: fact(f => mk_date(f.fupdated)), custom_statics: None},
  {name: "writtenTitle", arg: ref_ty, ret: option_of(Fresh.Typ.string()), imp: fact(f => opt(Fresh.Exp.string, f.written)), custom_statics: None},
  {name: "visits", arg: ref_ty, ret: Atom(Int), imp: fact(f => Fresh.Exp.int(f.fvisits)), custom_statics: None},
  {name: "firstVisit", arg: ref_ty, ret: option_of(date_var), imp: fact(f => opt(mk_date, f.first)), custom_statics: None},
  {
    name: "lastVisit",
    arg: ref_ty,
    ret: option_of(date_var),
    imp: fact(f => opt(((iso, _)) => mk_date(iso), List.last(f.recent))),
    custom_statics: None,
  },
  {name: "recentVisits", arg: ref_ty, ret: List(visit_var), imp: fact(f => Fresh.Exp.list_lit(List.map(f.recent, ~f=mk_visit))), custom_statics: None},
  {
    name: "notTags",
    arg: ref_ty,
    ret: List(ref_var),
    imp: fact(f => refs(List.filter_map(f.answers, ~f=((k, yes)) => yes ? None : Some(k)))),
    custom_statics: None,
  },
  {name: "isPericope", arg: ref_ty, ret: Atom(Bool), imp: fact(f => Fresh.Exp.bool(f.entry)), custom_statics: None},
  {name: "pericopeOf", arg: ref_ty, ret: ref_ty, imp: fact(f => mk_ref(f.fhome)), custom_statics: None},
  {
    name: "backlinks",
    arg: ref_ty,
    ret: List(ref_var),
    imp:
      on_ref(id =>
        switch (facts_of(id), meta_of(id)) {
        | (Some(f), _) => refs(f.fbacklinks)
        | (None, Some(p)) when String.equal(p.pid, id) => refs(p.backlinks)
        | _ => hole()
        }
      ),
    custom_statics: None,
  },
  date_fn("year", ((y, _, _, _, _, _)) => y),
  date_fn("month", ((_, m, _, _, _, _)) => m),
  date_fn("day", ((_, _, d, _, _, _)) => d),
  date_fn("hour", ((_, _, _, h, _, _)) => h),
  date_fn("minute", ((_, _, _, _, mi, _)) => mi),
  date_fn("weekday", ((y, m, d, _, _, _)) => (days_from_civil(y, m, d) + 3) % 7 + 1),
  {name: "showDate", arg: date_ty, ret: Atom(String), imp: on_date(iso => Fresh.Exp.string(show_date(iso))), custom_statics: None},
  {
    name: "before",
    arg: Prod([date_var, date_var]),
    ret: Atom(Bool),
    imp:
      two_dates((a, b) =>
        switch (epoch_minutes(a), epoch_minutes(b)) {
        | (Some(x), Some(y)) => Some(Fresh.Exp.bool(x < y))
        | _ => None
        }
      ),
    custom_statics: None,
  },
  {name: "minutesBetween", arg: Prod([date_var, date_var]), ret: Atom(Int), imp: between(1), custom_statics: None},
  {name: "daysBetween", arg: Prod([date_var, date_var]), ret: Atom(Int), imp: between(1440), custom_statics: None},
];

/* These values here are placeholders: the bridge binds them per run (all_value, neighbour) in the env it evaluates
   with. above and below: the peer blocks just before and after the expression block (the user, 2026-11-24: "an
   expression which uses above, below … to define where it sits at the moment of viewing"; peers only), worked out
   each time it's viewed, wherever it is now; none there, a hole. */
let consts: list(const) = [
  {name: "pericopes", typ: List(ref_var), imp: Fresh.Exp.list_lit([])},
  {name: "above", typ: Typ.term_of(ref_var), imp: Fresh.Exp.empty_hole()},
  {name: "below", typ: Typ.term_of(ref_var), imp: Fresh.Exp.empty_hole()},
  {name: "this", typ: Typ.term_of(ref_var), imp: Fresh.Exp.empty_hole()},
  {name: "here", typ: Typ.term_of(ref_var), imp: Fresh.Exp.empty_hole()},
  {name: "self", typ: Typ.term_of(ref_var), imp: Fresh.Exp.empty_hole()},
  {name: "now", typ: Typ.term_of(date_var), imp: Fresh.Exp.empty_hole()},
];

/* The peer block `dir` (-1 above, 1 below) of block `id`, as a Ref; none (or no id: not on a page), a hole. */
let neighbour = (id: string, dir: int): DHExp.t =>
  switch (Stdlib.Hashtbl.find_opt(snapshot^.peers, id)) {   /* (bound for every run: read only if the source names it, the bridge) */
  | Some(ids) =>
    let rec find = (i, l) =>
      switch (l) {
      | [x, ..._] when String.equal(x, id) => Some(i)
      | [_, ...rest] => find(i + 1, rest)
      | [] => None
      };
    switch (find(0, ids)) {
    | Some(i) =>
      switch (List.nth(ids, i + dir)) {
      | Some(x) when !String.is_empty(x) => mk_ref(x)
      | _ => hole()
      }
    | None => hole()
    };
  | None => hole()
  };

/* this: the pericope the expression is in, where it sits now (a call's: the quote's pericope), as a Ref (the user,
   2026-11-25: "this should be the current pericope, we dont need a word for self yet"); not on a page, a hole.
   Read from inside, the expression's own place in it is the recursive case: body(this) shows it as Loop(@it), and
   wordCount(this) counts everything but it. */
let this_value = (self: string): DHExp.t =>
  switch (Stdlib.Hashtbl.find_opt(snapshot^.home, self)) {
  | Some(pid) => mk_ref(pid)
  | None => hole()
  };

/* here: the pericope the expression is being viewed from (the user, 2026-11-25: "two people can look at one value
   from two perspectives and the value is different"): the page's, set per run by the bridge and passed inward (an
   expression read through another has the reader's); no one looking (the core's counts), it's `this`. */
let viewer: ref(string) = ref("");
let here_value = (self: string): DHExp.t => String.is_empty(viewer^) ? this_value(self) : mk_ref(viewer^);
/* self: the block itself (an expression block, or the block an inline expression is in; a call's: the quote). Read
   from inside it's the recursive case: body(self) a loop, wordCount(self) ↻. */
let self_value = (self: string): DHExp.t => String.is_empty(self) ? hole() : mk_ref(self);

/* now: the snapshot's moment (the page's, as it's handed over), a Date. */
let now_value = (): DHExp.t => String.is_empty(snapshot^.now) ? hole() : mk_date(snapshot^.now);   /* (now is read by being bound: run_source records it when the source names it) */

let all_value = (): DHExp.t =>
  refs(List.map(~f=p => p.pid, snapshot^.pericopes));   /* (bound for every run: read only if the source names it, the bridge) */
