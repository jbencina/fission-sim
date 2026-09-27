/**
 * ConfirmDialog — a simple modal confirmation overlay.
 *
 * Renders a blurred scrim with a centered card containing a title, message,
 * and two action buttons (Cancel / Confirm). The Confirm button can
 * optionally be rendered in "danger" red styling.
 *
 * Behaviour:
 *   - Closes on Escape key press.
 *   - Closes on backdrop click.
 *   - Focuses the Confirm button when opened.
 *   - Keeps Tab / Shift+Tab inside the dialog while it is open, so keyboard
 *     users cannot wander into the page behind the scrim.
 *   - Returns focus to whatever was focused before (usually the button that
 *     opened it) when it closes.
 *   - No external library dependencies — pure React.
 *
 * @module ConfirmDialog
 */

import { type FC, useEffect, useRef } from 'react'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface ConfirmDialogProps {
  /** Whether the dialog is visible. */
  open: boolean
  /** Bold heading text shown at the top of the card. */
  title: string
  /** Explanatory body text. */
  message: string
  /** Label for the confirm button. Defaults to "Confirm". */
  confirmLabel?: string
  /**
   * When true the confirm button is rendered with red destructive styling
   * to signal a dangerous or irreversible action.
   */
  danger?: boolean
  /** Called when the user clicks the Confirm button. */
  onConfirm: () => void
  /** Called when the user clicks Cancel, the backdrop, or presses Escape. */
  onCancel: () => void
}

// ---------------------------------------------------------------------------
// ConfirmDialog component
// ---------------------------------------------------------------------------

/** Elements that can receive keyboard focus inside the dialog card. */
const FOCUSABLE_SELECTOR =
  'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), ' +
  'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/**
 * ConfirmDialog
 *
 * A lightweight modal dialog.  Mount it anywhere — it uses a fixed overlay so
 * stacking context is not an issue.  Render `open={false}` to hide without
 * unmounting.
 *
 * Props:
 *   open         — show/hide the dialog
 *   title        — heading text
 *   message      — body text explaining the action
 *   confirmLabel — button label (default "Confirm")
 *   danger       — if true, confirm button is red
 *   onConfirm    — called on confirm click
 *   onCancel     — called on cancel, backdrop click, or Escape
 */
const ConfirmDialog: FC<ConfirmDialogProps> = ({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  danger = false,
  onConfirm,
  onCancel,
}) => {
  // Ref to the confirm button so we can focus it programmatically on open.
  const confirmRef = useRef<HTMLButtonElement>(null)
  // Ref to the card, used to find the focusable elements Tab cycles through.
  const cardRef = useRef<HTMLDivElement>(null)

  // Focus the confirm button whenever the dialog opens, and put focus back
  // where it was when the dialog closes (or unmounts while open).
  useEffect(() => {
    if (!open) return
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null
    // Small timeout ensures the element is rendered and visible before focus.
    const id = window.setTimeout(() => confirmRef.current?.focus(), 0)
    return () => {
      window.clearTimeout(id)
      // The restored control may become disabled moments later (SCRAM does
      // once the reactor reports scrammed); the browser then drops focus.
      previouslyFocused?.focus()
    }
  }, [open])

  // Keyboard handling while open: Escape cancels; Tab wraps within the card.
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onCancel()
        return
      }
      if (e.key !== 'Tab' || cardRef.current === null) return

      const focusable = Array.from(
        cardRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      )
      if (focusable.length === 0) {
        // Nothing to cycle through: still keep Tab from leaving the dialog.
        e.preventDefault()
        return
      }
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const active = document.activeElement
      const inside = active instanceof Node && cardRef.current.contains(active)

      // Wrap at either end, and pull focus back in if it is somewhere else.
      if (e.shiftKey && (active === first || !inside)) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && (active === last || !inside)) {
        e.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onCancel])

  // Render nothing when closed.
  if (!open) return null

  const confirmClass = danger
    ? 'bg-danger hover:bg-danger-hover text-white'
    : 'bg-accent hover:bg-accent-hover text-accent-ink'

  return (
    /*
     * Fullscreen overlay with a blurred scrim. Clicking the scrim cancels;
     * clicks inside the card stop propagation so they never dismiss it.
     */
    <div
      className="fixed inset-0 z-50 flex animate-fade-in items-center justify-center bg-black/40 p-4 backdrop-blur-[2px]"
      onClick={onCancel}
      aria-modal="true"
      role="dialog"
      aria-labelledby="confirm-dialog-title"
      aria-describedby="confirm-dialog-message"
    >
      <div
        ref={cardRef}
        className="w-full max-w-[26rem] animate-pop-in rounded-2xl border border-line bg-raised p-5 shadow-pop"
        onClick={(e) => e.stopPropagation()}
      >
        <h2
          id="confirm-dialog-title"
          className="text-[17px] font-semibold tracking-[-0.01em] text-ink"
        >
          {title}
        </h2>
        <p id="confirm-dialog-message" className="mt-2 text-[13px] leading-relaxed text-ink-2">
          {message}
        </p>

        <div className="mt-5 grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="h-10 rounded-[10px] bg-surface-2 text-[13px] font-medium text-ink transition-colors hover:bg-surface-3"
          >
            Cancel
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={onConfirm}
            className={`h-10 rounded-[10px] text-[13px] font-semibold transition-colors ${confirmClass}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

export default ConfirmDialog
