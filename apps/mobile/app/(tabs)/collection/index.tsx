import { Stack } from 'expo-router';

import { Collection } from '@/features/collection/Collection';

export default function CollectionScreen() {
  return (
    <>
      <Stack.Screen options={{ title: 'Collection', headerLargeTitle: true }} />
      <Collection />
    </>
  );
}
