/** Script revision paper colours, in industry order. Each shot takes one, everywhere it appears. */
export const REVISIONS = [
  { name: 'Blue', hex: '#b9d3f0' },
  { name: 'Pink', hex: '#f6bacb' },
  { name: 'Yellow', hex: '#f4e18b' },
  { name: 'Green', hex: '#bce2b0' },
  { name: 'Goldenrod', hex: '#efc264' },
  { name: 'Salmon', hex: '#f6a98f' },
  { name: 'Buff', hex: '#eedcbb' },
  { name: 'Tan', hex: '#d8b796' },
] as const

export function shotColor(index: number) {
  return REVISIONS[((index % REVISIONS.length) + REVISIONS.length) % REVISIONS.length].hex
}
