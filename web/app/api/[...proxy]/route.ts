// Streaming BFF proxy. Forwards /api/* to the private api service, injecting the
// opaque JWT from the HTTP-only cookie as a Bearer token. Streams responses
// (including SSE) straight through. CSRF-checks mutations.
import { NextRequest } from "next/server";

import { API_INTERNAL_URL, SESSION_COOKIE, TOKEN_COOKIE } from "@/lib/config";
import { sameOrigin } from "@/lib/csrf";

export const dynamic = "force-dynamic";

const MUTATING = new Set(["POST", "PUT", "PATCH", "DELETE"]);

async function handle(req: NextRequest, ctx: { params: Promise<{ proxy: string[] }> }) {
  if (MUTATING.has(req.method) && !sameOrigin(req)) {
    return new Response(JSON.stringify({ detail: "CSRF check failed" }), {
      status: 403,
      headers: { "content-type": "application/json" },
    });
  }

  const { proxy } = await ctx.params;
  const search = req.nextUrl.search;
  const target = `${API_INTERNAL_URL}/api/${proxy.join("/")}${search}`;

  const token = req.cookies.get(TOKEN_COOKIE)?.value;
  const headers = new Headers();
  const contentType = req.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const accept = req.headers.get("accept");
  if (accept) headers.set("accept", accept);
  if (token) headers.set("authorization", `Bearer ${token}`);

  const body =
    req.method === "GET" || req.method === "HEAD"
      ? undefined
      : await req.arrayBuffer();

  const upstream = await fetch(target, {
    method: req.method,
    headers,
    body,
    // @ts-expect-error - duplex is required by Node fetch for streaming bodies
    duplex: "half",
    cache: "no-store",
  });

  const respHeaders = new Headers();
  const ct = upstream.headers.get("content-type");
  if (ct) respHeaders.set("content-type", ct);
  respHeaders.set("cache-control", "no-store");
  if (upstream.status === 401) {
    respHeaders.append(
      "set-cookie",
      `${TOKEN_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax`,
    );
    respHeaders.append(
      "set-cookie",
      `${SESSION_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax`,
    );
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: respHeaders,
  });
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
