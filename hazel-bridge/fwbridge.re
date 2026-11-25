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
let shown = (v: Exp.t): string => {
  let v = strip(pretty_dates(v));
  let item = x =>
    switch (Unboxing.unbox(Atom(String), strip(x))) {
    | Matches(s) => s
    | _ => print(x)
    };
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

/* --- running a source ------------------------------------------------------------------ */

type ran = {
  value: Exp.t,
  ty: Typ.t,
  info: Statics.Map.t,
  too_long: bool /* ran out of steps: it may never finish (a hole stands for its value) */
};

/* Steps one run may take (the user, 2026-11-25: "a relatively short step limit"): a program that would run on (a
   recursion with no end) stops there and shows ∞, never freezing the page. Each expression read through another
   (body, wordCount) gets its own. */
let step_limit = 100000;

let ctx = Builtins.ctx_init(Some(Operators.default_mode));

let run_source = (~self: string="", src: string): option(ran) =>
  switch (
    PersistentZipper.parse_text(~source="fw", ~root=Exp, desugar(src))
  ) {
  | None => None
  | Some(z) =>
    let exp = MakeTerm.from_zip_for_sem(z, ~root=Exp).term;
    let (info, elab) = Statics.mk(CoreSettings.on, ctx, exp);
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
    | LimitedCompleted((value, _)) => Some({value, ty, info, too_long: false})
    | StepLimitExceeded => Some({value: Exp.fresh(EmptyHole), ty, info, too_long: true})
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

let answer = (~self: string="", src: string): Yojson.Safe.t => {
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
  | Some({value, ty, info, _}) =>
    let typ = ("type", `String(is_block_ty(ty) ? "Block" : ty_string(ty)));
    let errors = ("errors", errors_json(info));
    if (is_arrow(ty)) {
      `Assoc([("kind", `String("function")), typ, errors]);
    } else if (is_block_ty(ty)) {
      `Assoc([("kind", `String("block")), typ, ("block", tree(value)), errors]);
    } else {
      `Assoc([("kind", `String("value")), typ, ("printed", `String(shown(value))), errors]);
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
