import { Stack } from 'expo-router';

import { Capture } from '@/features/capture/Capture';

export default function CaptureScreen() {
  return (
    <>
      <Stack.Screen options={{ title: 'Capturer', headerBackButtonDisplayMode: 'minimal' }} />
      <Capture />
    </>
  );
}
