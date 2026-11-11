import { useSQLiteContext } from 'expo-sqlite';
import { useEffect, useState } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, View } from 'react-native';

import { listPhotos } from '@/db/monuments';
import { useTheme } from '@/lib/theme';
import { Text } from '@/lib/typography';

import type { Scored } from './decision';
import { describeCandidate } from './describe';
import type { AimTarget } from './useAim';

type Props = {
  candidates: Scored<AimTarget>[];
  /** Whether the photo could not tell: the player confirms what the geometry offers. */
  confirm: boolean;
  onChoose: (candidate: Scored<AimTarget>) => void;
  onCancel: () => void;
};

function wording(confirm: boolean, count: number) {
  if (!confirm) {
    return {
      question: 'C’est lequel ?',
      hint: 'Ta photo ressemble à plusieurs monuments. Lequel viens-tu de photographier ?',
      cancel: 'Aucun de ceux-là',
    };
  }
  const hint = 'Lutèce ne peut pas le vérifier sur ta photo : confirme que tu es bien devant.';
  return count === 1
    ? { question: 'C’est bien lui ?', hint, cancel: 'Ce n’est pas lui' }
    : { question: 'C’est lequel ?', hint, cancel: 'Aucun de ceux-là' };
}

/** The photo cannot settle it: the player tells which monument they shot. */
export function ChooseMonument({ candidates, confirm, onChoose, onCancel }: Props) {
  const db = useSQLiteContext();
  const theme = useTheme();
  // The best reference photo of each candidate, to recognise it by.
  const [thumbs, setThumbs] = useState<Record<string, string>>({});

  useEffect(() => {
    let current = true;
    void Promise.all(
      candidates.map(async ({ target }) => [target.id, (await listPhotos(db, target.id))[0]] as const),
    ).then((found) => {
      if (current) {
        setThumbs(
          Object.fromEntries(found.flatMap(([id, photo]) => (photo ? [[id, photo.thumbUrl]] : []))),
        );
      }
    });
    return () => {
      current = false;
    };
  }, [db, candidates]);

  const words = wording(confirm, candidates.length);
  return (
    <ScrollView
      style={{ backgroundColor: theme.background }}
      contentInsetAdjustmentBehavior="automatic"
      contentContainerStyle={styles.content}
    >
      <Text style={[styles.question, { color: theme.text }]}>{words.question}</Text>
      <Text style={[styles.hint, { color: theme.secondaryText }]}>{words.hint}</Text>
      {candidates.map((candidate) => (
        <Pressable
          key={candidate.target.id}
          style={[styles.choice, { backgroundColor: theme.surface }]}
          onPress={() => onChoose(candidate)}
          accessibilityRole="button"
        >
          {thumbs[candidate.target.id] ? (
            <Image
              source={{ uri: thumbs[candidate.target.id] }}
              style={[styles.thumb, { backgroundColor: theme.separator }]}
              accessibilityIgnoresInvertColors
            />
          ) : (
            <View style={[styles.thumb, { backgroundColor: theme.separator }]} />
          )}
          <View style={styles.text}>
            <Text style={[styles.title, { color: theme.text }]} numberOfLines={3}>
              {candidate.target.monument.title}
            </Text>
            <Text style={[styles.details, { color: theme.secondaryText }]}>
              {describeCandidate(candidate)}
            </Text>
          </View>
        </Pressable>
      ))}
      <Pressable style={styles.cancel} onPress={onCancel} accessibilityRole="button">
        <Text style={[styles.cancelLabel, { color: theme.accent }]}>{words.cancel}</Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: 16,
    gap: 12,
  },
  question: {
    fontSize: 28,
    fontWeight: '700',
  },
  hint: {
    fontSize: 15,
    lineHeight: 21,
    marginBottom: 4,
  },
  choice: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderRadius: 14,
    padding: 10,
  },
  thumb: {
    width: 84,
    height: 84,
    borderRadius: 10,
  },
  text: {
    flex: 1,
  },
  title: {
    fontSize: 17,
    fontWeight: '600',
  },
  details: {
    fontSize: 14,
    marginTop: 3,
  },
  cancel: {
    alignSelf: 'center',
    padding: 12,
  },
  cancelLabel: {
    fontSize: 16,
    fontWeight: '600',
  },
});
