import { API_INTERNAL_URL } from "./config";

// Server-side readiness check against the private api. Cached briefly so the root
// gate doesn't hammer the api on every render. The client poller (ReadinessGate)
// handles continuous polling — SSR alone can't poll.
export async function apiIsReady(): Promise<boolean> {
  try {
    const res = await fetch(`${API_INTERNAL_URL}/api/health`, {
      next: { revalidate: 2 },
    });
    if (!res.ok) return false;
    const data = await res.json();
    return data?.status === "ready";
  } catch {
    return false;
  }
}
