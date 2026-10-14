import { Redirect, Stack, useLocalSearchParams } from 'expo-router';

import { ModelCheck } from '@/features/recognition/ModelCheck';

/**
 * A screen for development only, reached at lutece://dev/recognition; with
 * ?run=1 the check starts by itself, for a phone that nobody holds.
 */
export default function RecognitionCheckScreen() {
  const { run } = useLocalSearchParams<{ run?: string }>();
  if (!__DEV__) {
    return <Redirect href="/" />;
  }
  return (
    <>
      <Stack.Screen options={{ title: 'Vérification du modèle', headerBackTitle: 'Retour' }} />
      <ModelCheck runAtOnce={run === '1'} />
    </>
  );
}
