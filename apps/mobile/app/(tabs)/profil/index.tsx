import { Stack, useRouter } from 'expo-router';
import { ScrollView, StyleSheet } from 'react-native';

import { useContribution } from '@/features/contribute/ContributeProvider';
import { LinkRow } from '@/features/navigation/LinkRow';
import { useTabBarInsets } from '@/lib/tabBar';
import { useTheme } from '@/lib/theme';

/** The settings of the player: for now, whether they send their photos. */
export default function ProfileScreen() {
  const theme = useTheme();
  const tabBarInsets = useTabBarInsets();
  const router = useRouter();
  const contribution = useContribution();
  return (
    <>
      <Stack.Screen options={{ title: 'Profil', headerLargeTitle: true }} />
      <ScrollView
        style={{ backgroundColor: theme.background }}
        contentContainerStyle={styles.content}
        contentInsetAdjustmentBehavior="automatic"
        {...tabBarInsets}
      >
        {contribution.available && (
          <LinkRow
            icon="photo.stack"
            title="Contribuer mes photos"
            detail={contribution.enabled ? 'Activé' : 'Désactivé'}
            onPress={() => router.push('/contribute')}
          />
        )}
      </ScrollView>
    </>
  );
}

const styles = StyleSheet.create({
  content: {
    gap: 10,
    paddingTop: 8,
  },
});
