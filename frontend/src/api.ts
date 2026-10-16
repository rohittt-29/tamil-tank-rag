import type { DocumentMeta, SearchResponse } from './types'

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

export const searchChunks = (q: string) =>
  getJson<SearchResponse>(`/api/search?${new URLSearchParams({ q, limit: '20' })}`)

export const listDocuments = () => getJson<DocumentMeta[]>('/api/documents')
