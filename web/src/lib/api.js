// api.js — the page's one way to the core (fw_web.py): JSON over fetch. It counts what's in flight (the tests ask
// whether the page has settled: main.js's window.fw).
export const TEST = new URLSearchParams(location.search).has("test");   // (?test: the tests' quick timers, test.html)
export const inflight = { n: 0 };

export const api = async (path, opts = {}) => {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  inflight.n++;
  try {
    const r = await fetch(path, { ...opts, headers });
    const body = await r.json().catch(() => ({}));
    return { ok: r.ok, status: r.status, body };
  } finally {
    inflight.n--;
  }
};
