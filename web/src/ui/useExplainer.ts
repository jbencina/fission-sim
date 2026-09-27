/**
 * useExplainer — open/close state for an explanation popover.
 *
 * An explanation opens three ways, so it works with a mouse, a keyboard and
 * a touch screen:
 *   - hovering its area with a mouse (after a short delay, so sweeping the
 *     pointer across a list does not flash every popover),
 *   - keyboard focus (`:focus-visible`) on its control, and
 *   - clicking or tapping its info button, which pins it open until tapped
 *     again, Escape, a tap elsewhere, or focus moving away.
 * Escape also hides an explanation opened by focus, until focus moves.
 */

import {
  type FocusEvent,
  type KeyboardEvent,
  type PointerEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react'

/** Default delay before a mouse hover opens the explanation [ms]. */
export const HOVER_DELAY_MS = 250

function isFocusVisible(el: EventTarget | null): boolean {
  if (!(el instanceof Element)) return false
  try {
    return el.matches(':focus-visible')
  } catch {
    return true
  }
}

export function useExplainer(hoverDelayMs: number = HOVER_DELAY_MS) {
  const [hovered, setHovered] = useState(false)
  const [focused, setFocused] = useState(false)
  const [pinned, setPinned] = useState(false)
  const [dismissed, setDismissed] = useState(false)
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => () => window.clearTimeout(timer.current), [])

  const onPointerEnter = useCallback((e: PointerEvent | globalThis.PointerEvent) => {
    if (e.pointerType !== 'mouse') return
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setHovered(true), hoverDelayMs)
  }, [hoverDelayMs])

  const onPointerLeave = useCallback(() => {
    window.clearTimeout(timer.current)
    setHovered(false)
    setDismissed(false)
  }, [])

  const onFocus = useCallback((e: FocusEvent) => {
    if (isFocusVisible(e.target)) setFocused(true)
  }, [])

  const onBlur = useCallback(() => {
    setFocused(false)
    setPinned(false)
    setDismissed(false)
  }, [])

  const onKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      setPinned(false)
      setDismissed(true)
    }
  }, [])

  const togglePinned = useCallback(() => {
    setDismissed(false)
    setPinned((p) => !p)
  }, [])

  return {
    open: !dismissed && (hovered || focused || pinned),
    pinned,
    setPinned,
    togglePinned,
    hoverHandlers: { onPointerEnter, onPointerLeave },
    focusHandlers: { onFocus, onBlur, onKeyDown },
  }
}
