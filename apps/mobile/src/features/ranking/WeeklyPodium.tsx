import { useFocusEffect, useRouter } from 'expo-router';
import { SymbolView } from 'expo-symbols';
import { useCallback, useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { formatPoints } from '@/features/game/rarity';
import { supabase } from '@/lib/supabase';
import { type Theme, useTheme } from '@/lib/theme';
import { Text, fonts } from '@/lib/typography';

import { useRanking } from './RankingProvider';
import { type Standing, fetchLeaderboard } from './send';
import { formatWeekLeft, untilNextWeek } from './week';

// The time left is written to the hour.
const TICK_MS = 60_000;
// The steps from left to right: the second, the first, the third.
const STEPS = [1, 0, 2];
const STEP_HEIGHTS = [56, 40, 28];

function ordinal(rank: number): string {
  return `${rank}${rank === 1 ? 'er' : 'e'}`;
}

function Step({ place, standing, theme }: { place: number; standing?: Standing; theme: Theme }) {
  const first = place === 0;
  const color = first ? theme.gold : place === 1 ? theme.muted : theme.separator;
  return (
    <View style={styles.column}>
      <Text
        style={[
          styles.name,
          { color: standing === undefined ? theme.secondaryText : standing.isMe ? theme.accent : theme.text },
        ]}
        numberOfLines={1}
      >
        {standing?.username ?? '—'}
      </Text>
      <Text style={[styles.points, { color: theme.secondaryText }]} numberOfLines={1}>
        {standing === undefined ? ' ' : formatPoints(standing.points)}
      </Text>
      <View style={[styles.step, { height: STEP_HEIGHTS[place], backgroundColor: color }]}>
        <Text style={[styles.stepRank, { color: first ? theme.onGold : theme.text }]}>
          {standing?.rank ?? place + 1}
        </Text>
      </View>
    </View>
  );
}

/** Where the player stands this week, under the podium. */
function standingLine(standings: Standing[]): string {
  if (standings.length === 0) {
    return 'Personne n’a encore de points cette semaine : à vous de prendre la tête.';
  }
  const me = standings.find((standing) => standing.isMe);
  if (me === undefined) {
    return 'Capturez un lieu cette semaine pour entrer au classement.';
  }
  return `Vous êtes ${ordinal(me.rank)} avec ${formatPoints(me.points)}.`;
}

/** The three best players of the week, where the player stands, and the way to the leaderboards. */
export function WeeklyPodium() {
  const theme = useTheme();
  const router = useRouter();
  const { round } = useRanking();
  const [standings, setStandings] = useState<Standing[] | null>(null);
  const [unreachable, setUnreachable] = useState(false);
  const [asked, setAsked] = useState(0);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    if (supabase === null) {
      return;
    }
    let current = true;
    void fetchLeaderboard(supabase, null, 'week', 3)
      .then((found) => {
        if (current) {
          setStandings(found);
          setUnreachable(false);
        }
      })
      .catch(() => {
        if (current) {
          setUnreachable(true);
        }
      });
    return () => {
      current = false;
    };
  }, [round, asked]);
  // Back on the screen: the others may have captured meanwhile.
  useFocusEffect(
    useCallback(() => {
      setAsked((value) => value + 1);
      setNow(new Date());
    }, []),
  );
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), TICK_MS);
    return () => clearInterval(timer);
  }, []);

  const podium = (standings ?? []).filter((standing) => standing.rank <= 3).slice(0, 3);
  const left = formatWeekLeft(untilNextWeek(now));
  return (
    <Pressable
      style={({ pressed }) => [
        styles.card,
        { backgroundColor: theme.surface },
        pressed && styles.pressed,
      ]}
      onPress={() => router.push('/leaderboard')}
      accessibilityRole="button"
      accessibilityLabel={`Classement de la semaine, encore ${left}. ${podium
        .map((standing) => `${ordinal(standing.rank)} ${standing.username}, ${formatPoints(standing.points)}`)
        .join(' ; ')}`}
    >
      <Text style={[styles.kicker, { color: theme.accent }]}>
        {`CETTE SEMAINE · ENCORE ${left.toLocaleUpperCase('fr')}`}
      </Text>
      <View style={styles.podium}>
        {STEPS.map((place) => (
          <Step key={place} place={place} standing={podium[place]} theme={theme} />
        ))}
      </View>
      {(unreachable || standings !== null) && (
        <Text style={[styles.line, { color: theme.secondaryText }]}>
          {unreachable
            ? 'Classement indisponible pour l’instant (pas de réseau ?).'
            : standingLine(standings ?? [])}
        </Text>
      )}
      <View style={[styles.footer, { borderTopColor: theme.separator }]}>
        <Text style={[styles.more, { color: theme.text }]}>Tout le classement</Text>
        <SymbolView
          name="chevron.right"
          size={13}
          tintColor={theme.secondaryText}
          weight="semibold"
          type="monochrome"
        />
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    marginHorizontal: 16,
    borderRadius: 22,
    paddingTop: 14,
    paddingHorizontal: 16,
    gap: 12,
  },
  pressed: {
    opacity: 0.7,
  },
  kicker: {
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 1.2,
  },
  podium: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 8,
  },
  column: {
    flex: 1,
    alignItems: 'center',
  },
  name: {
    fontSize: 15,
    fontWeight: '600',
  },
  points: {
    fontSize: 13,
    marginBottom: 6,
  },
  step: {
    alignSelf: 'stretch',
    alignItems: 'center',
    justifyContent: 'center',
    borderTopLeftRadius: 10,
    borderTopRightRadius: 10,
  },
  stepRank: {
    fontFamily: fonts.title,
    fontSize: 22,
    fontVariant: ['lining-nums'],
  },
  line: {
    fontSize: 14,
    lineHeight: 20,
  },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingVertical: 12,
  },
  more: {
    fontSize: 16,
    fontWeight: '600',
  },
});
