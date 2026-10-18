import { Stack } from 'expo-router';

import { CollectSettings } from '@/features/collect/CollectSettings';

/** Reached at lutece://collect: nothing in the app leads there. */
export default function CollectScreen() {
  return (
    <>
      <Stack.Screen options={{ title: 'Mode collecte', headerBackTitle: 'Retour' }} />
      <CollectSettings />
    </>
  );
}
