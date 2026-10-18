import { Stack } from 'expo-router';

import { ProgressOverview } from '@/features/progress/ProgressOverview';

export default function ProgressScreen() {
  return (
    <>
      <Stack.Screen options={{ title: 'Progression', headerBackTitle: 'Retour' }} />
      <ProgressOverview />
    </>
  );
}
