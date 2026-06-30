// Cookie-based route gating ONLY (no health polling — middleware runs per request
// and is the wrong place for readiness). Readiness is handled by the root page's
// SSR check + client poller.
import { NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE } from "@/lib/config";

export function middleware(req: NextRequest) {
  const hasSession = req.cookies.get(SESSION_COOKIE)?.value === "1";
  const { pathname } = req.nextUrl;

  if (
    (pathname.startsWith("/chat") || pathname.startsWith("/my-listings")
      || pathname.startsWith("/listings/"))
    && !hasSession
  ) {
    return NextResponse.redirect(new URL("/login", req.url));
  }
  if (pathname === "/login" && hasSession) {
    return NextResponse.redirect(new URL("/chat", req.url));
  }
  return NextResponse.next();
}

export const config = {
  // Gate the app routes; skip api, static, and the readiness root.
  matcher: ["/chat/:path*", "/my-listings/:path*", "/listings/:path*", "/login"],
};
