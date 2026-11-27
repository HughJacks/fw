/* fwbridge: fw's way into Hazel. Hazel's own pipeline as its CLI runs it (parse -> statics and elaboration ->
   evaluation), in fw's context (src/language/builtins/FwPrelude.re: Ref, Block, the store's built-ins).

   For the page:
     hazelRun(source, snapshot, self?)   a source evaluated; `self` the expression block's id (where it sits: above, below)
   It answers a JSON string:
     {kind: "block", type, block: tree}     a Block value, as a tree:
                                            {t: text, text} | {t: quote, target} | {t: paraphrase, target, text}
                                            | {t: blocks, children} | {t: hole, printed}
     {kind: "value", type, printed}         any other value
     {kind: "function", type}               a function
     {kind: "error", message}               it can't be run (can't parse)
   with `errors`: [{term, message}], Hazel's own words for each static error (the value still comes, around them).

   `snapshot` is a JSON string (null: the last one again): {pericopes: [{id, title, kinds, body: node}]}, a node
   {id, t: text|quote|paraphrase|blocks|expr|picture, text?, target?, source?, children?}, the page's own
   view of the store (the open pericope live from its editor). Parsed once per distinct string.

   `@<id>` in a source (fw's reference) is desugared here, before parsing, to `ref("<id>")`: a stopgap until Hazel's
   own syntax has a way to say it. */
open Js_of_ocaml;
open Haz3lcore;
open Language;

let settings: ExpToSegment.Settings.t = {
  secondary: AutoFormat,
  parenthesization: Defensive,
  label_format: QuoteWhenNecessary,
  inline: true,
  fold_case_clauses: false,
  fold_fn_bodies: `NoFold,
  hide_fixpoints: false,
  show_ascriptions: true,
  show_filters: true,
  show_unknown_as_hole: true,
  use_literal_lexemes: false,
  hole_tiles: false,
  project_tables: false,
};

/* A value without the ascriptions evaluation leaves on it (a hole's type, a builtin's result type). */
let rec strip = (d: Exp.t): Exp.t =>
  switch (Exp.term_of(d)) {
  | Asc(e, _)
  | Parens(e) => strip(e)
  | _ => d
  };

/* A value with every Date in it as fw writes one ("Nov 25, 2026, 3:12 pm"): dates are drawn pretty, wherever they are. */
let pretty_dates = (d: Exp.t): Exp.t =>
  Exp.map_term(
    ~f_exp=
      (continue, e) =>
        switch (FwPrelude.iso_of_date(e)) {
        | Some(iso) => IdTagged.FreshGrammar.Exp.string(FwPrelude.show_date(iso))
        | None => continue(e)
        },
    d,
  );

/* How a hole is drawn: ?, or ↻ when the run met itself (FwPrelude.looped: wordCount(this)). */
let hole_mark = ref("?");

let print = exp =>
  Printer.of_segment(
    ~holes=hole_mark^,
    ExpToSegment.exp_to_segment(~settings, strip(pretty_dates(exp))),
  );

/* A value as fw shows one (the user, 2026-11-25: "a list should pretty print as a comma separated list of things"): a
   list, its items one after another, commas between, a string (a date) in it its words; anything else as Hazel
   prints it. */
/* A list value's items, each as `shown` writes one (the page steps through them: the user, 2026-11-25, "we should be
   able to cursor navigate semantically differentiable computed values like lists"); not a list, None. */
let item_text = x =>
  switch (Unboxing.unbox(Atom(String), strip(x))) {
  | Matches(s) => s
  | _ => print(x)
  };
let items = (v: Exp.t): option(list(string)) =>
  switch (Exp.term_of(strip(pretty_dates(v)))) {
  | ListLit(l) => Some(List.map(~f=item_text, l))
  | _ => None
  };

let shown = (v: Exp.t): string => {
  let v = strip(pretty_dates(v));
  let item = item_text;
  switch (Exp.term_of(v)) {
  | ListLit([]) => "nothing"
  | ListLit(l) => String.concat(~sep=", ", List.map(~f=item, l))
  | _ => print(v)
  };
};

/* Text saying a type as fw says it: Block, Inline and Ref by name, never unrolled (as Typ.pretty_print and as Hazel's error
   messages print them; Ref first: Block's unrolled form names Ref). */
let named = (s: string): string =>
  [
    (Typ.pretty_print(FwPrelude.visit_t), "Visit"),
    (ErrorPrint.Print.typ(FwPrelude.visit_t), "Visit"),
    (Typ.pretty_print(FwPrelude.date_t), "Date"),
    (ErrorPrint.Print.typ(FwPrelude.date_t), "Date"),
    (Typ.pretty_print(FwPrelude.attention_t), "Attention"),
    (ErrorPrint.Print.typ(FwPrelude.attention_t), "Attention"),
    (Typ.pretty_print(FwPrelude.ref_t), "Ref"),
    (ErrorPrint.Print.typ(FwPrelude.ref_t), "Ref"),
    (Typ.pretty_print(FwPrelude.inline_t), "Inline"),
    (ErrorPrint.Print.typ(FwPrelude.inline_t), "Inline"),
    (Typ.pretty_print(FwPrelude.block_t), "Block"),
    (ErrorPrint.Print.typ(FwPrelude.block_t), "Block"),
  ]
  |> List.fold(~init=s, ~f=(s, (long, short)) =>
       String.substr_replace_all(s, ~pattern=long, ~with_=short)
     )
  |> (s => List.fold(["String", "Date", "Ref", "Block", "Int"], ~init=s, ~f=(s, t) =>
        String.substr_replace_all(s, ~pattern="None + Some(" ++ t ++ ")", ~with_="Option(" ++ t ++ ")")));   /* (as Hazel's Option) */

let ty_string = (ty: Typ.t): string => named(Typ.pretty_print(ty));

/* --- @<id> -> ref("<id>"), outside string literals ------------------------------- */

let is_id_char = c =>
  Char.is_alphanum(c) || Char.equal(c, '-') || Char.equal(c, '_');

let desugar = (src: string): string => {
  let b = Stdlib.Buffer.create(String.length(src) + 16);
  let n = String.length(src);
  let rec go = (i, in_string) =>
    if (i < n) {
      let c = src.[i];
      if (in_string) {
        Stdlib.Buffer.add_char(b, c);
        if (Char.equal(c, '\\') && i + 1 < n) {
          Stdlib.Buffer.add_char(b, src.[i + 1]);
          go(i + 2, true);
        } else {
          go(i + 1, !Char.equal(c, '"'));
        };
      } else if (Char.equal(c, '"')) {
        Stdlib.Buffer.add_char(b, c);
        go(i + 1, true);
      } else if (Char.equal(c, '@') && i + 1 < n && is_id_char(src.[i + 1])) {
        let j = ref(i + 1);
        while (j^ < n && is_id_char(src.[j^])) {
          j := j^ + 1;
        };
        Stdlib.Buffer.add_string(
          b,
          "ref(\"" ++ String.sub(src, ~pos=i + 1, ~len=j^ - i - 1) ++ "\")",
        );
        go(j^, false);
      } else {
        Stdlib.Buffer.add_char(b, c);
        go(i + 1, false);
      };
    };
  go(0, false);
  Stdlib.Buffer.contents(b);
};

/* --- the snapshot -------------------------------------------------------------------- */

let str = (j, k) =>
  switch (Yojson.Safe.Util.member(k, j)) {
  | `String(s) => s
  | _ => ""
  };

let rec node_of_json = (j: Yojson.Safe.t): FwPrelude.node => {
  let kids = () =>
    switch (Yojson.Safe.Util.member("children", j)) {
    | `List(l) => List.map(~f=node_of_json, l)
    | _ => []
    };
  let case: FwPrelude.case =
    switch (str(j, "t")) {
    | "text" =>
      Text(
        str(j, "text"),
        switch (Yojson.Safe.Util.member("links", j)) {
        | `List(l) =>
          List.filter_map(
            ~f=
              x =>
                switch (Yojson.Safe.Util.member("to", x), Yojson.Safe.Util.member("at", x)) {
                | (`String(to_), `List([`Int(a), `Int(e)])) => Some((to_, a, e))
                | _ => None
                },
            l,
          )
        | _ => []
        },
      )
    | "quote" => Quote(str(j, "target"))
    | "paraphrase" => Paraphrase(str(j, "target"), str(j, "text"))
    | "blocks"
    | "container" => Blocks(kids())
    | "expr" => Expr(str(j, "source"))
    | "picture"
    | "image" => Picture(str(j, "target"))
    | _ => Unknown
    };
  {id: str(j, "id"), case};
};

let pericope_of_json = (j: Yojson.Safe.t): FwPrelude.pericope => {
  pid: str(j, "id"),
  title: str(j, "title"),
  kinds:
    switch (Yojson.Safe.Util.member("kinds", j)) {
    | `List(l) =>
      List.filter_map(
        ~f=
          fun
          | `String(s) => Some(s)
          | _ => None,
        l,
      )
    | _ => []
    },
  body: node_of_json(Yojson.Safe.Util.member("body", j)),
  created: str(j, "created"),
  updated: str(j, "updated"),
  visits:
    switch (Yojson.Safe.Util.member("visits", j)) {
    | `Int(n) => n
    | _ => 0
    },
  backlinks:
    switch (Yojson.Safe.Util.member("backlinks", j)) {
    | `List(l) =>
      List.filter_map(
        ~f=
          fun
          | `String(s) => Some(s)
          | _ => None,
        l,
      )
    | _ => []
    },
};

let strings = (j: Yojson.Safe.t): list(string) =>
  switch (j) {
  | `List(l) =>
    List.filter_map(
      ~f=
        fun
        | `String(s) => Some(s)
        | _ => None,
      l,
    )
  | _ => []
  };

/* A block's own facts, as fw_web.snapshot_json sends them. */
let facts_of_json = (j: Yojson.Safe.t): FwPrelude.facts => {
  let m = k => Yojson.Safe.Util.member(k, j);
  {
    ftitle: str(j, "title"),
    written:
      switch (m("written")) {
      | `String(s) => Some(s)
      | _ => None
      },
    fcreated: str(j, "created"),
    fupdated: str(j, "updated"),
    fvisits:
      switch (m("visits")) {
      | `Int(n) => n
      | _ => 0
      },
    first:
      switch (m("first")) {
      | `String(s) => Some(s)
      | _ => None
      },
    recent:
      switch (m("recent")) {
      | `List(l) =>
        List.filter_map(
          ~f=
            fun
            | `List([`String(w), `String(f)]) => Some((w, f))
            | _ => None,
          l,
        )
      | _ => []
      },
    answers:
      switch (m("kinds")) {
      | `Assoc(l) =>
        List.filter_map(
          ~f=
            fun
            | (k, `Bool(b)) => Some((k, b))
            | _ => None,
          l,
        )
      | _ => []
      },
    fhome: str(j, "pericope"),
    entry:
      switch (m("entry")) {
      | `Bool(b) => b
      | _ => false
      },
    fbacklinks: strings(m("backlinks")),
  };
};

let set_snapshot = (json: string) => {
  let j = Yojson.Safe.from_string(json);
  let s =
    FwPrelude.make_snapshot(
      switch (Yojson.Safe.Util.member("pericopes", j)) {
      | `List(l) => List.map(~f=pericope_of_json, l)
      | _ => []
      },
    );
  switch (Yojson.Safe.Util.member("facts", j)) {
  | `Assoc(l) => List.iter(l, ~f=((id, f)) => Stdlib.Hashtbl.replace(s.facts, id, facts_of_json(f)))
  | _ => ()
  };
  FwPrelude.snapshot := {...s, now: str(j, "now")};
};

/* A patch to the snapshot held (the page's keystrokes: its open pericope, a few facts; never the whole store again):
   `pericopes` replaced by id or added, `gone` taken out, `facts` replaced by id, `now` if given. The rest stays as it
   was parsed: the cost of a key is the pericope it's in, not the store (2026-11-26: a whole re-read was ~53 ms). */
let patch_snapshot = (json: string) => {
  let j = Yojson.Safe.from_string(json);
  let old = FwPrelude.snapshot^;
  let fresh =
    switch (Yojson.Safe.Util.member("pericopes", j)) {
    | `List(l) => List.map(~f=pericope_of_json, l)
    | _ => []
    };
  let gone = strings(Yojson.Safe.Util.member("gone", j));
  let replaced = (p: FwPrelude.pericope) =>
    List.exists(fresh, ~f=(q: FwPrelude.pericope) => String.equal(q.pid, p.pid))
    || List.mem(gone, p.pid, ~equal=String.equal);
  let kept = List.filter(old.pericopes, ~f=p => !replaced(p));
  let s = FwPrelude.make_snapshot(kept @ fresh);
  Stdlib.Hashtbl.iter((id, f) => Stdlib.Hashtbl.replace(s.facts, id, f), old.facts);
  switch (Yojson.Safe.Util.member("facts", j)) {
  | `Assoc(l) => List.iter(l, ~f=((id, f)) => Stdlib.Hashtbl.replace(s.facts, id, facts_of_json(f)))
  | _ => ()
  };
  let now =
    switch (Yojson.Safe.Util.member("now", j)) {
    | `String(n) => n
    | _ => old.now
    };
  FwPrelude.snapshot := {...s, now};
};

/* --- running a source ------------------------------------------------------------------ */

let ctx = Builtins.ctx_init(Some(Operators.default_mode));

type ran = {
  value: Exp.t,
  ty: Typ.t,
  info: Statics.Map.t,
  too_long: bool, /* ran out of steps: it may never finish (a hole stands for its value) */
  casts: list((string, string, string)) /* each cast put in: (the cast, from, to), TYPE.md "Casting" */
};

/* --- casting (TYPE.md "Casting", the user, 2026-11-26: "a broad approach to autocasting for our context"): where
   Hazel's checker finds a value of one type where another is wanted, and fw knows the way, a cast is put in: the term
   wrapped in an ordinary call (asText, text, body, asBlock), the program checked again. Type-directed and visible
   (each reported); a hole's type is unknown, so it's never cast. */
let ty_name = (ty: Typ.t): string => named(Typ.pretty_print(ty));
let cast_for = (syn: Typ.t, ana: Typ.t): option(string) => {
  let s = ty_name(syn) and a = ty_name(ana);
  let listy = String.is_prefix(s, ~prefix="[") && String.is_suffix(s, ~suffix="]");
  let texty = List.mem(["Int", "Float", "Bool", "Date", "Ref"], s, ~equal=String.equal) || listy;
  switch (a) {
  | "String" when texty => Some("asText")
  | "Block" when String.equal(s, "String") => Some("text")
  | "Block" when String.equal(s, "Ref") => Some("body")
  | "Block" when texty => Some("asBlock")
  | _ => None
  };
};
/* The mismatches a cast mends, by the term's id: (id, the cast, from, to). */
let castable = (info: Statics.Map.t): list((Id.t, string, string, string)) =>
  Id.Map.bindings(info)
  |> List.filter_map(~f=((_, i)) =>
       switch (i) {
       | Info.InfoExp(e) =>
         List.find_map(e.marks, ~f=
           fun
           | Mark.ExpectationMismatch({ana, syn}) =>
             Option.map(cast_for(syn, ana), ~f=c => (Exp.rep_id(e.user_term), c, ty_name(syn), ty_name(ana)))
           | _ => None
         )
       | _ => None
       }
     )
  |> List.dedup_and_sort(~compare=((a, _, _, _), (b, _, _, _)) => Id.compare(a, b));
/* `exp` with each mismatch fw can mend cast (a few rounds: a cast may make the next one checkable), checked again:
   (the term, its statics, its elaboration, the casts put in). */
let with_casts = (exp: Exp.t) => {
  let rec go = (exp, n, done_) => {
    let (info, elab) = Statics.mk(CoreSettings.on, ctx, exp);
    switch (n > 0 ? castable(info) : []) {
    | [] => (exp, info, elab, List.rev(done_))
    | found =>
      let at = Id.Map.of_list(List.map(found, ~f=((id, c, _, _)) => (id, c)));
      let exp =
        Exp.map_term(
          ~f_exp=
            (continue, e) =>
              switch (Id.Map.find_opt(Exp.rep_id(e), at)) {
              | Some(c) => IdTagged.FreshGrammar.Exp.(ap(Forward, var(c), continue(e)))
              | None => continue(e)
              },
          exp,
        );
      go(exp, n - 1, List.rev_map(found, ~f=((_, c, f, t)) => (c, f, t)) @ done_);
    };
  };
  go(exp, 3, []);
};

/* Steps one run may take (the user, 2026-11-25: "a relatively short step limit"): a program that would run on (a
   recursion with no end) stops there and shows ∞, never freezing the page. Each expression read through another
   (body, wordCount) gets its own. */
let step_limit = 100000;


/* x.f, written for f(x) (TYPE.md "Projection": the user, 2026-11-25: "because this is simultaneously a live code
   notebook and a personal database, they sort of ARE fields"; built 2026-11-26). Done on the parsed term, where Hazel's
   own parser has already found x (its precedence: `@p.wordCount + 1` is (wordCount(@p)) + 1, `@p.title.length` a
   chain) and where Hazel reads `.` as a labeled tuple's projection, Dot(x, Label(f)). Rewritten when f is a function
   in scope: fw's or Hazel's built-ins (the context), or a name the code binds itself; anything else stays Hazel's own
   projection (a labeled tuple's field). Lexical, never x's type, so a hole stays a hole: `?.wordCount` is
   `wordCount(?)`. With arguments, Hazel's convention (a function of several takes one tuple): `x.f(a, b)` is
   `f((x, a, b))`, `x.f()` is `f(x)`. */
let projections = (exp: Exp.t): Exp.t => {
  let bound = Stdlib.Hashtbl.create(16);
  let _ =
    Exp.map_term(
      ~f_pat=
        (continue, p) => {
          switch (Pat.term_of(p)) {
          | Var(x) => Stdlib.Hashtbl.replace(bound, x, ())
          | _ => ()
          };
          continue(p);
        },
      exp,
    );
  let known = name =>
    Stdlib.Hashtbl.mem(bound, name) || Option.is_some(Ctx.lookup_var(ctx, name));
  let rec unparens = (e: Exp.t) =>
    switch (Exp.term_of(e)) {
    | Parens(x) => unparens(x)
    | _ => e
    };
  let label = (l: Exp.t) =>
    switch (Exp.term_of(l)) {
    | Label(name) when known(name) => Some(name)
    | _ => None
    };
  let module F = IdTagged.FreshGrammar.Exp;
  /* (go: the rewrite of a whole term, itself included: a chain's inner dots, its arguments) */
  let rec go = (e: Exp.t): Exp.t => Exp.map_term(~f_exp=step, e)
  and step = (continue, e) =>
        switch (Exp.term_of(e)) {
        | Ap(dir, f, arg) =>
          switch (Exp.term_of(f)) {
          | Dot(x, l) =>
            switch (label(l)) {
            | Some(name) =>
              let x = go(x);
              let args =
                switch (Exp.term_of(unparens(arg))) {
                | Tuple([]) => []
                | Tuple(l) => List.map(~f=go, l)
                | _ => [go(arg)]
                };
              {...e, term: Ap(dir, F.var(name), List.is_empty(args) ? x : F.tuple([x, ...args]))};
            | None => continue(e)
            }
          | _ => continue(e)
          }
        | Dot(x, l) =>
          switch (label(l)) {
          | Some(name) => {...e, term: Ap(Forward, F.var(name), go(x))}
          | None => continue(e)
          }
        | _ => continue(e)
        };
  go(exp);
};

let run_source = (~self: string="", src: string): option(ran) =>
  switch (
    PersistentZipper.parse_text(~source="fw", ~root=Exp, desugar(src))
  ) {
  | None => None
  | Some(z) =>
    let (exp, info, elab, casts) = with_casts(MakeTerm.from_zip_for_sem(z, ~root=Exp).term |> projections);   /* (x.f first, then casts) */
    let ty =
      switch (Id.Map.find_opt(Exp.rep_id(exp), info)) {
      | Some(InfoExp(i)) => Info.exp_ty(i)
      | _ => Typ.fresh(Unknown(Internal))
      };
    let env =
      Environment.extend(Builtins.env_init, ("pericopes", FwPrelude.all_value()));
    let env = Environment.extend(env, ("above", FwPrelude.neighbour(self, -1)));
    let env = Environment.extend(env, ("below", FwPrelude.neighbour(self, 1)));
    let env = Environment.extend(env, ("now", FwPrelude.now_value()));
    let env = Environment.extend(env, ("this", FwPrelude.this_value(self)));
    let env = Environment.extend(env, ("here", FwPrelude.here_value(self)));
    let env = Environment.extend(env, ("self", FwPrelude.self_value(self)));
    /* (the expression itself counts as being read while it runs: body(this), or of anything showing it, a hole) */
    let saved = FwPrelude.reading^;
    if (!String.is_empty(self) && !List.mem(saved, self, ~equal=String.equal)) {
      FwPrelude.reading := [self, ...saved];
    };
    let result =
      try(Evaluator.evaluate_and_limit(~step_limit, ~env, elab)) {
      | e =>
        FwPrelude.reading := saved;
        raise(e);
      };
    FwPrelude.reading := saved;
    switch (result) {
    | LimitedCompleted((value, _)) => Some({value, ty, info, too_long: false, casts})
    | StepLimitExceeded => Some({value: Exp.fresh(EmptyHole), ty, info, too_long: true, casts})
    };
  };

/* Whether a type is fw's Block (by name, or as its definition unrolled). */
let rec is_block_ty = (ty: Typ.t): bool =>
  switch (Typ.term_of(ty)) {
  | Var("Block") => true
  | Parens(t) => is_block_ty(t)
  | Rec(_, body) =>
    switch (Typ.term_of(body)) {
    | Sum(m) =>
      List.exists(
        ~f=
          fun
          | ConstructorMap.Variant("Paraphrase", _, _) => true
          | _ => false,
        m,
      )
    | _ => false
    }
  | _ => String.equal(Typ.pretty_print(ty), "Block")
  };

let rec is_arrow = (ty: Typ.t): bool =>
  switch (Typ.term_of(ty)) {
  | Arrow(_) => true
  | Parens(t) => is_arrow(t)
  | Poly(_, t) => is_arrow(t)
  | _ => false
  };

/* A Block value as a tree; a part not (yet) a Block (a hole) as printed. */
let rec tree = (d: Exp.t): Yojson.Safe.t => {
  let hole = () => `Assoc([("t", `String("hole")), ("printed", `String(print(d)))]);
  let s = x =>
    switch (Unboxing.unbox(Atom(String), x)) {
    | Matches(s) => Some(s)
    | _ => None
    };
  /* an Inline: (its words, Some(the Ref it links to)), or None (a hole) */
  let inline = x =>
    switch (Unboxing.unbox(SumWithArg("Plain"), x)) {
    | Matches(p) => Option.map(s(p), ~f=t => (t, None))
    | _ =>
      switch (Unboxing.unbox(SumWithArg("Link"), x)) {
      | Matches(l) =>
        switch (Unboxing.unbox(Tuple(2), l)) {
        | Matches([w, r]) =>
          switch (s(w), FwPrelude.id_of_ref(r)) {
          | (Some(t), Some(id)) => Some((t, Some(id)))
          | _ => None
          }
        | _ => None
        }
      | _ => None
      }
    };
  switch (Unboxing.unbox(SumWithArg("Text"), d)) {
  | Matches(a) =>
    switch (Unboxing.unbox(ListLit, a)) {
    | Matches(parts) =>
      let parts = List.map(~f=inline, parts);
      if (List.exists(~f=Option.is_none, parts)) {
        hole();
      } else {
        let (text, links, _) =
          List.fold(
            List.filter_opt(parts),
            ~init=("", [], 0),
            ~f=((text, links, at), (t, to_)) => {
              /* (a value's words as the page stores text: a dollar sign \$, never read back as code) */
              let t = String.substr_replace_all(t, ~pattern="$", ~with_="\\$");
              let e = at + String.length(t);
              let links =
                switch (to_) {
                | Some(id) => [`Assoc([("to", `String(id)), ("at", `List([`Int(at), `Int(e)]))]), ...links]
                | None => links
                };
              (text ++ t, links, e);
            },
          );
        `Assoc([("t", `String("text")), ("text", `String(text)), ("links", `List(List.rev(links)))]);
      };
    | _ => hole()
    }
  | _ =>
    switch (FwPrelude.from_parts(d)) {
    | Some((r, b)) =>
      switch (FwPrelude.id_of_ref(r)) {
      | Some(id) => `Assoc([("t", `String("from")), ("target", `String(id)), ("child", tree(b))])
      | None => hole()
      }
    | None =>
      switch (Unboxing.unbox(SumWithArg("Paraphrase"), d)) {
      | Matches(p) =>
        switch (Unboxing.unbox(Tuple(2), p)) {
        | Matches([r, t]) =>
          switch (FwPrelude.id_of_ref(r), s(t)) {
          | (Some(id), Some(t)) =>
            `Assoc([
              ("t", `String("paraphrase")),
              ("target", `String(id)),
              ("text", `String(t)),
            ])
          | _ => hole()
          }
        | _ => hole()
        }
      | _ =>
        switch (Unboxing.unbox(SumWithArg("Loop"), d)) {
        | Matches(r) =>
          switch (FwPrelude.id_of_ref(r)) {
          | Some(id) => `Assoc([("t", `String("loop")), ("target", `String(id))])
          | None => hole()
          }
        | _ =>
        switch (Unboxing.unbox(SumWithArg("Blocks"), d)) {
        | Matches(l) =>
          switch (Unboxing.unbox(ListLit, l)) {
          | Matches(kids) =>
            `Assoc([
              ("t", `String("blocks")),
              ("children", `List(List.map(~f=tree, kids))),
            ])
          | _ => hole()
          }
        | _ => hole()
        }
        }
      }
    }
  };
};

let errors_json = (info: Statics.Map.t): Yojson.Safe.t =>
  `List(
    Id.Map.fold(
      (_, i: Info.t, acc) => Info.is_error(i) ? [i, ...acc] : acc,
      info,
      [],
    )
    |> List.dedup_and_sort(~compare=Poly.compare)
    |> List.map(~f=i =>
         `Assoc([
           ("term", `String(ErrorPrint.term_string_of(i))),
           ("message", `String(named(ErrorPrint.string_of_marks(i, Info.marks_of(i))))),
         ])
       ),
  );

let rec answer = (~self: string="", src: string): Yojson.Safe.t => {
  FwPrelude.reads := [];
  if (String.is_substring(src, ~substring="now")) {
    FwPrelude.seen("now");
  };
  if (String.is_substring(src, ~substring="pericopes")) {
    FwPrelude.seen("*");
  };
  if (String.is_substring(src, ~substring="above") || String.is_substring(src, ~substring="below")) {
    /* (its peers: what's around it in its pericope, any change there) */
    Option.iter(Stdlib.Hashtbl.find_opt(FwPrelude.snapshot^.home, self), ~f=FwPrelude.seen);
  };
  let a = answer_(~self, src);
  let reads = List.dedup_and_sort(FwPrelude.reads^, ~compare=String.compare);
  switch (a) {
  | `Assoc(l) => `Assoc(l @ [("reads", `List(List.map(~f=x => `String(x), reads)))])
  | other => other
  };
}
and answer_ = (~self: string="", src: string): Yojson.Safe.t => {
  FwPrelude.looped := false;
  hole_mark := "?";
  let r = run_source(~self, src);
  if (FwPrelude.looped^) {
    hole_mark := "↻";
  };
  switch (r) {
  | None => `Assoc([("kind", `String("error")), ("message", `String("can't parse"))])
  | Some({too_long: true, _}) =>
    `Assoc([("kind", `String("error")), ("message", `String("∞ ran too long: it may never finish"))])
  | Some({value, ty, info, casts, _}) =>
    let casts_ =
      `List(List.map(casts, ~f=((c, f, t)) => `Assoc([("cast", `String(c)), ("from", `String(f)), ("to", `String(t))])));
    let typ = ("type", `String(is_block_ty(ty) ? "Block" : ty_string(ty)));
    let errors = ("errors", errors_json(info));
    let with_casts = j =>
      switch (j) {
      | `Assoc(l) when !List.is_empty(casts) => `Assoc(l @ [("casts", casts_)])
      | j => j
      };
    with_casts @@
    if (is_arrow(ty)) {
      `Assoc([("kind", `String("function")), typ, errors]);
    } else if (is_block_ty(ty)) {
      `Assoc([("kind", `String("block")), typ, ("block", tree(value)), errors]);
    } else {
      `Assoc(
        [("kind", `String("value")), typ, ("printed", `String(shown(value))), errors]
        @ (
          switch (items(value)) {
          | Some(l) => [("items", `List(List.map(~f=x => `String(x), l)))]
          | None => []
          }
        ),
      );
    };
  };
};

/* The store's own expressions, read by body(): a Block value, else None (a hole there). */
let () = {
  /* (an inline expression's value in its line, TYPE.md "Inline": a Ref its title (a Link), a string its words,
     anything else as fw prints it (a list its things, a Ref in it its title, a date pretty); blocks "!"; unparsable,
     ran too long or a hole "?") */
  let title_of = id =>
    switch (FwPrelude.facts_of(id)) {
    | Some(f) => f.ftitle
    | None => Option.value(Stdlib.Hashtbl.find_opt(FwPrelude.snapshot^.titles, id), ~default="?")
    };
  let titled_refs = (d: Exp.t): Exp.t =>
    Exp.map_term(
      ~f_exp=
        (continue, e) =>
          switch (FwPrelude.id_of_ref(e)) {
          | Some(id) => IdTagged.FreshGrammar.Exp.string(title_of(id))
          | None => continue(e)
          },
      d,
    );
  FwPrelude.inline_value :=
    (
      (self, src) =>
        switch (run_source(~self, src)) {
        | Some({value, ty, too_long: false, _}) =>
          if (is_block_ty(ty)) {
            Words("!");
          } else {
            let v = strip(value);
            switch (FwPrelude.id_of_ref(v)) {
            | Some(id) => Refer(title_of(id), id)
            | None =>
              switch (Unboxing.unbox(Atom(String), v)) {
              | Matches(w) => Words(w)
              | _ => Words(shown(titled_refs(v)))
              }
            };
          }
        | _ => Words("?")
        }
    );
  /* (an expression's words: what it shows, a Block's words or its printed value's) */
  FwPrelude.expr_words :=
    (
      (self, src) =>
        switch (run_source(~self, src)) {
        | Some({value, ty, too_long: false, _}) =>
          Some(
            is_block_ty(ty)
              ? FwPrelude.value_words(value)
              : FwPrelude.words_of_text(shown(value)),
          )
        | _ => None
        }
    );
  /* (a value as text, for asText (TYPE.md "Casting"): a reference its title, a date as fw writes one, a list its
     things with commas between, a string its words, anything else as Hazel prints it) */
  let rec text_of_value = (d: Exp.t): string => {
    let d = strip(pretty_dates(d));
    switch (FwPrelude.id_of_ref(d)) {
    | Some(id) => FwPrelude.title_of(id)
    | None =>
      switch (Unboxing.unbox(Atom(String), d)) {
      | Matches(s) => s
      | _ =>
        switch (Exp.term_of(d)) {
        | ListLit(l) => String.concat(~sep=", ", List.map(~f=text_of_value, l))
        | _ => print(d)
        }
      }
    };
  };
  FwPrelude.value_text := text_of_value;
  FwPrelude.eval_source :=
    (
      (self, src) =>
        switch (run_source(~self, src)) {
        | Some({value, ty, too_long: false, _}) when is_block_ty(ty) => Some(value)
        | _ => None
        }
    );
};

/* --- the page's function -------------------------------------------------------- */

let last: ref(option(Js.t(Js.js_string))) = ref(None);

let take_snapshot = (snap: Js.Optdef.t(Js.Opt.t(Js.t(Js.js_string)))) =>
  Js.Optdef.iter(snap, snap =>
    Js.Opt.iter(snap, s =>
      switch (last^) {
      | Some(prev) when Js.equals(prev, s) => ()
      | _ =>
        set_snapshot(Js.to_string(s));
        last := Some(s);
      }
    )
  );

let guard = (f: unit => Yojson.Safe.t): Js.t(Js.js_string) =>
  Js.string(
    try(Yojson.Safe.to_string(f())) {
    | e =>
      FwPrelude.reading := [];
      Yojson.Safe.to_string(
        `Assoc([("kind", `String("error")), ("message", `String(Exn.to_string(e)))]),
      );
    },
  );

let () =
  Js.export(
    "hazelPatch",
    Js.wrap_callback((s: Js.t(Js.js_string)) => {
      try(patch_snapshot(Js.to_string(s))) {
      | _ => ()
      };
      Js._true;
    }),
  );

let () = {
  Js.export(
    "hazelRun",
    Js.wrap_callback((s: Js.t(Js.js_string), snap, self: Js.Optdef.t(Js.t(Js.js_string)), here: Js.Optdef.t(Js.t(Js.js_string))) => {
      take_snapshot(snap);
      let self = Js.Optdef.case(self, () => "", Js.to_string);
      FwPrelude.viewer := Js.Optdef.case(here, () => "", Js.to_string);   /* (the page it's seen from: every run inside this one sees it too) */
      guard(() => answer(~self, Js.to_string(s)));
    }),
  );
};
