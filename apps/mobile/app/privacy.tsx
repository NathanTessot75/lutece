import { Stack } from 'expo-router';

import { Privacy } from '@/features/about/Privacy';

export default function PrivacyScreen() {
  return (
    <>
      <Stack.Screen options={{ title: 'Confidentialité', headerBackTitle: 'Retour' }} />
      <Privacy />
    </>
  );
}
