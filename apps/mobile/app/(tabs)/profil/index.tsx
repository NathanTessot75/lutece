import { Stack } from 'expo-router';
import { ScrollView } from 'react-native';

import { useTheme } from '@/lib/theme';

/** Empty for now. */
export default function Screen() {
  const theme = useTheme();
  return (
    <>
      <Stack.Screen options={{ title: 'Profil', headerLargeTitle: true }} />
      <ScrollView
        style={{ backgroundColor: theme.background }}
        contentInsetAdjustmentBehavior="automatic"
      />
    </>
  );
}
