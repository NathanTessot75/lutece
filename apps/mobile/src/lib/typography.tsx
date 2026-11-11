import {
  Inter_400Regular,
  Inter_500Medium,
  Inter_600SemiBold,
  Inter_700Bold,
  Inter_800ExtraBold,
} from '@expo-google-fonts/inter';
import { PlayfairDisplay_700Bold } from '@expo-google-fonts/playfair-display';
import { type ReactNode, createContext, use } from 'react';
import { Text as NativeText, StyleSheet, type TextProps, type TextStyle } from 'react-native';

/** The faces the app loads before it shows anything. */
export const FONT_ASSETS = {
  Inter_400Regular,
  Inter_500Medium,
  Inter_600SemiBold,
  Inter_700Bold,
  Inter_800ExtraBold,
  PlayfairDisplay_700Bold,
};

/** Playfair Display for the titles, Inter for the rest (decision of 10 November 2026). */
export const fonts = {
  title: 'PlayfairDisplay_700Bold',
  regular: 'Inter_400Regular',
  medium: 'Inter_500Medium',
  semibold: 'Inter_600SemiBold',
  bold: 'Inter_700Bold',
  heavy: 'Inter_800ExtraBold',
} as const;

// A face of Inter for each weight: iOS falls back to its own font when a
// loaded face is asked for at another weight.
const INTER: Record<string, string> = {
  normal: fonts.regular,
  '100': fonts.regular,
  '200': fonts.regular,
  '300': fonts.regular,
  '400': fonts.regular,
  '500': fonts.medium,
  '600': fonts.semibold,
  bold: fonts.bold,
  '700': fonts.bold,
  '800': fonts.heavy,
  '900': fonts.heavy,
};

/** The face for a style: the one it names, or Inter at its weight. */
export function faceOf(style: TextStyle | undefined): string {
  return style?.fontFamily ?? INTER[String(style?.fontWeight ?? '400')] ?? fonts.regular;
}

// Whether a text sits inside another, whose face it takes unless it asks.
const Nested = createContext(false);

/** Text in the faces of Lutèce. */
export function Text({ style, children, ...props }: TextProps & { children?: ReactNode }) {
  const nested = use(Nested);
  const flat = StyleSheet.flatten(style) ?? {};
  const decides = !nested || flat.fontFamily !== undefined || flat.fontWeight !== undefined;
  return (
    <Nested value>
      <NativeText
        {...props}
        style={decides ? [style, { fontFamily: faceOf(flat), fontWeight: 'normal' }] : style}
      >
        {children}
      </NativeText>
    </Nested>
  );
}

/** The faces of the navigation bars: their titles as the titles of the app. */
export const HEADER_FACES = {
  headerTitleStyle: { fontFamily: fonts.title },
  headerLargeTitleStyle: { fontFamily: fonts.title },
  headerBackTitleStyle: { fontFamily: fonts.regular },
};
