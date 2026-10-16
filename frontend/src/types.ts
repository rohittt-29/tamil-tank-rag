// Mirrors the Pydantic models in backend/app/main.py.

export interface DocumentMeta {
  id: number
  source_key: string
  title: string
  authors: string[]
  year: number | null
  language: string
  source_org: string | null
  source_url: string | null
  doi: string | null
  license: string | null
  page_count: number | null
  status: 'pending' | 'processing' | 'done' | 'failed'
  error: string | null
}

export interface SearchHit {
  chunk_id: number
  page_number: number
  section: 'body' | 'references'
  snippet: string
  score: number
  document: DocumentMeta
}

export interface SearchResponse {
  query: string
  method: string
  total: number
  hits: SearchHit[]
}
