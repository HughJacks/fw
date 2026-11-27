// build.mjs — the page built into dist/ (app.js, app.css): `npm run build`. dist/ is all fw_web serves,
// so once built it works offline.
import { build } from "esbuild";
import sveltePlugin from "esbuild-svelte";
import { execFileSync } from "node:child_process";
import { copyFileSync } from "node:fs";

// (the page is Svelte 5 components with runes, every one compiled in runes mode, even one that uses no
// rune (else Svelte reads it the old way); their CSS joins app.js's bundle as app.css's sibling)
await build({ entryPoints: ["src/main.js"], bundle: true, format: "esm", minify: true, sourcemap: true,
  outfile: "dist/app.js", target: "es2022", logLevel: "warning", mainFields: ["svelte", "browser", "module", "main"],
  conditions: ["svelte", "browser"], plugins: [sveltePlugin({ compilerOptions: { css: "injected", runes: true } })] });
execFileSync("npx", ["tailwindcss", "-i", "src/app.css", "-o", "dist/app.css", "--minify"], { stdio: ["ignore", "ignore", "inherit"] });
// the typeface (Source Sans 3, a humanist sans; OFL), served beside the page so it works offline
const FONTS = "node_modules/@fontsource-variable/source-sans-3/files/";
for (const f of ["latin", "latin-ext"].flatMap((s) => [`source-sans-3-${s}-wght-normal.woff2`, `source-sans-3-${s}-wght-italic.woff2`])) copyFileSync(FONTS + f, "dist/" + f);
// the expression engine (the expr branch: Hazel's, with fw's prelude, compiled by the hazel copy's fw/build.sh into vendor/), loaded by
// the page after it opens (hazel.js), so nothing waits on it
import { existsSync, readFileSync, writeFileSync } from "node:fs";
if (existsSync("vendor/hazel.js")) writeFileSync("dist/hazel.js", readFileSync("vendor/hazel.js"));   // (its bytes, not its read-only mode)
console.log("built dist/app.js, dist/app.css, the fonts, the expression engine");
