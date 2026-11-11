import { DarkTheme, DefaultTheme } from 'expo-router';
import { useColorScheme } from 'react-native';

import type { RarityTier } from '@/db/monuments';

import { fonts } from './typography';

export type Theme = {
  background: string;
  surface: string;
  text: string;
  secondaryText: string;
  separator: string;
  /** What the app invites to touch: buttons, links, what is chosen. */
  accent: string;
  onAccent: string;
  /** What is won: a capture, its points, a reward. */
  gold: string;
  onGold: string;
  /** What remains to capture. */
  pending: string;
  /** What can only be looked at. */
  muted: string;
  /** Each tier of rarity, readable as text on the surface and the background. */
  rarity: Record<RarityTier, string>;
};

// The palette of the art direction (10 November 2026): Paris blue, sky
// blue, cream, soft gold and city green.
const PARIS_BLUE = '#0B1F44';
const CREAM = '#F9F6F1';
const SOFT_GOLD = '#F6C453';

const LIGHT: Theme = {
  background: CREAM,
  surface: '#FFFFFF',
  text: PARIS_BLUE,
  secondaryText: '#5D6880',
  separator: '#E5DFD3',
  accent: PARIS_BLUE,
  onAccent: '#FFFFFF',
  gold: SOFT_GOLD,
  onGold: PARIS_BLUE,
  pending: '#2E4B7C',
  muted: '#B9C1CE',
  rarity: {
    commun: '#5D6880',
    peu_commun: '#4E7A4D',
    rare: '#2F5F9A',
    légendaire: '#A8780A',
  },
};

/** The night of Paris: the dark appearance, and the screens of a victory. */
export const NIGHT: Theme = {
  background: '#081631',
  surface: '#132A55',
  text: CREAM,
  secondaryText: '#AEB9CC',
  separator: '#25407A',
  accent: SOFT_GOLD,
  onAccent: PARIS_BLUE,
  gold: SOFT_GOLD,
  onGold: PARIS_BLUE,
  pending: '#8FB0D6',
  muted: '#4A5C80',
  rarity: {
    commun: '#B8C2D3',
    peu_commun: '#A7BFA6',
    rare: '#8FB3DF',
    légendaire: SOFT_GOLD,
  },
};

/** The colours of the current appearance of the phone, light or dark. */
export function useTheme(): Theme {
  return useColorScheme() === 'dark' ? NIGHT : LIGHT;
}

/** The navigation bars and tab bar in the colours and faces of the app. */
export function useNavigationTheme(): typeof DefaultTheme {
  const dark = useColorScheme() === 'dark';
  const base = dark ? DarkTheme : DefaultTheme;
  const theme = dark ? NIGHT : LIGHT;
  return {
    ...base,
    colors: {
      ...base.colors,
      primary: theme.accent,
      background: theme.background,
      card: theme.background,
      text: theme.text,
      border: theme.separator,
    },
    fonts: {
      regular: { fontFamily: fonts.regular, fontWeight: 'normal' },
      medium: { fontFamily: fonts.medium, fontWeight: 'normal' },
      bold: { fontFamily: fonts.bold, fontWeight: 'normal' },
      heavy: { fontFamily: fonts.heavy, fontWeight: 'normal' },
    },
  };
}
