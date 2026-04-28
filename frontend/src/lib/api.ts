const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

interface FetchOptions extends RequestInit {
  noAuth?: boolean;
  cache_ttl?: number; // Cache TTL in ms (0 = no cache)
}

// Simple in-memory cache for GET requests
const _cache = new Map<string, { data: unknown; expires: number }>();

export async function api<T = unknown>(
  path: string,
  opts: FetchOptions = {}
): Promise<T> {
  const { noAuth, cache_ttl, ...fetchOpts } = opts;
  const method = (fetchOpts.method || "GET").toUpperCase();

  // Check cache for GET requests
  if (method === "GET" && cache_ttl && cache_ttl > 0) {
    const cached = _cache.get(path);
    if (cached && cached.expires > Date.now()) {
      return cached.data as T;
    }
  }

  const headers = new Headers(fetchOpts.headers);

  if (!noAuth) {
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("access_token")
        : null;
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  if (!headers.has("Content-Type") && fetchOpts.body) {
    headers.set("Content-Type", "application/json; charset=utf-8");
  }

  // Accept UTF-8 responses
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json; charset=utf-8");
  }

  const res = await fetch(`${API_BASE}${path}`, { ...fetchOpts, headers });

  if (res.status === 401 && typeof window !== "undefined") {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("user");
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }

  const data = await res.json();

  // Store in cache for GET requests
  if (method === "GET" && cache_ttl && cache_ttl > 0) {
    _cache.set(path, { data, expires: Date.now() + cache_ttl });
  }

  return data;
}

/** Invalidate cached entries matching a path prefix */
export function invalidateCache(pathPrefix?: string) {
  if (!pathPrefix) {
    _cache.clear();
    return;
  }
  for (const key of _cache.keys()) {
    if (key.startsWith(pathPrefix)) {
      _cache.delete(key);
    }
  }
}

export function wsUrl(path: string): string {
  if (!API_BASE && typeof window !== "undefined") {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.hostname}:1000${path}`;
  }
  const base = (API_BASE || "http://localhost:1000").replace(/^http/, "ws");
  return `${base}${path}`;
}
