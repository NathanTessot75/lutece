import { Stack, useLocalSearchParams } from 'expo-router';

import { GroupPage } from '@/features/progress/GroupPage';
import { useGroups } from '@/features/progress/useGroups';

export default function SeriesScreen() {
  const { slug } = useLocalSearchParams<{ slug: string }>();
  const series = useGroups()?.series.find((one) => one.slug === slug);
  return (
    <>
      <Stack.Screen options={{ title: series?.name ?? '', headerBackButtonDisplayMode: 'minimal' }} />
      {series !== undefined && <GroupPage description={series.description} ids={series.ids} />}
    </>
  );
}
