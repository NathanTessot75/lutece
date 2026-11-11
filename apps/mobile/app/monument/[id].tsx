import { Stack, useLocalSearchParams } from 'expo-router';
import { useSQLiteContext } from 'expo-sqlite';
import { useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import {
  type MonumentDetails,
  type MonumentPhoto,
  getMonument,
  listPhotos,
} from '@/db/monuments';
import { useCaptures } from '@/features/collection/CapturesProvider';
import { MonumentPage } from '@/features/monuments/MonumentPage';
import { useTheme } from '@/lib/theme';
import { Text } from '@/lib/typography';

type Loaded = {
  id: string;
  monument: MonumentDetails | null;
  photos: MonumentPhoto[];
};

export default function MonumentScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const db = useSQLiteContext();
  const theme = useTheme();
  const { byMonument } = useCaptures();
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    let current = true;
    void Promise.all([getMonument(db, id), listPhotos(db, id)]).then(([monument, photos]) => {
      if (current) {
        setLoaded({ id, monument, photos });
      }
    });
    return () => {
      current = false;
    };
  }, [db, id]);

  const shown = loaded?.id === id ? loaded : null;
  return (
    <>
      <Stack.Screen options={{ title: '', headerBackButtonDisplayMode: 'minimal' }} />
      {shown?.monument ? (
        <MonumentPage
          monument={shown.monument}
          photos={shown.photos}
          capture={byMonument.get(id) ?? null}
        />
      ) : (
        <View style={[styles.empty, { backgroundColor: theme.background }]}>
          {shown && (
            <Text style={{ color: theme.secondaryText }}>Ce monument est introuvable.</Text>
          )}
        </View>
      )}
    </>
  );
}

const styles = StyleSheet.create({
  empty: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
