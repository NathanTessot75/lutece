import { Stack, useLocalSearchParams } from 'expo-router';

import { GroupPage } from '@/features/progress/GroupPage';
import { useGroups } from '@/features/progress/useGroups';
import { formatArrondissement } from '@/lib/format';

export default function ArrondissementScreen() {
  const { number } = useLocalSearchParams<{ number: string }>();
  const group = useGroups()?.arrondissements.find(
    (one) => String(one.arrondissement) === number,
  );
  return (
    <>
      <Stack.Screen
        options={{
          title: group ? formatArrondissement(group.arrondissement) : '',
          headerBackButtonDisplayMode: 'minimal',
        }}
      />
      {group !== undefined && <GroupPage description={null} ids={group.ids} />}
    </>
  );
}
