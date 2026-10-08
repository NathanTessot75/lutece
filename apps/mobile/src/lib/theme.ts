import { useColorScheme } from 'react-native';

export type Theme = {
  background: string;
  surface: string;
  text: string;
  secondaryText: string;
  separator: string;
};

const LIGHT: Theme = {
  background: '#F2F2F7',
  surface: '#FFFFFF',
  text: '#1C1C1E',
  secondaryText: '#6C6C70',
  separator: '#D1D1D6',
};

const DARK: Theme = {
  background: '#000000',
  surface: '#1C1C1E',
  text: '#FFFFFF',
  secondaryText: '#98989F',
  separator: '#38383A',
};

/** The colours of the current appearance of the phone, light or dark. */
export function useTheme(): Theme {
  return useColorScheme() === 'dark' ? DARK : LIGHT;
}
