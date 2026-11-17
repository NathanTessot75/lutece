import { useIsFocused } from 'expo-router';
import { type SFSymbol, SymbolView } from 'expo-symbols';
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { distanceBetween } from '@/features/capture/geometry';
import { pointsFor, tierLabel } from '@/features/game/rarity';
import { useOpenMonument } from '@/features/monuments/useOpenMonument';
import { formatDistance } from '@/lib/format';
import { useLocationAccess, usePosition } from '@/lib/location';
import { NIGHT, useTheme } from '@/lib/theme';
import { Text, fonts } from '@/lib/typography';

import { DAILY_MULTIPLIER, formatTimeLeft, untilMidnight } from './daily';
import { useDailyChallenge } from './DailyChallengeProvider';

// The time left is written to the minute.
const TICK_MS = 30_000;
// Light on the dark card, in both appearances of the phone.
const VEIL = 'rgba(255, 255, 255, 0.12)';

function Chip({ icon, text, gold = false }: { icon: SFSymbol; text: string; gold?: boolean }) {
  const theme = useTheme();
  return (
    <View style={[styles.chip, { backgroundColor: gold ? NIGHT.gold : VEIL }]}>
      <SymbolView
        name={icon}
        size={13}
        tintColor={gold ? NIGHT.onGold : theme.onMap}
        type="monochrome"
      />
      <Text style={[styles.chipText, { color: gold ? NIGHT.onGold : theme.onMap }]}>{text}</Text>
    </View>
  );
}

/** The place of the day: what it is, what it brings, and how long is left. */
export function DailyCard() {
  const theme = useTheme();
  const open = useOpenMonument();
  const { place, done, ready } = useDailyChallenge();
  const location = useLocationAccess();
  const focused = useIsFocused();
  const position = usePosition(focused && location.granted);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), TICK_MS);
    return () => clearInterval(timer);
  }, []);

  if (!ready) {
    return null;
  }
  if (place === null) {
    return (
      <View style={[styles.card, styles.body, { backgroundColor: theme.mapToCapture }]}>
        <Text style={[styles.kicker, { color: NIGHT.gold }]}>DÉFI DU JOUR</Text>
        <Text style={[styles.title, { color: theme.onMap }]}>Vous avez tout capturé.</Text>
      </View>
    );
  }

  const points = pointsFor(place.rarityTier) * DAILY_MULTIPLIER;
  const away =
    position === null
      ? null
      : distanceBetween(position, { latitude: place.lat, longitude: place.lon });
  return (
    <Pressable
      style={({ pressed }) => [
        styles.card,
        { backgroundColor: theme.mapToCapture },
        pressed && styles.pressed,
      ]}
      onPress={() => open(place.id)}
      accessibilityRole="button"
      accessibilityLabel={
        done
          ? `Défi du jour réussi : ${place.title}`
          : `Défi du jour : ${place.title}, ${points} points, encore ${formatTimeLeft(untilMidnight(now))}`
      }
    >
      <View style={styles.art}>
        <SymbolView
          name="building.columns.fill"
          size={64}
          tintColor="rgba(255, 255, 255, 0.16)"
          type="monochrome"
        />
      </View>
      <View style={styles.body}>
        <Text style={[styles.kicker, { color: NIGHT.gold }]}>
          {done
            ? 'DÉFI DU JOUR · RÉUSSI'
            : `DÉFI DU JOUR · ENCORE ${formatTimeLeft(untilMidnight(now)).toLocaleUpperCase('fr')}`}
        </Text>
        <Text style={[styles.title, { color: theme.onMap }]} numberOfLines={2}>
          {place.title}
        </Text>
        <View style={styles.chips}>
          {done ? (
            <Chip icon="checkmark.seal.fill" text="Revenez demain" gold />
          ) : (
            <Chip icon="flame.fill" text={`×${DAILY_MULTIPLIER} · ${points} points`} gold />
          )}
          {place.rarityTier !== null && <Chip icon="sparkles" text={tierLabel(place.rarityTier)} />}
          {away !== null && <Chip icon="location.fill" text={formatDistance(away)} />}
        </View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    marginHorizontal: 16,
    borderRadius: 22,
    overflow: 'hidden',
  },
  pressed: {
    opacity: 0.85,
  },
  art: {
    height: 110,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.06)',
  },
  body: {
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 16,
    gap: 6,
  },
  kicker: {
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 1.2,
  },
  title: {
    fontFamily: fonts.title,
    fontSize: 23,
    lineHeight: 29,
  },
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 4,
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  chipText: {
    fontSize: 13,
    fontWeight: '600',
  },
});
