// try-expr.mjs — the v1 expression language (src/expr.js) at a prompt, before it's in the editor:
// `node web/try-expr.mjs`, then type expressions; each shows what its block would show, and its type.
import { createInterface } from "node:readline";
import { run } from "./src/expr.js";

const rl = createInterface({ input: process.stdin, output: process.stdout, prompt: "expr › " });
console.log('the v1 expression language: Int, Float, String, Bool; + - * / ++ == != < <= > >= && || not; if … then … else\n(ctrl-d to leave)');
rl.prompt();
rl.on("line", (line) => {
  const r = run(line);
  if (!r.empty) console.log(`  ${r.text}${r.done ? `   : ${r.type}` : `   (unfinished${r.type !== "?" ? `, ${/^[AEIOU]/.test(r.type) ? "an" : "a"} ${r.type}` : ""})`}`);
  rl.prompt();
});
