import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { MonumentSummary } from '@/db/monuments';
import { describeMonument } from '@/features/monuments/describe';
import { useOpenMonument } from '@/features/monuments/useOpenMonument';
import { useTheme } from '@/lib/theme';

/** What the map says about the monument whose pin was touched; it opens its page. */
export function SelectedMonumentCard({ monument }: { monument: MonumentSummary }) {
  const theme = useTheme();
  const open = useOpenMonument();
  return (
    <Pressable
      style={[styles.card, { backgroundColor: theme.surface }]}
      onPress={() => open(monument.id)}
      accessibilityRole="button"
    >
      <View style={styles.text}>
        <Text style={[styles.title, { color: theme.text }]} numberOfLines={3}>
          {monument.title}
        </Text>
        <Text style={[styles.details, { color: theme.secondaryText }]}>
          {describeMonument(monument)}
        </Text>
      </View>
      <Text style={[styles.chevron, { color: theme.secondaryText }]}>›</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderRadius: 16,
    paddingHorizontal: 16,
    paddingVertical: 14,
    shadowColor: '#000000',
    shadowOpacity: 0.18,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
  },
  text: {
    flex: 1,
  },
  chevron: {
    fontSize: 24,
  },
  title: {
    fontSize: 17,
    fontWeight: '600',
  },
  details: {
    fontSize: 14,
    marginTop: 3,
  },
});
