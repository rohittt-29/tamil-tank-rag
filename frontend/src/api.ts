import type { DocumentMeta, SearchMode, SearchResponse } from './types'

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) {
    // FastAPI puts a readable reason in "detail" (e.g. "Run: python -m app.embed").
    const body = await res.json().catch(() => null)
    const detail = typeof body?.detail === 'string' ? body.detail : res.statusText
    throw new Error(`${res.status} ${detail}`)
  }
  return res.json() as Promise<T>
}

export const searchChunks = (q: string, mode: SearchMode = 'keyword') =>
  getJson<SearchResponse>(`/api/search?${new URLSearchParams({ q, mode, limit: '20' })}`)

export const listDocuments = () => getJson<DocumentMeta[]>('/api/documents')
