// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { Popover } from './ui'

afterEach(cleanup)

function Console() {
  return (
    // The bottom console scrolls sideways, which clips anything positioned inside it.
    <div data-testid="console" style={{ overflow: 'auto', height: 40 }}>
      <Popover trigger={(open) => <button aria-expanded={open}>Voice</button>}>
        <button>Inside the panel</button>
      </Popover>
      <span>Elsewhere</span>
    </div>
  )
}

describe('Popover', () => {
  it('opens outside any clipping container', () => {
    render(<Console />)
    fireEvent.click(screen.getByText('Voice'))
    const panel = screen.getByRole('dialog')
    expect(screen.getByTestId('console').contains(panel)).toBe(false)
    expect(document.body.contains(panel)).toBe(true)
    expect(screen.getByText('Voice').getAttribute('aria-expanded')).toBe('true')
  })

  it('stays open for clicks inside it and closes on outside clicks and Escape', () => {
    render(<Console />)
    fireEvent.click(screen.getByText('Voice'))
    fireEvent.pointerDown(screen.getByText('Inside the panel'))
    expect(screen.queryByRole('dialog')).not.toBeNull()

    act(() => {
      fireEvent.pointerDown(screen.getByText('Elsewhere'))
    })
    expect(screen.queryByRole('dialog')).toBeNull()

    fireEvent.click(screen.getByText('Voice'))
    act(() => {
      fireEvent.keyDown(document, { key: 'Escape' })
    })
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('toggles from its trigger', () => {
    render(<Console />)
    fireEvent.click(screen.getByText('Voice'))
    fireEvent.click(screen.getByText('Voice'))
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})
