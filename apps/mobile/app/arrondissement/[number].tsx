import { Stack, useLocalSearchParams } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { CloseSheetButton } from '@/features/monuments/CloseSheetButton';
import { GroupPage } from '@/features/progress/GroupPage';
import { useGroups } from '@/features/progress/useGroups';
import { formatArrondissement } from '@/lib/format';

export default function ArrondissementScreen() {
  // Opened from the page of a monument, the arrondissement rises as a sheet over it.
  const { number, sheet } = useLocalSearchParams<{ number: string; sheet?: string }>();
  const inSheet = sheet === '1';
  const group = useGroups()?.arrondissements.find(
    (one) => String(one.arrondissement) === number,
  );
  const title = group ? formatArrondissement(group.arrondissement) : '';
  return (
    <View style={styles.screen}>
      <Stack.Screen options={{ title, headerBackButtonDisplayMode: 'minimal' }} />
      {group !== undefined && (
        <GroupPage title={inSheet ? title : undefined} description={null} ids={group.ids} />
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
