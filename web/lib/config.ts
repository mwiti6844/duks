// Server-only runtime config. API_INTERNAL_URL must never be exposed to the client.
export const API_INTERNAL_URL =
  process.env.API_INTERNAL_URL || "http://localhost:8000";

export const TOKEN_COOKIE = "carduka_token";
export const SESSION_COOKIE = "carduka_session"; // non-sensitive presence cookie
