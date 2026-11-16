import { Stack, useLocalSearchParams } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { CloseSheetButton } from '@/features/monuments/CloseSheetButton';
import { GroupPage } from '@/features/progress/GroupPage';
import { useGroups } from '@/features/progress/useGroups';

export default function SeriesScreen() {
  // Opened from the page of a monument, the series rises as a sheet over it.
  const { slug, sheet } = useLocalSearchParams<{ slug: string; sheet?: string }>();
  const inSheet = sheet === '1';
  const series = useGroups()?.series.find((one) => one.slug === slug);
  return (
    <View style={styles.screen}>
      <Stack.Screen options={{ title: series?.name ?? '', headerBackButtonDisplayMode: 'minimal' }} />
      {series !== undefined && (
        <GroupPage
          title={inSheet ? series.name : undefined}
          description={series.description}
          ids={series.ids}
        />
      )}
      {inSheet && <CloseSheetButton />}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
  },
});
