import { useColorScheme } from 'react-native';

export type Theme = {
  background: string;
  surface: string;
  text: string;
  secondaryText: string;
  separator: string;
  /** What can be captured, and what the app invites to touch. */
  accent: string;
  onAccent: string;
  /** What can only be looked at. */
  muted: string;
};

const LIGHT: Theme = {
  background: '#F2F2F7',
  surface: '#FFFFFF',
  text: '#1C1C1E',
  secondaryText: '#6C6C70',
  separator: '#D1D1D6',
  accent: '#B5472B',
  onAccent: '#FFFFFF',
  muted: '#A1A1A8',
};

const DARK: Theme = {
  background: '#000000',
  surface: '#1C1C1E',
  text: '#FFFFFF',
  secondaryText: '#98989F',
  separator: '#38383A',
  accent: '#E0694A',
  onAccent: '#FFFFFF',
  muted: '#6E6E75',
};

/** The colours of the current appearance of the phone, light or dark. */
export function useTheme(): Theme {
  return useColorScheme() === 'dark' ? DARK : LIGHT;
}
