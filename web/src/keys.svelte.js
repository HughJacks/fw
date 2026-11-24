// keys.svelte.js (keys.js re-exports it) — the web editor's keys, as data (as fw_keys.py is the terminal's): each command, what it does, where it
// works, and its key; the user's own bindings (#/keys, kept by the core beside the store: web-keys.json) over the
// defaults. Since 2026-11-18 the defaults are a Mac app's (⌘), no longer the terminal's Ctrl, and stay off the keys
// a browser keeps for itself (⌘T, ⌘W, ⌘L, ⌘Q, ⌘M, ⌘N, ⌘⇧T, …). Key names are ProseMirror's ("Mod-Shift-e": Mod is ⌘
// on a Mac, Ctrl elsewhere).
import { api } from "./api.js";

/** The commands that have keys: id, what it does (as the bindings page says it), where, and its default. */
export const COMMANDS = [
  { id: "menu", label: "The actions menu: what can be done here", where: "editor", key: "Mod-/" },
  { id: "open", label: "Open it (a quote's source, a link, a paraphrase's source)", where: "editor", key: "Mod-o" },
  { id: "popout", label: "Turn into a quote (the block, or the selection, a pericope of its own)", where: "editor", key: "Mod-e" },
  { id: "popopen", label: "Turn into a quote and open it", where: "editor", key: "Mod-Shift-e" },
  { id: "detach", label: "Turn into text (a quote: a plain copy, no longer live)", where: "editor", key: "Mod-Alt-t" },
  { id: "link", label: "Link to a pericope (the selection)", where: "editor", key: "Mod-k" },
  { id: "unlink", label: "Remove link", where: "editor", key: "Mod-Shift-k" },
  { id: "mask", label: "Create or edit mask (a quote)", where: "editor", key: "Mod-Shift-m" },
  { id: "showall", label: "Remove mask", where: "editor", key: "Mod-Alt-m" },
  { id: "lock", label: "Lock or unlock writing through (a quote)", where: "editor", key: "Mod-Shift-l" },
  { id: "code", label: "An expression's code: shown and edited, the result dim below (again: hidden)", where: "editor", key: "Mod-Shift-x" },
  { id: "nest", label: "A block inside the block (split at the cursor, a level down)", where: "editor", key: "Mod-Enter" },
  { id: "delete", label: "Delete this pericope (asked first)", where: "editor", key: "Mod-Shift-Backspace" },
  { id: "done", label: "Send it away: saved, off the top of the screen, and home (done for now; not back)", where: "editor", key: "Mod-Shift-Enter" },
  { id: "back", label: "Step out: back where you were (the trail Open it makes)", where: "everywhere", key: "Mod-[" },
  { id: "forward", label: "Step in again: forward along the trail", where: "everywhere", key: "Mod-]" },
  { id: "home", label: "Home", where: "everywhere", key: "Mod-Shift-h" },
  { id: "keys", label: "This page: the keys", where: "everywhere", key: "Mod-Shift-," },
  { id: "kinds", label: "The tags view: every tag, and what's tagged", where: "everywhere", key: "Mod-Shift-u" },
  { id: "kindYes", label: "Yes, it has this tag (a guess, in a tag's list)", where: "kinds", key: "y" },
  { id: "kindNo", label: "No, it hasn't (a guess, or one of yours taken out, in a tag's list)", where: "kinds", key: "n" },
  { id: "kindDelete", label: "Delete the tag selected, in the tags view (asked first)", where: "kinds", key: "Mod-Backspace" },
  { id: "deleteHome", label: "Delete the pericope selected, on home (asked first)", where: "home", key: "Mod-Backspace" },
];

/** Keys a browser keeps for itself (a page can't have them, or shouldn't). */
export const KEPT = new Set(["Mod-t", "Mod-w", "Mod-n", "Mod-q", "Mod-l", "Mod-m", "Mod-h", "Mod-Shift-t", "Mod-Shift-n", "Mod-Shift-w",
  "Mod-r", "Mod-Shift-r", "Mod-Tab", "Mod-Shift-Tab", "Mod-1", "Mod-2", "Mod-3", "Mod-4", "Mod-5", "Mod-6", "Mod-7", "Mod-8", "Mod-9",
  "Mod-p", "Mod-f", "Mod-c", "Mod-v", "Mod-x", "Mod-a", "Mod-z", "Mod-Shift-z", "Mod-y", "Mod-Shift-v"]);

// the user's bindings, {command id: key name}: a rune, so whatever shows a key follows a change at once (2026-11-18)
const bound = $state({ mine: {} });
export async function loadKeys() { const r = await api("/api/keys"); if (r.ok) bound.mine = r.body.keys || {}; }
export async function saveKeys(next) {
  bound.mine = next;
  await api("/api/keys", { method: "PUT", body: JSON.stringify({ keys: bound.mine }) });
}
export const userKeys = () => ({ ...bound.mine });

/** Command `id`'s key now (the user's, else the default). */
export function keyOf(id) {
  return bound.mine[id] || COMMANDS.find((c) => c.id === id)?.key || null;
}

const mac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

/** A key event's name, as ProseMirror names keys ("Mod-Shift-e"), or null for a modifier alone. */
export function nameOf(e) {
  if (["Shift", "Control", "Alt", "Meta"].includes(e.key)) return null;
  let base = e.key === " " ? "Space" : e.key;
  if (base.length === 1) base = (e.shiftKey && /[A-Z]/.test(base) ? base.toLowerCase() : base.toLowerCase());
  if (e.code && /^Key[A-Z]$/.test(e.code)) base = e.code.slice(3).toLowerCase();   // (⌥ and ⇧ change e.key; the key itself)
  if (e.code === "Comma") base = ",";
  if (e.code === "Slash") base = "/";
  if (e.code === "BracketLeft") base = "[";
  if (e.code === "BracketRight") base = "]";
  const parts = [];
  if (mac ? e.metaKey : e.ctrlKey) parts.push("Mod");
  if (mac && e.ctrlKey) parts.push("Ctrl");
  if (e.altKey) parts.push("Alt");
  if (e.shiftKey) parts.push("Shift");
  return [...parts, base].join("-");
}

/** Whether key event `e` is command `id`'s key. */
export const pressed = (e, id) => nameOf(e) === keyOf(id);

/** A key name as a Mac shows it: "Mod-Shift-e" → "⌘⇧E". */
export function pretty(name) {
  if (!name) return "";
  const parts = name.split("-"), base = parts.pop() || "-";
  const sym = { Mod: mac ? "⌘" : "Ctrl+", Ctrl: "⌃", Alt: mac ? "⌥" : "Alt+", Shift: "⇧" };
  const keys = { Enter: "↵", Backspace: "⌫", Delete: "⌦", Escape: "esc", ArrowUp: "↑", ArrowDown: "↓", ArrowLeft: "←", ArrowRight: "→", Space: "space", Tab: "⇥" };
  return parts.map((p) => sym[p] || p).join("") + (keys[base] || base.toUpperCase());
}
