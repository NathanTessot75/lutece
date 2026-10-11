import { Stack } from 'expo-router';

import { Aim } from '@/features/capture/Aim';

export default function AimScreen() {
  return (
    <>
      <Stack.Screen options={{ title: 'Viser', headerBackButtonDisplayMode: 'minimal' }} />
      <Aim />
    </>
  );
}
