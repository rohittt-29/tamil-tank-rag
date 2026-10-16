import { useEffect, useState, type FormEvent } from 'react'
import { listDocuments, searchChunks } from './api'
import { Snippet } from './Snippet'
import type { DocumentMeta, SearchMode, SearchResponse } from './types'

// ── Helpers (preserved from original) ───────────────────────────────
const MODES: { value: SearchMode; label: string; hint: string }[] = [
  { value: 'keyword',  label: 'Keyword',  hint: 'Exact words — all must appear' },
  { value: 'semantic', label: 'Semantic', hint: 'Similar meaning via embeddings' },
  { value: 'hybrid',   label: 'Hybrid',   hint: 'Keyword + semantic fused (RRF)' },
]

function citation(d: DocumentMeta) {
  const authors = d.authors.length > 2 ? `${d.authors[0]} et al.` : d.authors.join(' & ')
  return [authors, d.year && `(${d.year})`, d.source_org].filter(Boolean).join(' ')
}

function sourceLink(d: DocumentMeta, page?: number) {
  if (d.doi) return `https://doi.org/${d.doi}`
  if (d.source_url) return page ? `${d.source_url}#page=${page}` : d.source_url
  return null
}

// ── Inline SVG icons (zero dependency) ──────────────────────────────
function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="11" cy="11" r="7" />
      <line x1="16.5" y1="16.5" x2="22" y2="22" />
    </svg>
  )
}

function ExternalLinkIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </svg>
  )
}

function WaterIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="white" aria-hidden="true">
      <path d="M12 2C6.5 8 4 12.5 4 16a8 8 0 0 0 16 0c0-3.5-2.5-8-8-14z" />
    </svg>
  )
}

// ── Skeleton loader ──────────────────────────────────────────────────
function SkeletonResults() {
  return (
    <div role="status" aria-label="Loading results…">
      {[80, 65, 75].map((w, i) => (
        <div key={i} className="skeleton-card">
          <div className="skeleton skeleton-line skeleton-line--med" />
          <div className="skeleton skeleton-line" />
          <div className="skeleton skeleton-line" style={{ width: `${w}%` }} />
          <div style={{ marginTop: 8 }}>
            <div className="skeleton skeleton-line skeleton-line--title" />
            <div className="skeleton skeleton-line skeleton-line--short" style={{ marginTop: 6 }} />
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Main component ───────────────────────────────────────────────────
export default function App() {
  const [query,   setQuery]   = useState('')
  const [mode,    setMode]    = useState<SearchMode>('keyword')
  const [result,  setResult]  = useState<SearchResponse | null>(null)
  const [docs,    setDocs]    = useState<DocumentMeta[]>([])
  const [error,   setError]   = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)

  // Load document collection on mount — same as original
  useEffect(() => {
    listDocuments()
      .then(setDocs)
      .catch((e: Error) => setError(`Could not load document list: ${e.message}`))
  }, [])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    setHasSearched(true)
    try {
      setResult(await searchChunks(query.trim(), mode))
    } catch (err) {
      setError(`Search failed: ${(err as Error).message}`)
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  const doneCount = docs.filter(d => d.status === 'done').length

  return (
    <div className="app-shell">
      {/* ── Top navigation ── */}
      <nav className="top-nav" aria-label="Site navigation">
        <div className="top-nav__inner">
          <a href="/" className="nav-brand" aria-label="Eri Knowledge home">
            <span className="nav-brand__mark" aria-hidden="true">
              <WaterIcon />
            </span>
            <span className="nav-brand__name">Eri Knowledge</span>
            <span className="nav-brand__sep" aria-hidden="true">|</span>
            <span className="nav-brand__sub">Tamil Water-Management Archive</span>
          </a>
          <div className="nav-spacer" />
          {docs.length > 0 && (
            <span className="nav-badge" aria-label={`${doneCount} documents indexed`}>
              {doneCount} doc{doneCount === 1 ? '' : 's'} indexed
            </span>
          )}
        </div>
      </nav>

      {/* ── Main content ── */}
      <main className="page-content" id="main-content">

        {/* Search hero */}
        <section className="search-hero" aria-labelledby="search-heading">
          <div className="search-hero__eyebrow" aria-hidden="true">
            Traditional Knowledge Repository
          </div>
          <h1 id="search-heading">
            Tamil Tank Irrigation<br />Knowledge Search
          </h1>
          <p className="search-hero__sub">
            Search a curated collection of academic and historical documents on
            traditional Tamil <em>eri</em> (tank) irrigation. Every result
            shows the source document and page number.
          </p>

          {/* Search form — same onSubmit, same API params */}
          <form onSubmit={onSubmit} className="search-form" role="search" aria-label="Knowledge search">
            <div className="search-bar">
              <input
                id="search-input"
                className="search-bar__input"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder='e.g. tank cascade, "kudimaramathu", desilting methods'
                aria-label="Search query"
                autoComplete="off"
                spellCheck="false"
              />
              <button
                type="submit"
                className="search-bar__btn"
                disabled={loading}
                aria-label={loading ? 'Searching…' : 'Search'}
              >
                <SearchIcon />
                {loading ? 'Searching…' : 'Search'}
              </button>
            </div>

            {/* Mode selector */}
            <div className="mode-row" role="group" aria-label="Search mode">
              <span className="mode-row__label" id="mode-label">Mode</span>
              <div className="mode-pills" aria-labelledby="mode-label">
                {MODES.map((m) => (
                  <label key={m.value} className="mode-pill" title={m.hint}>
                    <input
                      type="radio"
                      name="search-mode"
                      value={m.value}
                      checked={mode === m.value}
                      onChange={() => setMode(m.value)}
                      aria-label={`${m.label} — ${m.hint}`}
                    />
                    <span className="mode-pill__label">
                      <span className={`mode-dot mode-dot--${m.value}`} aria-hidden="true" />
                      {m.label}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          </form>
        </section>

        {/* ── Error state ── */}
        {error && (
          <div className="status-banner status-banner--error" role="alert">
            <span className="status-banner__icon" aria-hidden="true">⚠</span>
            <span className="status-banner__body">{error}</span>
          </div>
        )}

        {/* ── Loading state ── */}
        {loading && <SkeletonResults />}

        {/* ── Warning from backend ── */}
        {!loading && result?.warning && (
          <div className="status-banner status-banner--warning" role="status">
            <span className="status-banner__icon" aria-hidden="true">⚡</span>
            <span className="status-banner__body">{result.warning}</span>
          </div>
        )}

        {/* ── Results ── */}
        {!loading && result && (
          <section aria-label="Search results" aria-live="polite">
            <div className="results-header">
              <h2>Results</h2>
              <span className="results-header__meta">
                {result.total} passage{result.total === 1 ? '' : 's'} for &ldquo;{result.query}&rdquo;
              </span>
              <span className="results-header__tag">
                {result.method} search
              </span>
            </div>

            {result.hits.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state__icon" aria-hidden="true">🔍</div>
                <h3>No passages found</h3>
                <p>
                  Try different keywords, switch to Semantic mode for broader
                  matching, or check for typos.
                </p>
              </div>
            ) : (
              <ol className="hit-list" aria-label={`${result.hits.length} search results`}>
                {result.hits.map((h, idx) => {
                  const link = sourceLink(h.document, h.page_number)
                  return (
                    <li key={h.chunk_id} className="hit-card">
                      <span className="hit-card__rank" aria-label={`Result ${idx + 1}`}>
                        #{idx + 1}
                      </span>

                      <Snippet text={h.snippet} />

                      <div className="hit-meta">
                        <div className="hit-meta__title">{h.document.title}</div>
                        <div className="hit-meta__attrs">
                          <span>{citation(h.document)}</span>
                          <span className="hit-meta__sep" aria-hidden="true">·</span>
                          <span className="hit-meta__page" aria-label={`Page ${h.page_number}${h.document.page_count ? ` of ${h.document.page_count}` : ''}`}>
                            p.&nbsp;{h.page_number}
                            {h.document.page_count ? `/${h.document.page_count}` : ''}
                          </span>
                          {h.document.language && (
                            <>
                              <span className="hit-meta__sep" aria-hidden="true">·</span>
                              <span>{h.document.language}</span>
                            </>
                          )}
                          {h.document.license && (
                            <>
                              <span className="hit-meta__sep" aria-hidden="true">·</span>
                              <span className="hit-meta__license">{h.document.license}</span>
                            </>
                          )}
                          {link && (
                            <>
                              <span className="hit-meta__sep" aria-hidden="true">·</span>
                              <a
                                href={link}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="hit-meta__link"
                                aria-label={`Open original source for "${h.document.title}" (opens in new tab)`}
                              >
                                Original source
                                <ExternalLinkIcon />
                              </a>
                            </>
                          )}
                        </div>
                      </div>
                    </li>
                  )
                })}
              </ol>
            )}
          </section>
        )}

        {/* ── No search yet — informational nudge ── */}
        {!loading && !result && !error && hasSearched === false && docs.length > 0 && (
          <div className="status-banner status-banner--info" role="status">
            <span className="status-banner__icon" aria-hidden="true">💡</span>
            <span className="status-banner__body">
              Enter a query above to search {docs.length} document{docs.length === 1 ? '' : 's'} in the
              collection. Use <strong>Keyword</strong> for exact terms,{' '}
              <strong>Semantic</strong> for concept-based retrieval, or{' '}
              <strong>Hybrid</strong> to combine both.
            </span>
          </div>
        )}

        {/* ── Document collection ── */}
        {docs.length > 0 && (
          <section className="collection-section" aria-labelledby="collection-heading">
            <div className="section-header">
              <h2 id="collection-heading">Collection</h2>
              <span className="section-header__count">
                {docs.length} document{docs.length === 1 ? '' : 's'}
              </span>
            </div>

            <ul className="doc-list" aria-label="Document collection">
              {docs.map((d) => (
                <li key={d.id} className="doc-item">
                  <div className="doc-item__status" aria-label={`Status: ${d.status}`}>
                    <span className={`status-dot status-dot--${d.status}`} aria-hidden="true" />
                  </div>
                  <div className="doc-item__body">
                    <div className="doc-item__title" title={d.title}>{d.title}</div>
                    <div className="doc-item__meta">
                      <span>{citation(d)}</span>
                      {d.language && (
                        <>
                          <span aria-hidden="true">·</span>
                          <span>{d.language}</span>
                        </>
                      )}
                      <span aria-hidden="true">·</span>
                      <span>{d.status}</span>
                    </div>
                    {d.error && (
                      <div className="doc-item__error" role="alert">
                        ⚠ {d.error}
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}
      </main>

      {/* ── Footer ── */}
      <footer className="app-footer">
        <span>
          Tamil Tank Irrigation Knowledge Search &mdash; Traditional{' '}
          <em>eri</em> water-management archive.
          Search powered by PostgreSQL full-text and pgvector semantic search.
        </span>
      </footer>
    </div>
  )
}
