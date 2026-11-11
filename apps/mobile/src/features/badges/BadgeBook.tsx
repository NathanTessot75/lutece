import { Alert, Pressable, ScrollView, StyleSheet, View, useWindowDimensions } from 'react-native';

import { type BadgeState, FAMILIES } from '@/features/game/badges';
import { formatDate } from '@/lib/format';
import { type Theme, useTheme } from '@/lib/theme';
import { Text } from '@/lib/typography';

import { useBadgeBook } from './useBadgeBook';

const COLUMNS = 3;
const GAP = 10;
const SIDE = 16;

function progressLine({ badge, measure }: BadgeState): string {
  // A badge won or not at once has no count to show.
  if (measure.goal === 1) {
    return 'À gagner';
  }
  const count = `${measure.reached}/${measure.goal}`;
  return badge.unit ? `${count} ${badge.unit}` : count;
}

function Tile({ state, width, theme }: { state: BadgeState; width: number; theme: Theme }) {
  const { badge, wonAt } = state;
  const won = wonAt !== null;
  const status = won ? `Gagné le ${formatDate(wonAt)}` : progressLine(state);
  return (
    <Pressable
      style={[styles.tile, { width, backgroundColor: theme.surface }]}
      onPress={() => Alert.alert(badge.name, `${badge.condition}\n\n${status}`)}
      accessibilityRole="button"
      accessibilityLabel={`${badge.name}, ${won ? status : `à gagner, ${status}`}`}
    >
      <Text style={[styles.icon, !won && styles.locked]}>{badge.icon}</Text>
      <Text
        style={[styles.name, { color: won ? theme.text : theme.secondaryText }]}
        numberOfLines={2}
      >
        {badge.name}
      </Text>
      <Text style={[styles.status, { color: won ? theme.accent : theme.secondaryText }]}>
        {won ? formatDate(wonAt) : progressLine(state)}
      </Text>
    </Pressable>
  );
}

/** Every badge, by family: those won in colour with their date, the others greyed. */
export function BadgeBook() {
  const theme = useTheme();
  const { width } = useWindowDimensions();
  const states = useBadgeBook();
  if (states === null) {
    return <View style={[styles.screen, { backgroundColor: theme.background }]} />;
  }
  const tileWidth = (width - 2 * SIDE - (COLUMNS - 1) * GAP) / COLUMNS;
  const won = states.filter((state) => state.wonAt !== null).length;
  return (
    <ScrollView
      style={[styles.screen, { backgroundColor: theme.background }]}
      contentInsetAdjustmentBehavior="automatic"
      contentContainerStyle={styles.content}
    >
      <Text style={[styles.summary, { color: theme.secondaryText }]}>
        {won} {won > 1 ? 'badges gagnés' : 'badge gagné'} sur {states.length}
      </Text>
      {FAMILIES.map(({ family, name }) => {
        const members = states.filter((state) => state.badge.family === family);
        return (
          <View key={family}>
            <Text style={[styles.section, { color: theme.secondaryText }]}>{name}</Text>
            <View style={styles.grid}>
              {members.map((state) => (
                <Tile key={state.badge.slug} state={state} width={tileWidth} theme={theme} />
              ))}
            </View>
          </View>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { paddingHorizontal: SIDE, paddingBottom: 32 },
  summary: { fontSize: 15, paddingTop: 8 },
  section: {
    fontSize: 13,
    fontWeight: '600',
    textTransform: 'uppercase',
    paddingTop: 24,
    paddingBottom: 8,
  },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: GAP },
  tile: {
    alignItems: 'center',
    borderRadius: 14,
    paddingVertical: 12,
    paddingHorizontal: 6,
    gap: 4,
  },
  icon: { fontSize: 34 },
  locked: { opacity: 0.3 },
  name: { fontSize: 13, fontWeight: '600', textAlign: 'center' },
  status: { fontSize: 12, textAlign: 'center' },
});
