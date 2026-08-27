// ARK-S23-01. The research API is fail-closed behind an Owner bearer token.
// Roughly 140 BFF routes call fetch directly, so the token is attached once
// here instead of being copied into every route. It is injected only for the
// server-side research origin and never reaches the browser bundle.
export async function register() {
  const base = process.env.RESEARCH_API_URL;
  const token = process.env.RESEARCH_API_TOKEN;
  if (!base || !token) return;

  const original = globalThis.fetch;
  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (!url.startsWith(base)) return original(input, init);
    const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
    if (!headers.has("authorization")) headers.set("authorization", `Bearer ${token}`);
    return original(input, { ...init, headers });
  };
}
