// ask.js — a question in the page (the terminal's "y to delete"), not the browser's dialog: Enter or y says yes,
// anything else no. The question is state (ui.asking); App.svelte shows Ask.svelte while there is one.
import { ui } from "./state.svelte.js";

/** `question` asked; resolves true for Enter or y. */
export function ask(question, yes = "↵ or y: yes · anything else: no") {
  return new Promise((resolve) => {
    const was = document.activeElement;
    ui.asking = { question, yes, answer: (a) => { ui.asking = null; was?.focus?.(); resolve(a); } };
  });
}
