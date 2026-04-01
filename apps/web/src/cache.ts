type CacheEntry<T> = {
  data: T
  timestamp: number
}

const store = new Map<string, CacheEntry<unknown>>()

const DEFAULT_TTL_MS = 30_000 // 30 seconds

export function cacheGet<T>(key: string, ttlMs: number = DEFAULT_TTL_MS): T | undefined {
  const entry = store.get(key)
  if (!entry) return undefined
  if (Date.now() - entry.timestamp > ttlMs) {
    store.delete(key)
    return undefined
  }
  return entry.data as T
}

export function cacheSet<T>(key: string, data: T): void {
  store.set(key, { data, timestamp: Date.now() })
}

export function cacheInvalidate(keyPrefix: string): void {
  for (const key of store.keys()) {
    if (key.startsWith(keyPrefix)) {
      store.delete(key)
    }
  }
}

export function cacheClear(): void {
  store.clear()
}

export async function cachedFetch<T>(
  key: string,
  fetcher: () => Promise<T>,
  ttlMs: number = DEFAULT_TTL_MS
): Promise<T> {
  const cached = cacheGet<T>(key, ttlMs)
  if (cached !== undefined) return cached
  const data = await fetcher()
  cacheSet(key, data)
  return data
}
