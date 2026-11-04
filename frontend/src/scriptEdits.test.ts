import { describe, expect, it } from 'vitest'
import type { BoardSentence } from './api'
import { setPin, setQueries, setQuery } from './scriptEdits'

/**
 * A storyboard sentence as the server would describe it: offsets of the sentence and of the
 * [visual: …] / [clip: …] directions that belong to it (the nearest ones before it).
 */
function sentence(script: string, text: string, index = 0): BoardSentence {
  const start = script.indexOf(text)
  if (start < 0) throw new Error(`"${text}" is not in the script`)
  const before = script.slice(0, start)
  const previousEnd = Math.max(0, before.lastIndexOf('.') + 1)
  const span = (pattern: RegExp): [number, number] | null => {
    let found: [number, number] | null = null
    for (const m of before.slice(previousEnd).matchAll(pattern)) found = [previousEnd + m.index!, previousEnd + m.index! + m[0].length]
    return found
  }
  const hint_span = span(/\[visual:[^\]]*\]/g)
  const pin_span = span(/\[clip:[^\]]*\]/g)
  return {
    index,
    text,
    hint: hint_span ? script.slice(hint_span[0] + 8, hint_span[1] - 1).trim() : null,
    pin: pin_span ? Number(script.slice(pin_span[0] + 6, pin_span[1] - 1)) : null,
    start,
    end: start + text.length,
    hint_span,
    pin_span,
    query: '',
    query_source: 'keywords',
  }
}

const SCRIPT = `# Walking

[visual: park at sunrise]
A walk helps your brain.

It raises your heart rate. Then it calms you down.`

describe('locking clips', () => {
  it('puts the lock on its own line above a sentence that starts a line, and removes it cleanly', () => {
    const locked = setPin(SCRIPT, sentence(SCRIPT, 'It raises your heart rate.'), 42)
    expect(locked).toContain('\n[clip: 42]\nIt raises your heart rate.')
    expect(setPin(locked, sentence(locked, 'It raises your heart rate.'), null)).toBe(SCRIPT)
  })

  it('joins an existing direction line', () => {
    const locked = setPin(SCRIPT, sentence(SCRIPT, 'A walk helps your brain.'), 7)
    expect(locked).toContain('[visual: park at sunrise] [clip: 7]\nA walk')
    expect(setPin(locked, sentence(locked, 'A walk helps your brain.'), null)).toBe(SCRIPT)
  })

  it('goes inline for a sentence in the middle of a line', () => {
    const locked = setPin(SCRIPT, sentence(SCRIPT, 'Then it calms you down.'), 9)
    expect(locked).toContain('heart rate. [clip: 9] Then it calms')
    expect(setPin(locked, sentence(locked, 'Then it calms you down.'), null)).toBe(SCRIPT)
  })

  it('swaps one locked clip for another in place', () => {
    const locked = setPin(SCRIPT, sentence(SCRIPT, 'It raises your heart rate.'), 42)
    const swapped = setPin(locked, sentence(locked, 'It raises your heart rate.'), 43)
    expect(swapped).toBe(locked.replace('[clip: 42]', '[clip: 43]'))
  })
})

describe('footage searches', () => {
  it('replaces an existing search and restores it', () => {
    const changed = setQuery(SCRIPT, sentence(SCRIPT, 'A walk helps your brain.'), 'jogger on a bridge')
    expect(changed).toContain('[visual: jogger on a bridge]\nA walk')
    expect(setQuery(changed, sentence(changed, 'A walk helps your brain.'), 'park at sunrise')).toBe(SCRIPT)
  })

  it('adds a search on its own line and clearing it restores the script', () => {
    const added = setQuery(SCRIPT, sentence(SCRIPT, 'It raises your heart rate.'), 'heart monitor')
    expect(added).toContain('\n[visual: heart monitor]\nIt raises')
    expect(setQuery(added, sentence(added, 'It raises your heart rate.'), '')).toBe(SCRIPT)
  })

  it('strips brackets so a search can never break the script', () => {
    const added = setQuery(SCRIPT, sentence(SCRIPT, 'It raises your heart rate.'), 'heart [monitor]')
    expect(added).toContain('[visual: heart monitor]')
  })

  it('writes suggestions only for sentences without a search', () => {
    const sentences = [sentence(SCRIPT, 'A walk helps your brain.', 0), sentence(SCRIPT, 'It raises your heart rate.', 1)]
    const out = setQueries(SCRIPT, sentences, [
      { index: 0, query: 'ignored' },
      { index: 1, query: 'pulse check' },
    ])
    expect(out).not.toContain('ignored')
    expect(out).toContain('[visual: pulse check]\nIt raises')
  })
})
