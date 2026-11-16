import { useRouter } from 'expo-router';
import { SymbolView } from 'expo-symbols';
import { Pressable, StyleSheet } from 'react-native';

import { useTheme } from '@/lib/theme';

const SIZE = 40;

/** Lowers the sheet of a page: a round button with a chevron pointing down. */
export function CloseSheetButton() {
  const theme = useTheme();
  const router = useRouter();
  const close = () => (router.canGoBack() ? router.back() : router.replace('/'));
  return (
    <Pressable
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: theme.surface },
        pressed && styles.pressed,
      ]}
      onPress={close}
      accessibilityRole="button"
      accessibilityLabel="Fermer"
      hitSlop={8}
    >
      <SymbolView name="chevron.down" size={17} tintColor={theme.text} weight="semibold" />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    position: 'absolute',
    top: 14,
    left: 16,
    width: SIZE,
    height: SIZE,
    borderRadius: SIZE / 2,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000000',
    shadowOpacity: 0.18,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
  },
  pressed: {
    transform: [{ scale: 0.92 }],
  },
});
