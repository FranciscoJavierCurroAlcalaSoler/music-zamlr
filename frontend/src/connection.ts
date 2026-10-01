declare global {
  var __ZAMLR__: { apiBase?: string; token?: string } | undefined;
}

export const TOKEN_HEADER = "X-Zamlr-Token";

export function apiBase(): string {
  return (
    globalThis.__ZAMLR__?.apiBase ??
    import.meta.env.VITE_API_BASE ??
    "http://localhost:8000"
  );
}

export function authHeaders(): Record<string, string> {
  const token = globalThis.__ZAMLR__?.token;
  return token ? { [TOKEN_HEADER]: token } : {};
}
