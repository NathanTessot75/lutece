import { Stack } from 'expo-router';

import { Credits } from '@/features/about/Credits';

export default function CreditsScreen() {
  return (
    <>
      <Stack.Screen options={{ title: 'Crédits', headerBackTitle: 'Retour' }} />
      <Credits />
    </>
  );
}
