import { StyleSheet, Text, View } from 'react-native';

import type { MonumentSummary } from '@/db/monuments';
import { describeMonument } from '@/features/monuments/describe';
import { useTheme } from '@/lib/theme';

/** What the map says about the monument whose pin was touched. */
export function SelectedMonumentCard({ monument }: { monument: MonumentSummary }) {
  const theme = useTheme();
  return (
    <View style={[styles.card, { backgroundColor: theme.surface }]}>
      <Text style={[styles.title, { color: theme.text }]} numberOfLines={3}>
        {monument.title}
      </Text>
      <Text style={[styles.details, { color: theme.secondaryText }]}>
        {describeMonument(monument)}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 16,
    paddingHorizontal: 16,
    paddingVertical: 14,
    shadowColor: '#000000',
    shadowOpacity: 0.18,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
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
