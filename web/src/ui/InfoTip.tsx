/**
 * Explanation popovers for the dashboard's educational copy.
 *
 * - `InfoTip`: a small ⓘ button. Hovering it (or the tile/row it belongs
 *   to), focusing it with the keyboard, or tapping it shows the explanation.
 * - `HelpTip`: wraps an operator control; its explanation shows on hover and
 *   on keyboard focus, and is linked to the control with aria-describedby.
 */

import {
  type FC,
  type ReactNode,
  type RefObject,
  useEffect,
  useId,
  useRef,
  useState,
} from 'react'
import Popover from './Popover'
import { InfoIcon } from './icons'
import { useExplainer } from './useExplainer'

const PopoverBody: FC<{ title?: string; children: ReactNode }> = ({ title, children }) => (
  <>
    {title && <p className="mb-1 text-[13px] font-semibold leading-snug text-ink">{title}</p>}
    <div>{children}</div>
  </>
)

export interface InfoTipProps {
  title: string
  body: ReactNode
  /** Accessible name of the button; defaults to "About {title}". */
  label?: string
  align?: 'start' | 'end' | 'center'
  side?: 'bottom' | 'top'
  /**
   * The tile or row the button belongs to: hovering it also opens the
   * explanation, and the popover lines up with it instead of the icon.
   */
  area?: RefObject<HTMLElement>
  className?: string
  /**
   * Custom button content (a badge, a readout) instead of the ⓘ icon. The
   * content then names the button, and `className` styles it entirely.
   */
  children?: ReactNode
}

export const InfoTip: FC<InfoTipProps> = ({
  title,
  body,
  label,
  align = 'start',
  side = 'bottom',
  area,
  className = '',
  children,
}) => {
  const id = useId()
  const buttonRef = useRef<HTMLButtonElement>(null)
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  const { open, pinned, setPinned, togglePinned, hoverHandlers, focusHandlers } = useExplainer()
  const { onPointerEnter, onPointerLeave } = hoverHandlers

  useEffect(() => {
    const el = area?.current ?? buttonRef.current
    setAnchor(el)
    if (!el) return
    el.addEventListener('pointerenter', onPointerEnter)
    el.addEventListener('pointerleave', onPointerLeave)
    return () => {
      el.removeEventListener('pointerenter', onPointerEnter)
      el.removeEventListener('pointerleave', onPointerLeave)
    }
  }, [area, onPointerEnter, onPointerLeave])

  // Touch browsers (notably Safari) do not always focus a tapped button, so
  // blur alone cannot close a pinned tip: a tap anywhere else also closes it.
  useEffect(() => {
    if (!pinned) return
    const el = area?.current ?? buttonRef.current
    const close = (e: PointerEvent) => {
      if (!el?.contains(e.target as Node)) setPinned(false)
    }
    document.addEventListener('pointerdown', close)
    return () => document.removeEventListener('pointerdown', close)
  }, [pinned, area, setPinned])

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        aria-label={children ? label : (label ?? `About ${title}`)}
        aria-describedby={id}
        onClick={togglePinned}
        {...focusHandlers}
        className={
          children
            ? className
            : [
                '-m-1 inline-grid shrink-0 place-items-center rounded-full p-1 transition-colors',
                open ? 'text-ink-2' : 'text-ink-3 hover:text-ink-2',
                className,
              ].join(' ')
        }
      >
        {children ?? <InfoIcon size={14} />}
      </button>
      <Popover id={id} open={open} anchor={anchor} align={align} side={side}>
        <PopoverBody title={title}>{body}</PopoverBody>
      </Popover>
    </>
  )
}

export interface HelpTipProps {
  tip: ReactNode
  title?: string
  /** Receives the popover id; pass it as aria-describedby on each control it explains. */
  children: (tipId: string) => ReactNode
  side?: 'bottom' | 'top'
  align?: 'start' | 'end' | 'center'
  className?: string
}

/** Controls are hovered on the way to a click, so wait longer before explaining. */
const CONTROL_HOVER_DELAY_MS = 600

export const HelpTip: FC<HelpTipProps> = ({
  tip,
  title,
  children,
  side = 'top',
  align = 'start',
  className = '',
}) => {
  const id = useId()
  const [anchor, setAnchor] = useState<HTMLDivElement | null>(null)
  const { open, hoverHandlers, focusHandlers } = useExplainer(CONTROL_HOVER_DELAY_MS)

  return (
    <div ref={setAnchor} className={className} {...hoverHandlers} {...focusHandlers}>
      {children(id)}
      <Popover id={id} open={open} anchor={anchor} align={align} side={side}>
        <PopoverBody title={title}>{tip}</PopoverBody>
      </Popover>
    </div>
  )
}
