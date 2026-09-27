/**
 * Theme preference (system / light / dark) and the theme currently applied.
 *
 * The preference is saved in localStorage. "system" follows the operating
 * system's appearance setting and keeps following it while the page is open.
 * The applied theme is written to `data-theme` on <html>, which switches the
 * CSS variables in index.css. An inline script in index.html applies the
 * same rule before first paint, so the page never flashes the wrong theme.
 */

import { create } from 'zustand'

export type ThemePreference = 'system' | 'light' | 'dark'
export type ResolvedTheme = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'fission-sim:theme'

/** The theme to apply for a preference, given whether the OS is in dark mode. */
export function resolveTheme(preference: ThemePreference, systemDark: boolean): ResolvedTheme {
  if (preference === 'system') return systemDark ? 'dark' : 'light'
  return preference
}

function readPreference(): ThemePreference {
  try {
    const saved = localStorage.getItem(THEME_STORAGE_KEY)
    if (saved === 'light' || saved === 'dark' || saved === 'system') return saved
  } catch {
    // Storage can be unavailable (private mode, blocked cookies); use the default.
  }
  return 'system'
}

const hasDom = typeof window !== 'undefined' && typeof document !== 'undefined'
const darkQuery = hasDom ? window.matchMedia('(prefers-color-scheme: dark)') : null

function apply(theme: ResolvedTheme): void {
  if (hasDom) document.documentElement.setAttribute('data-theme', theme)
}

interface ThemeState {
  preference: ThemePreference
  resolved: ResolvedTheme
  setPreference: (preference: ThemePreference) => void
}

const initialPreference: ThemePreference = hasDom ? readPreference() : 'system'
const initialResolved = resolveTheme(initialPreference, darkQuery?.matches ?? true)
apply(initialResolved)

export const useThemeStore = create<ThemeState>()((set) => ({
  preference: initialPreference,
  resolved: initialResolved,
  setPreference: (preference) => {
    try {
      localStorage.setItem(THEME_STORAGE_KEY, preference)
    } catch {
      // Not persisted; the choice still applies for this page view.
    }
    const resolved = resolveTheme(preference, darkQuery?.matches ?? true)
    apply(resolved)
    set({ preference, resolved })
  },
}))

darkQuery?.addEventListener('change', (e) => {
  const { preference } = useThemeStore.getState()
  if (preference !== 'system') return
  const resolved = resolveTheme(preference, e.matches)
  apply(resolved)
  useThemeStore.setState({ resolved })
})
