import { useEffect, useState, type FormEvent } from 'react'
import { listDocuments, searchChunks } from './api'
import { Snippet } from './Snippet'
import type { DocumentMeta, SearchResponse } from './types'

function citation(d: DocumentMeta) {
  const authors = d.authors.length > 2 ? `${d.authors[0]} et al.` : d.authors.join(' & ')
  return [authors, d.year && `(${d.year})`, d.source_org].filter(Boolean).join(' ')
}

function sourceLink(d: DocumentMeta, page?: number) {
  if (d.doi) return `https://doi.org/${d.doi}`
  if (d.source_url) return page ? `${d.source_url}#page=${page}` : d.source_url
  return null
}

export default function App() {
  const [query, setQuery] = useState('')
  const [result, setResult] = useState<SearchResponse | null>(null)
  const [docs, setDocs] = useState<DocumentMeta[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    listDocuments().then(setDocs).catch((e: Error) => setError(`Could not load documents: ${e.message}`))
  }, [])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    try {
      setResult(await searchChunks(query.trim()))
    } catch (err) {
      setError(`Search failed: ${(err as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main>
      <header>
        <h1>Tamil Tank Irrigation Knowledge Search</h1>
        <p className="muted">
          Search a curated collection of documents on traditional Tamil tank (eri) irrigation. Every result
          shows the document and page it came from.
        </p>
      </header>

      <form onSubmit={onSubmit} className="search">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder='e.g. tank cascade, "kudimaramathu", desilting -groundwater'
          aria-label="Search query"
        />
        <button disabled={loading}>{loading ? 'Searching…' : 'Search'}</button>
      </form>

      {error && <p className="error">{error}</p>}

      {result && (
        <section>
          <p className="muted">
            {result.total} matching passage{result.total === 1 ? '' : 's'} for “{result.query}” ({result.method}{' '}
            search)
          </p>
          <ol className="hits">
            {result.hits.map((h) => {
              const link = sourceLink(h.document, h.page_number)
              return (
                <li key={h.chunk_id} className="hit">
                  <Snippet text={h.snippet} />
                  <div className="source">
                    <strong>{h.document.title}</strong>
                    <span>
                      {citation(h.document)} · page {h.page_number}
                      {h.document.page_count ? ` of ${h.document.page_count}` : ''}
                    </span>
                    <span>
                      {h.document.license && `${h.document.license} · `}
                      {link && (
                        <a href={link} target="_blank" rel="noreferrer">
                          original source
                        </a>
                      )}
                    </span>
                  </div>
                </li>
              )
            })}
          </ol>
        </section>
      )}

      <section className="collection">
        <h2>Collection ({docs.length} document{docs.length === 1 ? "" : "s"})</h2>
        <ul>
          {docs.map((d) => (
            <li key={d.id}>
              {d.title} <span className="muted">— {citation(d)} · {d.language} · {d.status}</span>
              {d.error && <span className="error"> ({d.error})</span>}
            </li>
          ))}
        </ul>
      </section>
    </main>
  )
}
