// Root gate: SSR readiness check, then route to /chat or /login based on the
// session-presence cookie. If the api isn't ready, render the client poller.
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import ReadinessGate from "@/components/ReadinessGate";
import { SESSION_COOKIE } from "@/lib/config";
import { apiIsReady } from "@/lib/health";

export const dynamic = "force-dynamic";

export default async function Home() {
  const ready = await apiIsReady();
  if (!ready) {
    return <ReadinessGate />;
  }
  const hasSession = (await cookies()).get(SESSION_COOKIE)?.value === "1";
  redirect(hasSession ? "/chat" : "/login");
}
