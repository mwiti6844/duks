// Login route: forwards credentials to the api service, then stores the returned
// opaque JWT in an HTTP-only cookie. The web tier never inspects or verifies the JWT.
import { NextRequest, NextResponse } from "next/server";

import { API_INTERNAL_URL, SESSION_COOKIE, TOKEN_COOKIE } from "@/lib/config";
import { sameOrigin } from "@/lib/csrf";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  if (!sameOrigin(req)) {
    return NextResponse.json({ detail: "CSRF check failed" }, { status: 403 });
  }
  const body = await req.json().catch(() => null);
  if (!body?.username || !body?.password) {
    return NextResponse.json({ detail: "username and password required" }, { status: 400 });
  }

  const upstream = await fetch(`${API_INTERNAL_URL}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: body.username, password: body.password }),
    cache: "no-store",
  });
  const data = await upstream.json().catch(() => ({}));
  if (!upstream.ok) {
    return NextResponse.json(data, { status: upstream.status });
  }

  const res = NextResponse.json({ user: data.user });
  const secure = process.env.NODE_ENV === "production";
  // Path=/ so middleware on "/" can see the cookie; HttpOnly keeps the JWT opaque.
  res.cookies.set(TOKEN_COOKIE, data.token, {
    httpOnly: true,
    sameSite: "lax",
    secure,
    path: "/",
    maxAge: 60 * 60 * 12,
  });
  // Non-sensitive presence cookie for fast client/middleware gating.
  res.cookies.set(SESSION_COOKIE, "1", {
    httpOnly: false,
    sameSite: "lax",
    secure,
    path: "/",
    maxAge: 60 * 60 * 12,
  });
  return res;
}
