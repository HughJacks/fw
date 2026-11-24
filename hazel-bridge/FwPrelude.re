/* FwPrelude: fw's context for Hazel (fw extends Hazel: fw-expr's TYPE.md).

   Two types:
     Ref    opaque: a pericope's or a block's id. Made only by `ref` (what `@<id>` in a source becomes) and by the
            built-ins below; its constructor isn't in the context, so a program can't take one apart or forge one
            except through `ref`.
     Inline = + Plain(String) + Link((String, Ref))      a text's words, and its links
     Block  = + Text([Inline]) + Paraphrase((Ref, String)) + Blocks([Block]) + From((Ref, Block))
            the shown block (fw-expr TYPE.md, "Every block in the dialect"): a quote is body(@x), a From, the blocks
            that came from x unchanged. From is sealed, as Ref is: its constructor isn't in the context, so only body
            makes one (no forged quote); origin and content read one.

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
   A block's facts (title, kinds, created, …) are its pericope's.
     tags    : Ref -> [Ref]        its tags (yes answers)

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

type snapshot = {
  pericopes: list(pericope),
  nodes: Stdlib.Hashtbl.t(string, node), /* every block and pericope body, by id */
  titles: Stdlib.Hashtbl.t(string, string),
  kinds_of: Stdlib.Hashtbl.t(string, list(string)),
  meta: Stdlib.Hashtbl.t(string, pericope), /* each pericope's facts, by its id */
  home: Stdlib.Hashtbl.t(string, string), /* a block's id -> its pericope's (a block's facts are its pericope's) */
  peers: Stdlib.Hashtbl.t(string, list(string)) /* a block's id -> its parent's blocks, in order (above, below) */
};

let empty_snapshot = (): snapshot => {
  pericopes: [],
  nodes: Stdlib.Hashtbl.create(64),
  titles: Stdlib.Hashtbl.create(64),
  kinds_of: Stdlib.Hashtbl.create(64),
  meta: Stdlib.Hashtbl.create(64),
  home: Stdlib.Hashtbl.create(256),
  peers: Stdlib.Hashtbl.create(256),
};

let snapshot: ref(snapshot) = ref(empty_snapshot());

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
      ]),
    )
  );

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
        | ConstructorMap.Variant("From", _, _) => false
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
  @ [
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
/* A text and its links (to, start, end) as Inlines: plain stretches and linked ones, in order. */
let text_with = (s: string, links: list((string, int, int))) => {
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
let from = (id, b) =>
  Fresh.Exp.(
    ap(
      Forward,
      ctr("From", Fresh.Typ.prod([ref_t, block_t])),
      tuple([mk_ref(id), b]),
    )
  );
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
  if (List.length(reading^) >= max_depth
      || !String.is_empty(n.id)
      && List.mem(reading^, n.id, ~equal=String.equal)) {
    hole();
  } else {
    let saved = reading^;
    reading := [n.id, ...saved];
    let v =
      switch (n.case) {
      | Text(s, links) => text_with(s, links)
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
  switch (Stdlib.Hashtbl.find_opt(snapshot^.nodes, id)) {
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
  switch (Stdlib.Hashtbl.find_opt(snapshot^.nodes, id)) {
  | Some(n) => from(id, shown(n))
  | None => hole()
  };

let body_of = from_id;

let members_of = (kid: string): list(string) =>
  List.filter_map(
    ~f=p => List.mem(p.kinds, kid, ~equal=String.equal) ? Some(p.pid) : None,
    snapshot^.pericopes,
  );

/* The pericope a Ref's facts are read from: its own, or (a block's) the pericope it's in. */
let meta_of = (id: string): option(pericope) =>
  switch (Stdlib.Hashtbl.find_opt(snapshot^.home, id)) {
  | Some(pid) => Stdlib.Hashtbl.find_opt(snapshot^.meta, pid)
  | None => None
  };

/* Words in a node as fw counts them (the header's count): the text shown, quoted text flattened, each block once. */
let words_of_text = (s: string): int =>
  String.split_on_chars(s, ~on=[' ', '\n', '\t', '\r'])
  |> List.count(~f=w => !String.is_empty(w));
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
      | Paraphrase(_, t) => words_of_text(t)
      | Blocks(kids) => List.fold(kids, ~init=0, ~f=(a, k) => a + go(k))
      | Quote(id) =>
        switch (Stdlib.Hashtbl.find_opt(snapshot^.nodes, id)) {
        | Some(t) => go(t)
        | None => 0
        }
      | Expr(_)
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

let fns: list(fn) = [
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
    ret: Typ.term_of(BuiltinsADT.Option.t),
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
        switch (meta_of(id)) {
        | Some(p) => Fresh.Exp.string(p.title)
        | None => hole()
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
          switch (meta_of(id)) {
          | Some(p) => p.kinds
          | None => []
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
        switch (Stdlib.Hashtbl.find_opt(snapshot^.nodes, id)) {
        | Some(n) => Fresh.Exp.int(words_in(n))
        | None => hole()
        }
      ),
    custom_statics: None,
  },
  {
    name: "created",
    arg: Typ.term_of(ref_var),
    ret: Atom(String),
    imp: on_ref(id => switch (meta_of(id)) { | Some(p) => Fresh.Exp.string(p.created) | None => hole() }),
    custom_statics: None,
  },
  {
    name: "updated",
    arg: Typ.term_of(ref_var),
    ret: Atom(String),
    imp: on_ref(id => switch (meta_of(id)) { | Some(p) => Fresh.Exp.string(p.updated) | None => hole() }),
    custom_statics: None,
  },
  {
    name: "visits",
    arg: Typ.term_of(ref_var),
    ret: Atom(Int),
    imp: on_ref(id => switch (meta_of(id)) { | Some(p) => Fresh.Exp.int(p.visits) | None => hole() }),
    custom_statics: None,
  },
  {
    name: "backlinks",
    arg: Typ.term_of(ref_var),
    ret: List(ref_var),
    imp: on_ref(id => switch (meta_of(id)) { | Some(p) => refs(p.backlinks) | None => hole() }),
    custom_statics: None,
  },
];

/* These values here are placeholders: the bridge binds them per run (all_value, neighbour) in the env it evaluates
   with. above and below: the peer blocks just before and after the expression block (the user, 2026-11-24: "an
   expression which uses above, below … to define where it sits at the moment of viewing"; peers only), worked out
   each time it's viewed, wherever it is now; none there, a hole. */
let consts: list(const) = [
  {name: "pericopes", typ: List(ref_var), imp: Fresh.Exp.list_lit([])},
  {name: "above", typ: Typ.term_of(ref_var), imp: Fresh.Exp.empty_hole()},
  {name: "below", typ: Typ.term_of(ref_var), imp: Fresh.Exp.empty_hole()},
];

/* The peer block `dir` (-1 above, 1 below) of block `id`, as a Ref; none (or no id: not on a page), a hole. */
let neighbour = (id: string, dir: int): DHExp.t =>
  switch (Stdlib.Hashtbl.find_opt(snapshot^.peers, id)) {
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

let all_value = (): DHExp.t =>
  refs(List.map(~f=p => p.pid, snapshot^.pericopes));
