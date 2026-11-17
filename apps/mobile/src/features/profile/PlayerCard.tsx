import { useRouter } from 'expo-router';
import { SymbolView } from 'expo-symbols';
import { Pressable, StyleSheet, View } from 'react-native';

import { useCaptures } from '@/features/collection/CapturesProvider';
import { totalPoints } from '@/features/game/rarity';
import { titleFor } from '@/features/game/titles';
import { useRanking } from '@/features/ranking/RankingProvider';
import { formatCount, formatDate } from '@/lib/format';
import { useTheme } from '@/lib/theme';
import { Text, fonts } from '@/lib/typography';

/** Who the player is: their pseudonym, their title and the way to the next one. */
export function PlayerCard() {
  const theme = useTheme();
  const router = useRouter();
  const { captures } = useCaptures();
  const ranking = useRanking();
  const points = totalPoints(captures);
  const { title, next, progress } = titleFor(points);
  // The captures come newest first.
  const first = captures.at(-1);
  const name = ranking.username ?? 'Joueur anonyme';

  return (
    <View style={[styles.card, { backgroundColor: theme.surface }]}>
      <View style={styles.who}>
        <View style={[styles.avatar, { backgroundColor: theme.accent }]}>
          {ranking.username === null ? (
            <SymbolView
              name="building.columns.fill"
              size={28}
              tintColor={theme.onAccent}
              type="monochrome"
            />
          ) : (
            <Text style={[styles.initial, { color: theme.onAccent }]}>
              {ranking.username.charAt(0).toLocaleUpperCase('fr')}
            </Text>
          )}
        </View>
        <View style={styles.names}>
          <Text style={[styles.kicker, { color: theme.accent }]}>
            {title.name.toLocaleUpperCase('fr')}
          </Text>
          <Text style={[styles.name, { color: theme.text }]} numberOfLines={1}>
            {name}
          </Text>
          <Text style={[styles.since, { color: theme.secondaryText }]}>
            {first === undefined
              ? 'Aucune capture pour l’instant'
              : `Première capture le ${formatDate(first.capturedAt)}`}
          </Text>
        </View>
      </View>

      <View style={styles.climb}>
        <Text style={[styles.next, { color: theme.text }]}>
          {next === null
            ? 'Vous avez atteint le plus haut titre.'
            : `Encore ${formatCount(next.from - points)} points pour devenir ${next.name}`}
        </Text>
        <View
          style={[styles.track, { backgroundColor: theme.background }]}
          accessibilityRole="progressbar"
          accessibilityValue={{ min: 0, max: 100, now: Math.round(progress * 100) }}
        >
          <View
            style={[styles.fill, { backgroundColor: theme.gold, width: `${progress * 100}%` }]}
          />
        </View>
      </View>

      {ranking.available && ranking.username === null && (
        <Pressable
          style={({ pressed }) => [
            styles.choose,
            { borderTopColor: theme.separator },
            pressed && styles.pressed,
          ]}
          onPress={() => router.push('/leaderboard')}
          accessibilityRole="button"
        >
          <Text style={[styles.chooseLabel, { color: theme.accent }]}>Choisir un pseudonyme</Text>
          <SymbolView
            name="chevron.right"
            size={13}
            tintColor={theme.secondaryText}
            weight="semibold"
            type="monochrome"
          />
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    marginHorizontal: 16,
    borderRadius: 22,
    paddingTop: 16,
    paddingHorizontal: 16,
    paddingBottom: 4,
  },
  who: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
  },
  avatar: {
    width: 64,
    height: 64,
    borderRadius: 32,
    alignItems: 'center',
    justifyContent: 'center',
  },
  initial: {
    fontFamily: fonts.title,
    fontSize: 30,
    lineHeight: 36,
  },
  names: {
    flex: 1,
    gap: 1,
  },
  kicker: {
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 1.2,
  },
  name: {
    fontFamily: fonts.title,
    fontSize: 24,
    lineHeight: 30,
  },
  since: {
    fontSize: 13,
  },
  climb: {
    gap: 8,
    paddingVertical: 14,
  },
  next: {
    fontSize: 14,
  },
  track: {
    height: 8,
    borderRadius: 4,
    overflow: 'hidden',
  },
  fill: {
    height: '100%',
    borderRadius: 4,
  },
  choose: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingVertical: 12,
  },
  pressed: {
    opacity: 0.7,
  },
  chooseLabel: {
    fontSize: 16,
    fontWeight: '600',
  },
});
