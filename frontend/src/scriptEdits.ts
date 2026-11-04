import type { BoardSentence } from './api'

/** Directions live inside the script text, so the storyboard edits the script itself. */

interface Edit {
  start: number
  end: number
  text: string
}

function apply(script: string, edits: Edit[]) {
  return [...edits]
    .sort((a, b) => b.start - a.start)
    .reduce((out, e) => out.slice(0, e.start) + e.text + out.slice(e.end), script)
}

function clean(query: string) {
  return query.replace(/[[\]]/g, '').trim()
}

/** True when the sentence begins its own line, so a direction can sit on the line above it. */
function startsLine(script: string, at: number) {
  return at === 0 || script[at - 1] === '\n'
}

/** Remove a direction, plus the space after it, or its whole line if it stood alone. */
function removal(script: string, [start, end]: [number, number]): Edit {
  if (script[end] === ' ') return { start, end: end + 1, text: '' }
  if (script[end] === '\n' && startsLine(script, start)) return { start, end: end + 1, text: '' }
  if (script[start - 1] === ' ') return { start: start - 1, end, text: '' }
  return { start, end, text: '' }
}

/** Add a direction for a sentence: next to its other direction, on its own line, or inline. */
function insertion(script: string, s: BoardSentence, direction: string, other: [number, number] | null): Edit {
  if (other) return { start: other[1], end: other[1], text: ` ${direction}` }
  if (startsLine(script, s.start)) return { start: s.start, end: s.start, text: `${direction}\n` }
  return { start: s.start, end: s.start, text: `${direction} ` }
}

export function setQuery(script: string, s: BoardSentence, query: string) {
  const q = clean(query)
  if (s.hint_span) {
    return apply(script, [q ? { start: s.hint_span[0], end: s.hint_span[1], text: `[visual: ${q}]` } : removal(script, s.hint_span)])
  }
  if (!q) return script
  return apply(script, [insertion(script, s, `[visual: ${q}]`, s.pin_span)])
}

export function setQueries(script: string, sentences: BoardSentence[], queries: { index: number; query: string }[]) {
  const edits: Edit[] = []
  for (const { index, query } of queries) {
    const s = sentences[index]
    if (!s || s.hint_span || !clean(query)) continue
    edits.push(insertion(script, s, `[visual: ${clean(query)}]`, s.pin_span))
  }
  return apply(script, edits)
}

export function setPin(script: string, s: BoardSentence, id: number | null) {
  if (s.pin_span) {
    return apply(script, [id == null ? removal(script, s.pin_span) : { start: s.pin_span[0], end: s.pin_span[1], text: `[clip: ${id}]` }])
  }
  if (id == null) return script
  return apply(script, [insertion(script, s, `[clip: ${id}]`, s.hint_span)])
}
