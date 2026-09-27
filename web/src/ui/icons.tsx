/**
 * Small inline icons (24 × 24 viewBox, stroked with currentColor).
 * Decorative: each is aria-hidden; the control around it carries the name.
 */

import type { FC, SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement> & { size?: number }

const Icon: FC<IconProps & { children: React.ReactNode }> = ({ size = 16, children, ...rest }) => (
  <svg
    aria-hidden="true"
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.8}
    strokeLinecap="round"
    strokeLinejoin="round"
    {...rest}
  >
    {children}
  </svg>
)

export const InfoIcon: FC<IconProps> = (p) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5" />
    <circle cx="12" cy="7.75" r="0.6" fill="currentColor" />
  </Icon>
)

export const PauseIcon: FC<IconProps> = (p) => (
  <Icon {...p}>
    <path d="M9 5v14M15 5v14" />
  </Icon>
)

export const PlayIcon: FC<IconProps> = (p) => (
  <Icon {...p}>
    <path d="M7 4.5v15l12.5-7.5L7 4.5Z" fill="currentColor" strokeWidth={1.2} />
  </Icon>
)

export const ResetIcon: FC<IconProps> = (p) => (
  <Icon {...p}>
    <path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1" />
    <path d="M3.5 4v4.5H8" />
  </Icon>
)

export const AlertIcon: FC<IconProps> = (p) => (
  <Icon {...p}>
    <path d="M10.3 3.9 2.6 17.5A2 2 0 0 0 4.3 20.5h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
    <path d="M12 9.5v4" />
    <circle cx="12" cy="16.9" r="0.6" fill="currentColor" />
  </Icon>
)

export const CloseIcon: FC<IconProps> = (p) => (
  <Icon {...p}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Icon>
)

export const BookIcon: FC<IconProps> = (p) => (
  <Icon {...p}>
    <path d="M2.5 5.5c2.6-1.4 6-1.3 9.5 1v13c-3.5-2.3-6.9-2.4-9.5-1v-13Z" />
    <path d="M21.5 5.5c-2.6-1.4-6-1.3-9.5 1v13c3.5-2.3 6.9-2.4 9.5-1v-13Z" />
  </Icon>
)

/** The fission-sim mark: a core inside a vessel ring. */
export const BrandMark: FC<IconProps> = ({ size = 22, ...rest }) => (
  <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" {...rest}>
    <circle cx="12" cy="12" r="9.25" stroke="currentColor" strokeWidth="1.8" />
    <circle cx="12" cy="12" r="5.25" stroke="currentColor" strokeWidth="1.4" strokeDasharray="2.2 2.2" opacity="0.7" />
    <circle cx="12" cy="12" r="2.1" fill="currentColor" />
  </svg>
)
