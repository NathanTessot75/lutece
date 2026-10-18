import { Stack } from 'expo-router';

import { ContributeSettings } from '@/features/contribute/ContributeSettings';

export default function ContributeScreen() {
  return (
    <>
      <Stack.Screen options={{ title: 'Contribuer', headerBackTitle: 'Retour' }} />
      <ContributeSettings />
    </>
  );
}
