/**
 * ConfirmDialog — a simple modal confirmation overlay.
 *
 * Renders a fullscreen dark overlay with a centered card containing a title,
 * message, and two action buttons (Cancel / Confirm). The Confirm button can
 * optionally be rendered in "danger" red styling.
 *
 * Behaviour:
 *   - Closes on Escape key press.
 *   - Closes on backdrop click.
 *   - Focuses the Confirm button when opened.
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
   * (bg-red-600) to signal a dangerous or irreversible action.
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

  // Focus the confirm button whenever the dialog opens.
  useEffect(() => {
    if (open) {
      // Small timeout ensures the element is rendered and visible before focus.
      const id = window.setTimeout(() => confirmRef.current?.focus(), 0)
      return () => window.clearTimeout(id)
    }
  }, [open])

  // Close on Escape key.
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onCancel])

  // Render nothing when closed.
  if (!open) return null

  const confirmClass = danger
    ? 'bg-red-600 hover:bg-red-500 focus:ring-red-500 text-white'
    : 'bg-sky-600 hover:bg-sky-500 focus:ring-sky-500 text-white'

  return (
    /*
     * Fullscreen fixed overlay.
     * bg-black/60 gives a semi-transparent dark scrim behind the card.
     * z-50 ensures the dialog floats above all other content.
     * Clicking the backdrop calls onCancel (the onClick is on the overlay div,
     * but we stop propagation on the card itself to prevent accidental dismissal).
     */
    <div
      className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
      onClick={onCancel}
      aria-modal="true"
      role="dialog"
      aria-labelledby="confirm-dialog-title"
    >
      {/* Centered card — stop propagation so clicks inside do NOT close the dialog */}
      <div
        className="bg-slate-900 border border-slate-700 rounded-2xl p-6 max-w-md w-full shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Title */}
        <h2
          id="confirm-dialog-title"
          className="text-lg font-bold text-slate-100 mb-2"
        >
          {title}
        </h2>

        {/* Message body */}
        <p className="text-sm text-slate-300 leading-relaxed mb-6">{message}</p>

        {/* Action buttons — right-aligned */}
        <div className="flex justify-end gap-3">
          {/* Cancel — secondary neutral style */}
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-slate-700 hover:bg-slate-600 text-slate-200 transition-colors focus:outline-none focus:ring-2 focus:ring-slate-500"
          >
            Cancel
          </button>

          {/* Confirm — primary or danger style depending on props */}
          <button
            ref={confirmRef}
            type="button"
            onClick={onConfirm}
            className={`px-4 py-2 rounded-lg text-sm font-bold transition-colors focus:outline-none focus:ring-2 ${confirmClass}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

export default ConfirmDialog
