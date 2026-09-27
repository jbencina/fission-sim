/**
 * Popover — a floating explanation panel positioned next to an anchor.
 *
 * Rendered into document.body with fixed positioning, so a scrolling
 * sidebar or a chart card never clips it. It flips above the anchor when
 * there is no room below and stays inside the viewport horizontally.
 *
 * The panel is always mounted, transparent while closed, so that
 * `aria-describedby` on the control it explains always resolves and screen
 * readers read the explanation on focus. It never takes pointer events.
 */

import { type FC, type ReactNode, useCallback, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

export interface PopoverProps {
  id: string
  open: boolean
  anchor: HTMLElement | null
  /** Horizontal alignment to the anchor: its left edge, right edge, or centre. */
  align?: 'start' | 'end' | 'center'
  /** Preferred side; flips when there is no room. */
  side?: 'bottom' | 'top'
  children: ReactNode
}

const GAP = 8
const EDGE = 8

const Popover: FC<PopoverProps> = ({ id, open, anchor, align = 'start', side = 'bottom', children }) => {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)

  const place = useCallback(() => {
    const el = ref.current
    if (!el || !anchor) return
    const a = anchor.getBoundingClientRect()
    const w = el.offsetWidth
    const h = el.offsetHeight
    const vw = window.innerWidth
    const vh = window.innerHeight

    let left = align === 'end' ? a.right - w : align === 'center' ? a.left + a.width / 2 - w / 2 : a.left
    left = Math.min(Math.max(EDGE, left), vw - w - EDGE)

    const below = a.bottom + GAP
    const above = a.top - GAP - h
    let top = side === 'bottom' ? below : above
    if (side === 'bottom' && below + h > vh - EDGE && above >= EDGE) top = above
    if (side === 'top' && above < EDGE && below + h <= vh - EDGE) top = below
    top = Math.max(EDGE, top)

    setPos((p) => (p && p.top === top && p.left === left ? p : { top, left }))
  }, [anchor, align, side])

  useLayoutEffect(() => {
    if (!open) return
    place()
    window.addEventListener('scroll', place, true)
    window.addEventListener('resize', place)
    return () => {
      window.removeEventListener('scroll', place, true)
      window.removeEventListener('resize', place)
    }
  }, [open, place])

  return createPortal(
    <div
      ref={ref}
      id={id}
      role="tooltip"
      style={pos ? { top: pos.top, left: pos.left } : { top: 0, left: 0 }}
      className={[
        'pointer-events-none fixed z-[60] w-72 max-w-[calc(100vw-16px)]',
        'border border-line-strong bg-raised p-3 shadow-pop',
        'text-[12.5px] leading-relaxed text-ink-2',
        'transition-[opacity,transform] duration-150 ease-smooth',
        open && pos ? 'translate-y-0 opacity-100' : 'translate-y-0.5 opacity-0',
      ].join(' ')}
    >
      {children}
    </div>,
    document.body,
  )
}

export default Popover
