import { NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE, TOKEN_COOKIE } from "@/lib/config";
import { sameOrigin } from "@/lib/csrf";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  if (!sameOrigin(req)) {
    return NextResponse.json({ detail: "CSRF check failed" }, { status: 403 });
  }
  const res = NextResponse.json({ ok: true });
  res.cookies.delete(TOKEN_COOKIE);
  res.cookies.delete(SESSION_COOKIE);
  return res;
}
