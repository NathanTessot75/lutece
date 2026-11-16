import { useLocalSearchParams } from 'expo-router';
import { useSQLiteContext } from 'expo-sqlite';
import { useEffect, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { type MonumentDetails, getMonument } from '@/db/monuments';
import { useCaptures } from '@/features/collection/CapturesProvider';
import { CloseSheetButton } from '@/features/monuments/CloseSheetButton';
import { MonumentPage } from '@/features/monuments/MonumentPage';
import { useTheme } from '@/lib/theme';
import { Text } from '@/lib/typography';

type Loaded = {
  id: string;
  monument: MonumentDetails | null;
};

export default function MonumentScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const db = useSQLiteContext();
  const theme = useTheme();
  const { byMonument } = useCaptures();
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    let current = true;
    void getMonument(db, id).then((monument) => {
      if (current) {
        setLoaded({ id, monument });
      }
    });
    return () => {
      current = false;
    };
  }, [db, id]);

  const shown = loaded?.id === id ? loaded : null;
  return (
    <View style={styles.sheet}>
      {shown?.monument ? (
        <MonumentPage monument={shown.monument} capture={byMonument.get(id) ?? null} />
      ) : (
        <View style={[styles.empty, { backgroundColor: theme.background }]}>
          {shown && (
            <Text style={{ color: theme.secondaryText }}>Ce monument est introuvable.</Text>
          )}
        </View>
      )}
      <CloseSheetButton />
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: {
    flex: 1,
  },
  empty: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
