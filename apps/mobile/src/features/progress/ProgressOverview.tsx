import { useRouter } from 'expo-router';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { useCaptures } from '@/features/collection/CapturesProvider';
import { countProgress } from '@/features/game/progress';
import { formatArrondissement } from '@/lib/format';
import { useTheme } from '@/lib/theme';

import { GroupRow } from './GroupRow';
import { useGroups } from './useGroups';

/** Every arrondissement and every series, with how far the player is in each. */
export function ProgressOverview() {
  const theme = useTheme();
  const router = useRouter();
  const groups = useGroups();
  const { byMonument } = useCaptures();
  if (groups === null) {
    return <View style={[styles.screen, { backgroundColor: theme.background }]} />;
  }
  return (
    <ScrollView
      style={[styles.screen, { backgroundColor: theme.background }]}
      contentInsetAdjustmentBehavior="automatic"
      contentContainerStyle={styles.content}
    >
      <Text style={[styles.section, { color: theme.secondaryText }]}>Arrondissements</Text>
      <View style={[styles.group, { backgroundColor: theme.surface }]}>
        {groups.arrondissements.map((group, index) => (
          <GroupRow
            key={group.arrondissement}
            label={formatArrondissement(group.arrondissement)}
            progress={countProgress(group.ids, byMonument)}
            following={index > 0}
            onPress={() =>
              router.push({
                pathname: '/arrondissement/[number]',
                params: { number: String(group.arrondissement) },
              })
            }
          />
        ))}
      </View>
      <Text style={[styles.section, { color: theme.secondaryText }]}>Séries</Text>
      <View style={[styles.group, { backgroundColor: theme.surface }]}>
        {groups.series.map((series, index) => (
          <GroupRow
            key={series.slug}
            label={series.name}
            progress={countProgress(series.ids, byMonument)}
            following={index > 0}
            onPress={() => router.push({ pathname: '/series/[slug]', params: { slug: series.slug } })}
          />
        ))}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { paddingBottom: 32 },
  section: {
    fontSize: 13,
    fontWeight: '600',
    textTransform: 'uppercase',
    paddingHorizontal: 16,
    paddingTop: 24,
    paddingBottom: 6,
  },
  group: { marginHorizontal: 16, borderRadius: 12, paddingHorizontal: 14 },
});
