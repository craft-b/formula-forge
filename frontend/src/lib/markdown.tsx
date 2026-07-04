import { Fragment, type ReactNode } from "react"

// Minimal, XSS-safe inline markdown → React. Handles **bold**, *italic*,
// `code`, line breaks, and "- " / "* " bullet lists. Deliberately small and
// dependency-free (no dangerouslySetInnerHTML): the backend only emits simple
// markdown, and this keeps the CSP tight. Replaces the old raw-text rendering
// that showed literal ** asterisks (audit finding F11).

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = []
  // Split on bold, italic, and code spans while keeping the delimiters.
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g)
  parts.forEach((part, i) => {
    if (!part) return
    const key = `${keyPrefix}-${i}`
    if (part.startsWith("**") && part.endsWith("**")) {
      nodes.push(<strong key={key}>{part.slice(2, -2)}</strong>)
    } else if (part.startsWith("`") && part.endsWith("`")) {
      nodes.push(
        <code key={key} className="px-1 py-0.5 rounded bg-slate-100 text-[0.85em] text-slate-700">
          {part.slice(1, -1)}
        </code>
      )
    } else if (part.startsWith("*") && part.endsWith("*")) {
      nodes.push(<em key={key}>{part.slice(1, -1)}</em>)
    } else {
      nodes.push(<Fragment key={key}>{part}</Fragment>)
    }
  })
  return nodes
}

export function Markdown({ text }: { text: string }) {
  const lines = text.split("\n")
  const blocks: ReactNode[] = []
  let bullets: string[] = []

  const flushBullets = (key: string) => {
    if (bullets.length === 0) return
    blocks.push(
      <ul key={key} className="list-disc pl-5 space-y-0.5 my-1">
        {bullets.map((b, i) => (
          <li key={i}>{renderInline(b, `${key}-${i}`)}</li>
        ))}
      </ul>
    )
    bullets = []
  }

  lines.forEach((line, i) => {
    const trimmed = line.trim()
    if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      bullets.push(trimmed.slice(2))
    } else {
      flushBullets(`ul-${i}`)
      if (trimmed) {
        blocks.push(
          <p key={`p-${i}`} className="my-1 first:mt-0 last:mb-0">
            {renderInline(trimmed, `p-${i}`)}
          </p>
        )
      }
    }
  })
  flushBullets("ul-end")

  return <>{blocks}</>
}
