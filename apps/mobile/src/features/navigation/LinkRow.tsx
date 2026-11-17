import { type SFSymbol, SymbolView } from 'expo-symbols';
import { Pressable, StyleSheet, View } from 'react-native';

import { useTheme } from '@/lib/theme';
import { Text } from '@/lib/typography';

type Props = {
  icon: SFSymbol;
  title: string;
  /** A word on what it holds, on the right. */
  detail?: string;
  onPress: () => void;
};

/** A row that leads to another page: an icon, a title, a detail and a chevron. */
export function LinkRow({ icon, title, detail, onPress }: Props) {
  const theme = useTheme();
  return (
    <Pressable
      style={({ pressed }) => [
        styles.row,
        { backgroundColor: theme.surface },
        pressed && styles.pressed,
      ]}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={detail ? `${title}, ${detail}` : title}
    >
      <View style={[styles.icon, { backgroundColor: theme.background }]}>
        <SymbolView name={icon} size={20} tintColor={theme.accent} type="monochrome" />
      </View>
      <Text style={[styles.title, { color: theme.text }]}>{title}</Text>
      {detail !== undefined && (
        <Text style={[styles.detail, { color: theme.secondaryText }]} numberOfLines={1}>
          {detail}
        </Text>
      )}
      <SymbolView
        name="chevron.right"
        size={13}
        tintColor={theme.secondaryText}
        weight="semibold"
        type="monochrome"
      />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    marginHorizontal: 16,
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 16,
  },
  pressed: {
    opacity: 0.7,
  },
  icon: {
    width: 38,
    height: 38,
    borderRadius: 19,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    flex: 1,
    fontSize: 17,
    fontWeight: '600',
  },
  detail: {
    fontSize: 15,
    maxWidth: '40%',
  },
});
