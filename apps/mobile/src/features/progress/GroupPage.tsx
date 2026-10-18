import { useSQLiteContext } from 'expo-sqlite';
import { useEffect, useState } from 'react';
import { FlatList, Image, Pressable, StyleSheet, Text, View } from 'react-native';

import type { Capture } from '@/db/captures';
import { type MonumentSummary, listMonumentsByIds } from '@/db/monuments';
import { photoUri } from '@/features/capture/photos';
import { useCaptures } from '@/features/collection/CapturesProvider';
import { countProgress } from '@/features/game/progress';
import { describeMonument } from '@/features/monuments/describe';
import { useOpenMonument } from '@/features/monuments/useOpenMonument';
import { formatDate } from '@/lib/format';
import { type Theme, useTheme } from '@/lib/theme';

type RowProps = {
  monument: MonumentSummary;
  capture: Capture | null;
  theme: Theme;
  onOpen: (id: string) => void;
};

function Row({ monument, capture, theme, onOpen }: RowProps) {
  return (
    <Pressable
      style={[styles.row, { backgroundColor: theme.surface, borderColor: theme.separator }]}
      onPress={() => onOpen(monument.id)}
      accessibilityRole="button"
    >
      {capture?.photoFile ? (
        <Image
          source={{ uri: photoUri(capture.photoFile) }}
          style={[styles.photo, { backgroundColor: theme.separator }]}
          accessibilityIgnoresInvertColors
        />
      ) : (
        <View
          style={[
            styles.photo,
            capture === null
              ? { borderColor: theme.separator, borderWidth: 1.5 }
              : { backgroundColor: theme.separator },
          ]}
        />
      )}
      <View style={styles.text}>
        <Text
          style={[styles.title, { color: capture === null ? theme.secondaryText : theme.text }]}
          numberOfLines={2}
        >
          {monument.title}
        </Text>
        <Text style={[styles.details, { color: theme.secondaryText }]}>
          {capture === null ? describeMonument(monument) : `Capturé le ${formatDate(capture.capturedAt)}`}
        </Text>
      </View>
    </Pressable>
  );
}

type Props = {
  /** What the group gathers; none for an arrondissement. */
  description: string | null;
  ids: readonly string[];
};

/** The places of a series or of an arrondissement: those captured first. */
export function GroupPage({ description, ids }: Props) {
  const db = useSQLiteContext();
  const theme = useTheme();
  const open = useOpenMonument();
  const { byMonument } = useCaptures();
  const [monuments, setMonuments] = useState<MonumentSummary[]>([]);

  const key = ids.join(',');
  useEffect(() => {
    let current = true;
    void listMonumentsByIds(db, key ? key.split(',') : []).then((found) => {
      if (current) {
        setMonuments(found);
      }
    });
    return () => {
      current = false;
    };
  }, [db, key]);

  const progress = countProgress(ids, byMonument);
  const captured = monuments
    .filter((monument) => byMonument.has(monument.id))
    .sort((a, b) =>
      (byMonument.get(b.id)?.capturedAt ?? '').localeCompare(byMonument.get(a.id)?.capturedAt ?? ''),
    );
  const remaining = monuments
    .filter((monument) => !byMonument.has(monument.id))
    .sort((a, b) => a.title.localeCompare(b.title, 'fr'));
  const share = progress.total === 0 ? 0 : progress.captured / progress.total;
  return (
    <FlatList
      data={[...captured, ...remaining]}
      keyExtractor={(monument) => monument.id}
      contentInsetAdjustmentBehavior="automatic"
      style={{ backgroundColor: theme.background }}
      ListHeaderComponent={
        <View style={styles.header}>
          {description !== null && (
            <Text style={[styles.description, { color: theme.text }]}>{description}</Text>
          )}
          <Text style={[styles.count, { color: theme.secondaryText }]}>
            {progress.captured} sur {progress.total} {progress.captured > 1 ? 'capturés' : 'capturé'}
          </Text>
          <View style={[styles.track, { backgroundColor: theme.separator }]}>
            <View style={[styles.fill, { width: `${share * 100}%`, backgroundColor: theme.accent }]} />
          </View>
        </View>
      }
      renderItem={({ item }) => (
        <Row
          monument={item}
          capture={byMonument.get(item.id) ?? null}
          theme={theme}
          onOpen={open}
        />
      )}
    />
  );
}

const styles = StyleSheet.create({
  header: { paddingHorizontal: 16, paddingTop: 8, paddingBottom: 16, gap: 8 },
  description: { fontSize: 16, lineHeight: 22 },
  count: { fontSize: 15 },
  track: { height: 6, borderRadius: 3, overflow: 'hidden' },
  fill: { height: '100%', borderRadius: 3 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  photo: { width: 52, height: 52, borderRadius: 9 },
  text: { flex: 1 },
  title: { fontSize: 16, fontWeight: '600' },
  details: { fontSize: 13, marginTop: 3 },
});
