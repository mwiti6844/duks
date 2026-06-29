import { NextRequest } from "next/server";

// CSRF defense for cookie-backed mutations: require the request Origin (or Referer)
// host to match the Host header. Combined with SameSite=Lax cookies this blocks
// cross-site POSTs.
export function sameOrigin(req: NextRequest): boolean {
  const host = req.headers.get("host");
  if (!host) return false;
  const origin = req.headers.get("origin");
  if (origin) {
    try {
      return new URL(origin).host === host;
    } catch {
      return false;
    }
  }
  // Fall back to Referer when Origin is absent (some same-origin GETs/proxies).
  const referer = req.headers.get("referer");
  if (referer) {
    try {
      return new URL(referer).host === host;
    } catch {
      return false;
    }
  }
  // Cookie-backed mutations must carry browser provenance. Non-browser callers
  // should call the private API with Bearer auth rather than rely on this BFF.
  return false;
}
