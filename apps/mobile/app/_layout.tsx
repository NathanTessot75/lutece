import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import { SQLiteProvider } from 'expo-sqlite';
import { Suspense, useEffect } from 'react';
import { ActivityIndicator, StyleSheet, useColorScheme, View } from 'react-native';

import { BUNDLE_ASSET, BUNDLE_DATABASE_NAME, removeStaleBundles } from '@/db/bundle';
import { PlayerDatabaseProvider } from '@/db/PlayerDatabase';
import { CollectProvider } from '@/features/collect/CollectProvider';
import { CapturesProvider } from '@/features/collection/CapturesProvider';
import { ContributeProvider } from '@/features/contribute/ContributeProvider';
import { RankingProvider } from '@/features/ranking/RankingProvider';
import { useTheme } from '@/lib/theme';

function Loading() {
  const theme = useTheme();
  return (
    <View style={[styles.loading, { backgroundColor: theme.background }]}>
      <ActivityIndicator />
    </View>
  );
}

export default function RootLayout() {
  // The navigation bars follow the appearance of the phone, like the screens.
  const navigationTheme = useColorScheme() === 'dark' ? DarkTheme : DefaultTheme;
  useEffect(() => {
    try {
      removeStaleBundles();
    } catch {
      // Old copies only take room: they will go at the next start.
    }
  }, []);
  return (
    <ThemeProvider value={navigationTheme}>
      <Suspense fallback={<Loading />}>
        <SQLiteProvider
          databaseName={BUNDLE_DATABASE_NAME}
          assetSource={{ assetId: BUNDLE_ASSET }}
          useSuspense
        >
          <PlayerDatabaseProvider>
            <CapturesProvider>
              <CollectProvider>
                <ContributeProvider>
                  <RankingProvider>
                    <Stack>
                      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
                    </Stack>
                  </RankingProvider>
                </ContributeProvider>
              </CollectProvider>
            </CapturesProvider>
          </PlayerDatabaseProvider>
        </SQLiteProvider>
      </Suspense>
    </ThemeProvider>
  );
}

const styles = StyleSheet.create({
  loading: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
