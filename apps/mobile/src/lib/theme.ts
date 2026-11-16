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

// The palette of the art direction (16 November 2026): the stone of Paris,
// the ink of its texts, the slate and zinc of its roofs, the gilding of its
// gates, and the verdigris of its copper.
const LIMESTONE = '#F2EDE3';
const POLISHED_STONE = '#FBF8F2';
const INK = '#24272B';
const SLATE = '#2E4050';
const ZINC = '#5A7184';
const GILDING = '#C9A24A';
const NIGHT_STONE = '#16181B';
const LAMPLIGHT = '#D9B45F';

const LIGHT: Theme = {
  background: LIMESTONE,
  surface: POLISHED_STONE,
  text: INK,
  secondaryText: '#6B6358',
  separator: '#E2D9C9',
  accent: SLATE,
  onAccent: POLISHED_STONE,
  gold: GILDING,
  onGold: INK,
  pending: ZINC,
  muted: '#C9C0B2',
  rarity: {
    commun: '#73695D',
    peu_commun: '#43705F',
    rare: '#3A6283',
    légendaire: '#85631A',
  },
};

/** Paris at night, stone under the street lamps: the dark appearance, and
 * the screens of a victory. */
export const NIGHT: Theme = {
  background: NIGHT_STONE,
  surface: '#24282D',
  text: '#EEE7DA',
  secondaryText: '#A79F93',
  separator: '#34393F',
  accent: LAMPLIGHT,
  onAccent: NIGHT_STONE,
  gold: LAMPLIGHT,
  onGold: NIGHT_STONE,
  pending: '#9DB3C4',
  muted: '#4A5057',
  rarity: {
    commun: '#BFB6A8',
    peu_commun: '#9EC3B2',
    rare: '#9EBDD8',
    légendaire: '#E3C06C',
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
