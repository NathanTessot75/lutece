import * as Haptics from 'expo-haptics';
import { useEffect } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import Animated, { FadeIn, FadeInDown, ZoomIn } from 'react-native-reanimated';

import { useBadgeBook } from '@/features/badges/useBadgeBook';
import { useCaptures } from '@/features/collection/CapturesProvider';
import { advancesOf, formatProgress, isComplete } from '@/features/game/progress';

import type { MonumentSummary } from '@/db/monuments';
import { formatPoints, tierLabel, tierNote } from '@/features/game/rarity';
import { describeMonument } from '@/features/monuments/describe';
import { useOpenMonument } from '@/features/monuments/useOpenMonument';
import { useGroups } from '@/features/progress/useGroups';
import { useTheme } from '@/lib/theme';

import { photoUri } from './photos';

// The reward comes after the photo and the name, then the progress, the
// badges won, and the buttons.
const REWARD_DELAY_MS = 650;
const PROGRESS_DELAY_MS = 900;
const BADGES_DELAY_MS = 1150;
const ACTIONS_DELAY_MS = 1400;

type Props = {
  /** With what its story page tells of it, when one is written. */
  monument: MonumentSummary & { summary: string | null };
  photoFile: string | null;
  /** What the capture brought. */
  points: number;
  onContinue: () => void;
};

/** The monument is in the collection: the moment a capture is for. */
export function Captured({ monument, photoFile, points, onContinue }: Props) {
  const theme = useTheme();
  const open = useOpenMonument();
  const tier = monument.rarityTier;
  const color = tier === null ? theme.accent : theme.rarity[tier];
  const note = tierNote(tier);
  const groups = useGroups();
  const { byMonument } = useCaptures();
  const advances = groups === null ? [] : advancesOf(monument, groups, byMonument);
  const book = useBadgeBook();
  const won = (book ?? []).filter((state) => state.wonWith === monument.id);

  // A rare place earns a second touch, stronger, when its reward appears.
  useEffect(() => {
    if (tier !== 'rare' && tier !== 'légendaire') {
      return;
    }
    const style =
      tier === 'légendaire' ? Haptics.ImpactFeedbackStyle.Heavy : Haptics.ImpactFeedbackStyle.Medium;
    const timer = setTimeout(() => void Haptics.impactAsync(style), REWARD_DELAY_MS);
    return () => clearTimeout(timer);
  }, [tier]);

  // A badge won earns its own touch when it appears.
  const anyWon = won.length > 0;
  useEffect(() => {
    if (!anyWon) {
      return;
    }
    const timer = setTimeout(
      () => void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success),
      BADGES_DELAY_MS,
    );
    return () => clearTimeout(timer);
  }, [anyWon]);

  return (
    <ScrollView
      style={{ backgroundColor: theme.background }}
      contentInsetAdjustmentBehavior="automatic"
      contentContainerStyle={styles.content}
    >
      <Animated.Text
        entering={ZoomIn.springify().damping(12)}
        style={[styles.cheer, { color: theme.accent }]}
      >
        Capturé !
      </Animated.Text>
      {photoFile !== null && (
        <Animated.View entering={FadeIn.duration(400).delay(150)} style={styles.photoFrame}>
          <Image
            source={{ uri: photoUri(photoFile) }}
            style={[styles.photo, { backgroundColor: theme.separator }]}
            resizeMode="cover"
            accessibilityIgnoresInvertColors
          />
        </Animated.View>
      )}
      <Animated.View entering={FadeInDown.delay(300)} style={styles.heading}>
        <Text style={[styles.title, { color: theme.text }]}>{monument.title}</Text>
        <Text style={[styles.details, { color: theme.secondaryText }]}>
          {describeMonument(monument)}
        </Text>
        {monument.summary !== null && (
          <Text style={[styles.summary, { color: theme.text }]}>{monument.summary}</Text>
        )}
      </Animated.View>
      <Animated.View
        entering={ZoomIn.delay(REWARD_DELAY_MS).springify().damping(10)}
        style={[styles.reward, { backgroundColor: theme.surface, borderColor: color }]}
        accessible
        accessibilityLabel={[tier && tierLabel(tier), `${formatPoints(points)} gagnés`, note]
          .filter(Boolean)
          .join('. ')}
      >
        {tier !== null && (
          <Text style={[styles.tier, { color }]}>{tierLabel(tier).toLocaleUpperCase('fr')}</Text>
        )}
        <Text style={[styles.points, { color }]}>+{formatPoints(points)}</Text>
        {note !== null && (
          <Text style={[styles.note, { color: theme.secondaryText }]}>{note}</Text>
        )}
      </Animated.View>
      {advances.length > 0 && (
        <Animated.View
          entering={FadeInDown.delay(PROGRESS_DELAY_MS)}
          style={[styles.progress, { backgroundColor: theme.surface }]}
        >
          {advances.map((advance) => {
            const complete = isComplete(advance.progress);
            return (
              <View key={`${advance.kind}-${advance.key}`} style={styles.advance}>
                <View style={styles.advanceText}>
                  <Text style={[styles.advanceLabel, { color: theme.text }]}>{advance.label}</Text>
                  {complete && (
                    <Text style={[styles.complete, { color: theme.accent }]}>
                      {advance.kind === 'series' ? 'Série terminée !' : 'Arrondissement terminé !'}
                    </Text>
                  )}
                </View>
                <Text
                  style={[styles.advanceCount, { color: complete ? theme.accent : theme.secondaryText }]}
                >
                  {complete ? '✓ ' : ''}
                  {formatProgress(advance.progress)}
                </Text>
              </View>
            );
          })}
        </Animated.View>
      )}
      {anyWon && (
        <Animated.View
          entering={ZoomIn.delay(BADGES_DELAY_MS).springify().damping(12)}
          style={[styles.badges, { backgroundColor: theme.surface, borderColor: theme.accent }]}
        >
          <Text style={[styles.badgesTitle, { color: theme.accent }]}>
            {won.length > 1 ? 'Badges gagnés !' : 'Badge gagné !'}
          </Text>
          {won.map(({ badge }) => (
            <View key={badge.slug} style={styles.badge}>
              <Text style={styles.badgeIcon}>{badge.icon}</Text>
              <View style={styles.advanceText}>
                <Text style={[styles.advanceLabel, { color: theme.text }]}>{badge.name}</Text>
                <Text style={[styles.badgeCondition, { color: theme.secondaryText }]}>
                  {badge.condition}
                </Text>
              </View>
            </View>
          ))}
        </Animated.View>
      )}
      <Animated.View entering={FadeIn.delay(ACTIONS_DELAY_MS)} style={styles.actions}>
        <Pressable
          style={[styles.button, { backgroundColor: theme.accent }]}
          onPress={onContinue}
          accessibilityRole="button"
        >
          <Text style={[styles.buttonLabel, { color: theme.onAccent }]}>Continuer</Text>
        </Pressable>
        <Pressable
          style={[styles.button, { backgroundColor: theme.surface }]}
          onPress={() => open(monument.id)}
          accessibilityRole="button"
        >
          <Text style={[styles.buttonLabel, { color: theme.accent }]}>Voir la fiche</Text>
        </Pressable>
      </Animated.View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    alignItems: 'center',
    padding: 24,
    gap: 10,
  },
  cheer: {
    fontSize: 34,
    fontWeight: '800',
    marginBottom: 6,
  },
  photoFrame: {
    alignSelf: 'stretch',
    marginBottom: 8,
  },
  photo: {
    width: '100%',
    aspectRatio: 1,
    borderRadius: 18,
  },
  heading: {
    alignItems: 'center',
    gap: 4,
  },
  title: {
    fontSize: 22,
    fontWeight: '700',
    textAlign: 'center',
  },
  details: {
    fontSize: 15,
    textAlign: 'center',
  },
  summary: {
    fontSize: 16,
    lineHeight: 23,
    textAlign: 'center',
    marginTop: 8,
  },
  reward: {
    alignSelf: 'stretch',
    alignItems: 'center',
    gap: 2,
    marginTop: 12,
    paddingVertical: 14,
    paddingHorizontal: 16,
    borderRadius: 18,
    borderWidth: 2,
  },
  tier: {
    fontSize: 14,
    fontWeight: '700',
    letterSpacing: 1.5,
  },
  points: {
    fontSize: 30,
    fontWeight: '800',
  },
  note: {
    fontSize: 14,
    textAlign: 'center',
    marginTop: 2,
  },
  progress: {
    alignSelf: 'stretch',
    borderRadius: 14,
    paddingHorizontal: 14,
    paddingVertical: 6,
  },
  advance: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 6,
  },
  advanceText: {
    flex: 1,
  },
  advanceLabel: {
    fontSize: 16,
  },
  complete: {
    fontSize: 14,
    fontWeight: '700',
    marginTop: 1,
  },
  advanceCount: {
    fontSize: 16,
    fontWeight: '600',
    fontVariant: ['tabular-nums'],
  },
  badges: {
    alignSelf: 'stretch',
    borderRadius: 14,
    borderWidth: 2,
    paddingHorizontal: 14,
    paddingVertical: 10,
    gap: 8,
  },
  badgesTitle: {
    fontSize: 14,
    fontWeight: '700',
    letterSpacing: 1,
    textTransform: 'uppercase',
    textAlign: 'center',
  },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  badgeIcon: {
    fontSize: 30,
  },
  badgeCondition: {
    fontSize: 13,
    marginTop: 1,
  },
  actions: {
    alignSelf: 'stretch',
    gap: 10,
    marginTop: 18,
  },
  button: {
    alignItems: 'center',
    borderRadius: 14,
    paddingVertical: 14,
  },
  buttonLabel: {
    fontSize: 17,
    fontWeight: '600',
  },
});
