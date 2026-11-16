import { useFonts } from 'expo-font';
import { Stack, ThemeProvider } from 'expo-router';
import { SQLiteProvider } from 'expo-sqlite';
import { Suspense, useEffect } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

import { BUNDLE_ASSET, BUNDLE_DATABASE_NAME, removeStaleBundles } from '@/db/bundle';
import { PlayerDatabaseProvider } from '@/db/PlayerDatabase';
import { CollectProvider } from '@/features/collect/CollectProvider';
import { CapturesProvider } from '@/features/collection/CapturesProvider';
import { ContributeProvider } from '@/features/contribute/ContributeProvider';
import { RankingProvider } from '@/features/ranking/RankingProvider';
import { useNavigationTheme, useTheme } from '@/lib/theme';
import { FONT_ASSETS, HEADER_FACES } from '@/lib/typography';

/** The navigation bar of a group page, hidden when it rises as a sheet. */
function groupOptions({ route }: { route: { params?: object } }) {
  const params = route.params as { sheet?: string } | undefined;
  return { headerShown: params?.sheet !== '1' };
}

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
  const navigationTheme = useNavigationTheme();
  const [fontsLoaded, fontsFailed] = useFonts(FONT_ASSETS);
  useEffect(() => {
    try {
      removeStaleBundles();
    } catch {
      // Old copies only take room: they will go at the next start.
    }
  }, []);
  // Without its faces, the app would show its first screen in the system font.
  if (!fontsLoaded && !fontsFailed) {
    return <Loading />;
  }
  return (
    <GestureHandlerRootView style={styles.root}>
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
                      <Stack screenOptions={HEADER_FACES}>
                        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
                        {/* The page of a monument rises from the bottom, over what showed it. */}
                        <Stack.Screen
                          name="monument/[id]"
                          options={{ presentation: 'modal', headerShown: false }}
                        />
                        {/* Opened from the page of a monument, a group rises as a sheet:
                            its own button lowers it, without a navigation bar. */}
                        <Stack.Screen name="series/[slug]" options={groupOptions} />
                        <Stack.Screen name="arrondissement/[number]" options={groupOptions} />
                      </Stack>
                    </RankingProvider>
                  </ContributeProvider>
                </CollectProvider>
              </CapturesProvider>
            </PlayerDatabaseProvider>
          </SQLiteProvider>
        </Suspense>
      </ThemeProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
  loading: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
