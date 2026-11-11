import { Stack } from 'expo-router';

import { HEADER_FACES } from '@/lib/typography';

export default function Layout() {
  return <Stack screenOptions={HEADER_FACES} />;
}
