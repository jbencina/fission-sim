/**
 * Hook for sliders that preview locally and commit on native `change`.
 *
 * React fires `onChange` for range inputs on every input event. The operator
 * controls need the browser's native `change` timing instead: once when a drag
 * is released, or once per keyboard step.
 */

import { type ChangeEvent, type RefObject, useEffect, useRef, useState } from 'react'

export interface CommittedRange {
  /** Attach to the `<input type="range">` that should commit on release. */
  ref: RefObject<HTMLInputElement>
  /** Local preview value [same units as the backend value]. */
  value: number
  /** Call from React `onChange` to update the local preview while dragging. */
  onChange: (event: ChangeEvent<HTMLInputElement>) => void
  /** Imperatively set the preview, used for bumpless mode toggles. */
  setValue: (value: number) => void
}

/**
 * Keep a range input local while dragging, then commit on release.
 *
 * Parameters
 * ----------
 * backendValue:
 *   Value from the latest telemetry frame [same units as the slider].
 * onCommit:
 *   Callback invoked with the input's finite numeric value on native `change`.
 *
 * Returns
 * -------
 * CommittedRange
 *   Ref, local value and input handlers for the range control.
 */
export function useCommittedRange(backendValue: number, onCommit: (value: number) => void): CommittedRange {
  const ref = useRef<HTMLInputElement>(null)
  const [value, setValue] = useState(backendValue)
  const draggingRef = useRef(false)
  const backendRef = useRef(backendValue)
  backendRef.current = backendValue

  useEffect(() => {
    if (!draggingRef.current) setValue(backendValue)
  }, [backendValue])

  useEffect(() => {
    const el = ref.current
    if (!el) return

    const commit = () => {
      draggingRef.current = false
      const parsed = Number.parseFloat(el.value)
      if (Number.isFinite(parsed)) onCommit(parsed)
    }

    let pending: number | undefined
    const release = () => {
      window.clearTimeout(pending)
      pending = window.setTimeout(() => {
        if (!draggingRef.current) return
        draggingRef.current = false
        setValue(backendRef.current)
      }, 0)
    }

    el.addEventListener('change', commit)
    el.addEventListener('pointerup', release)
    el.addEventListener('pointercancel', release)
    el.addEventListener('blur', release)
    return () => {
      window.clearTimeout(pending)
      el.removeEventListener('change', commit)
      el.removeEventListener('pointerup', release)
      el.removeEventListener('pointercancel', release)
      el.removeEventListener('blur', release)
    }
  }, [onCommit])

  return {
    ref,
    value,
    onChange: (event) => {
      draggingRef.current = true
      setValue(Number.parseFloat(event.target.value))
    },
    setValue,
  }
}
