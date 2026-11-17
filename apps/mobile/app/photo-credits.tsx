import { Stack } from 'expo-router';

import { PhotoCredits } from '@/features/about/PhotoCredits';

export default function PhotoCreditsScreen() {
  return (
    <>
      <Stack.Screen options={{ title: 'Auteurs des photos', headerBackTitle: 'Retour' }} />
      <PhotoCredits />
    </>
  );
}
