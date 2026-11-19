// float.svelte.js — a box floating at a place on the page (the terminal's menus open at the cursor): a component
// mounted on the body, its props a rune, so whoever opened it can change them and it follows. `dismiss(back)` takes
// it down (back: the focus returned with `refocus`); dismissing twice is nothing.
import { mount, unmount } from "svelte";

/** `Component` floated just under `at` (a ProseMirror coordsAtPos, or a DOMRect) with `props`. Returns
 * {props, dismiss, open}. */
export function float(Component, at, props, refocus = null) {
  let view = null;
  const p = $state({
    ...props,
    left: Math.max(8, at.left + window.scrollX),
    top: at.bottom + window.scrollY + 4,
    dismiss: (back = true) => {
      if (view) { const v = view; view = null; unmount(v); }
      if (back) refocus?.();
    },
  });
  view = mount(Component, { target: document.body, props: p });
  return { props: p, dismiss: p.dismiss, get open() { return !!view; } };
}
