// step.svelte.js — one step between pericopes (motion.js runs it): how far along each of its beats is, a Svelte Tween
// from 0 to 1, and one effect that turns those numbers into the live elements' styles, every frame. Nothing is drawn
// in their place: the header and the blocks are the page's own (one page); only while the page underneath changes
// does a copy of the frame (the ghost) stand where it was.
//
// The beats' numbers, and what each moves:
//   hide   the tabs, the numbers, the ↗s, the lines fade out
//   veil   everything but the block the step goes through fades out, the header too
//   widen  that block's sides go out to the page's (no text moves: the boxes holding text take it as padding)
//   room   the ghost grows to (or shrinks into) the block taking its place on the other page
//   show   that block is there, under the ghost, and the ghost fades off it
import { Tween } from "svelte/motion";
import { cubicInOut } from "svelte/easing";

export const BEATS = ["hide", "veil", "widen", "room", "show"];
const SWITCHES = new Set(["show"]);   // (switched on or off at once, no fade: the ghost's hand-over)
const FADES = new Set(["hide", "veil"]);   // (fading: the tabs, the header and the blocks)
const BOXED = ["marginLeft", "marginRight", "opacity"];

export class Step {
  // what it moves ({header, stem, host, quote}: `host` the page's .fw-doc, Svelte's (the beats' numbers go on it as
  // variables: ProseMirror redraws its own elements when anything else changes them); `quote` a quote the step goes
  // through (a quote's element is its own view's, so it can be styled), what was measured of it at
  // rest ({left, right}: how far its sides go out), the ghost ({wrap, quote, quoteHeight, move, grow, shift}) and the
  // block coming in under it: state, so the effect draws again when they change
  els = $state.raw({});
  g = $state.raw(null);
  ghost = $state.raw(null);
  arriving = $state.raw(null);
  touched = new Set();   // (every frame and block it's styled: their styles taken off at the end)

  constructor(els, duration, fade = duration) {
    this.els = els;
    this.t = Object.fromEntries(BEATS.map((b) => [b, new Tween(0, { duration: FADES.has(b) ? fade : duration, easing: cubicInOut })]));
    this.stop = $effect.root(() => { $effect(() => this.draw()); });
  }

  /** Beat `name` to `to` (1: done, 0: undone), animated; at once with `now`. */
  go(name, to, now = false) { return this.t[name].set(to, now || SWITCHES.has(name) ? { duration: 0 } : {}); }

  /** Every beat's number, as styles (the effect: it runs again whenever one moves). */
  draw() {
    const v = Object.fromEntries(BEATS.map((b) => [b, this.t[b].current]));
    const { header, stem, host, quote } = this.els, g = this.g;
    document.documentElement.style.setProperty("--step-hide", v.hide);
    for (const e of [header, stem]) if (e) e.style.opacity = String(1 - v.veil);
    // (the block coming in is there whole, under the ghost, from the moment it starts to show: only the ghost fades, so
    // where the two are alike nothing dims, no flicker)
    const shown = v.show > 0 ? 1 : 0;
    if (host) { this.touched.add(host); host.style.setProperty("--step-veil", v.veil); host.style.setProperty("--step-show", shown); }
    if (g && quote) {
      this.touched.add(quote);
      quote.style.marginLeft = `${-v.widen * g.left}px`;
      quote.style.marginRight = `${-v.widen * g.right}px`;
      quote.style.setProperty("--grow-l", `${v.widen * g.left}px`);
      quote.style.setProperty("--grow-r", `${v.widen * g.right}px`);
    }
    const gh = this.ghost;
    if (gh) {
      gh.wrap.style.transform = `translateY(${v.room * gh.move}px)`;
      gh.quote.style.height = `${gh.quoteHeight + v.room * gh.grow}px`;   // (growing, or shrinking: cut as it goes)
      gh.quote.style.overflow = "hidden";
      gh.wrap.style.setProperty("--shift", `${v.room * gh.shift}px`);
      gh.wrap.style.opacity = String(1 - v.show);
    }
    if (this.arriving) { this.touched.add(this.arriving); this.arriving.style.opacity = String(shown); }
  }

  /** Done: the effect stopped, every style it set taken off. */
  end() {
    this.stop();
    document.documentElement.style.removeProperty("--step-hide");
    const { header, stem } = this.els;
    for (const e of [header, stem]) if (e) e.style.opacity = "";
    for (const e of this.touched) { for (const k of BOXED) e.style[k] = ""; for (const k of ["--step-veil", "--step-show", "--grow-l", "--grow-r"]) e.style.removeProperty(k); }
    this.ghost?.wrap.remove();
  }
}
