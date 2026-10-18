import { useColorScheme } from 'react-native';

import type { RarityTier } from '@/db/monuments';

export type Theme = {
  background: string;
  surface: string;
  text: string;
  secondaryText: string;
  separator: string;
  /** What the player has captured, and what the app invites to touch. */
  accent: string;
  onAccent: string;
  /** What remains to capture. */
  pending: string;
  /** What can only be looked at. */
  muted: string;
  /** Each tier of rarity, readable as text on the surface and the background. */
  rarity: Record<RarityTier, string>;
};

const LIGHT: Theme = {
  background: '#F2F2F7',
  surface: '#FFFFFF',
  text: '#1C1C1E',
  secondaryText: '#6C6C70',
  separator: '#D1D1D6',
  accent: '#B5472B',
  onAccent: '#FFFFFF',
  pending: '#55555A',
  muted: '#B0B0B6',
  rarity: {
    commun: '#6C6C70',
    peu_commun: '#1F7A45',
    rare: '#2459B8',
    légendaire: '#9A6500',
  },
};

const DARK: Theme = {
  background: '#000000',
  surface: '#1C1C1E',
  text: '#FFFFFF',
  secondaryText: '#98989F',
  separator: '#38383A',
  accent: '#E0694A',
  onAccent: '#FFFFFF',
  pending: '#C7C7CC',
  muted: '#6E6E75',
  rarity: {
    commun: '#AEAEB2',
    peu_commun: '#4CD787',
    rare: '#7AA8FF',
    légendaire: '#F2C14E',
  },
};

/** The colours of the current appearance of the phone, light or dark. */
export function useTheme(): Theme {
  return useColorScheme() === 'dark' ? DARK : LIGHT;
}
