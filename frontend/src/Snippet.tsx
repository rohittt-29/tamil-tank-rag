// The backend wraps matched words in \u0002 ... \u0003. We split on those
// markers and render <mark> elements, so we never inject raw HTML.
const START = '\u0002'
const STOP  = '\u0003'

export function Snippet({ text }: { text: string }) {
  const parts = text.split(START)
  return (
    <p className="snippet">
      {parts.map((part, i) => {
        if (i === 0) return <span key={i}>{part}</span>
        const [hit, rest = ''] = part.split(STOP)
        return (
          <span key={i}>
            <mark>{hit}</mark>
            {rest}
          </span>
        )
      })}
    </p>
  )
}
