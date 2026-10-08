import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import { SQLiteProvider } from 'expo-sqlite';
import { Suspense } from 'react';
import { ActivityIndicator, StyleSheet, useColorScheme, View } from 'react-native';

import { BUNDLE_ASSET, BUNDLE_DATABASE_NAME } from '@/db/bundle';
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
  return (
    <ThemeProvider value={navigationTheme}>
      <Suspense fallback={<Loading />}>
        <SQLiteProvider
          databaseName={BUNDLE_DATABASE_NAME}
          assetSource={{ assetId: BUNDLE_ASSET }}
          useSuspense
        >
          <Stack />
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
