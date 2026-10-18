import { Stack } from 'expo-router';

import { BadgeBook } from '@/features/badges/BadgeBook';

export default function BadgesScreen() {
  return (
    <>
      <Stack.Screen options={{ title: 'Badges', headerBackTitle: 'Retour' }} />
      <BadgeBook />
    </>
  );
}
