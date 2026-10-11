import { useSQLiteContext } from 'expo-sqlite';
import { useEffect, useState } from 'react';
import { FlatList, Image, Pressable, StyleSheet, Text, View } from 'react-native';

import type { Capture } from '@/db/captures';
import { type MonumentSummary, countCapturable, listMonumentsByIds } from '@/db/monuments';
import { photoUri } from '@/features/capture/photos';
import { useOpenMonument } from '@/features/monuments/useOpenMonument';
import { formatCount, formatDate } from '@/lib/format';
import { type Theme, useTheme } from '@/lib/theme';

import { useCaptures } from './CapturesProvider';

type RowProps = {
  capture: Capture;
  monument: MonumentSummary;
  theme: Theme;
  onOpen: (id: string) => void;
};

function Row({ capture, monument, theme, onOpen }: RowProps) {
  return (
    <Pressable
      style={[styles.row, { backgroundColor: theme.surface, borderColor: theme.separator }]}
      onPress={() => onOpen(monument.id)}
      accessibilityRole="button"
    >
      {capture.photoFile === null ? (
        <View style={[styles.photo, { backgroundColor: theme.separator }]} />
      ) : (
        <Image
          source={{ uri: photoUri(capture.photoFile) }}
          style={[styles.photo, { backgroundColor: theme.separator }]}
          accessibilityIgnoresInvertColors
        />
      )}
      <View style={styles.text}>
        <Text style={[styles.title, { color: theme.text }]} numberOfLines={3}>
          {monument.title}
        </Text>
        <Text style={[styles.details, { color: theme.secondaryText }]}>
          Capturé le {formatDate(capture.capturedAt)}
        </Text>
      </View>
    </Pressable>
  );
}

function countLine(captured: number, capturable: number): string {
  const what = captured > 1 ? 'monuments capturés' : 'monument capturé';
  return `${formatCount(captured)} ${what} sur ${formatCount(capturable)}`;
}

/** What the player has captured, the latest first. */
export function Collection() {
  const db = useSQLiteContext();
  const theme = useTheme();
  const open = useOpenMonument();
  const { captures } = useCaptures();
  const [monuments, setMonuments] = useState<ReadonlyMap<string, MonumentSummary>>(new Map());
  const [capturable, setCapturable] = useState<number | null>(null);

  useEffect(() => {
    let current = true;
    void countCapturable(db).then((count) => {
      if (current) {
        setCapturable(count);
      }
    });
    return () => {
      current = false;
    };
  }, [db]);

  useEffect(() => {
    let current = true;
    const ids = captures.map((capture) => capture.monumentId);
    void listMonumentsByIds(db, ids).then((found) => {
      if (current) {
        setMonuments(new Map(found.map((monument) => [monument.id, monument])));
      }
    });
    return () => {
      current = false;
    };
  }, [db, captures]);

  // A capture whose monument has left the bundle is kept, but not shown.
  const shown = captures.flatMap((capture) => {
    const monument = monuments.get(capture.monumentId);
    return monument ? [{ capture, monument }] : [];
  });
  return (
    <FlatList
      data={shown}
      keyExtractor={({ capture }) => capture.monumentId}
      contentInsetAdjustmentBehavior="automatic"
      style={{ backgroundColor: theme.background }}
      ListHeaderComponent={
        <Text style={[styles.caption, { color: theme.secondaryText }]}>
          {capturable === null ? ' ' : countLine(captures.length, capturable)}
        </Text>
      }
      ListEmptyComponent={
        captures.length === 0 ? (
          <Text style={[styles.empty, { color: theme.secondaryText }]}>
            Ta collection est vide. Ouvre la carte, approche-toi d’un monument et capture-le.
          </Text>
        ) : null
      }
      renderItem={({ item }) => (
        <Row capture={item.capture} monument={item.monument} theme={theme} onOpen={open} />
      )}
    />
  );
}

const styles = StyleSheet.create({
  caption: {
    fontSize: 15,
    paddingHorizontal: 16,
    paddingTop: 4,
    paddingBottom: 12,
  },
  empty: {
    fontSize: 16,
    lineHeight: 23,
    paddingHorizontal: 16,
    paddingTop: 24,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  photo: {
    width: 72,
    height: 72,
    borderRadius: 10,
  },
  text: {
    flex: 1,
  },
  title: {
    fontSize: 16,
    fontWeight: '600',
  },
  details: {
    fontSize: 13,
    marginTop: 3,
  },
});
