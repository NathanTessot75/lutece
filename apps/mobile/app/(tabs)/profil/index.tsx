import Constants from 'expo-constants';
import { Stack, useRouter } from 'expo-router';
import { ScrollView, StyleSheet } from 'react-native';

import { useContribution } from '@/features/contribute/ContributeProvider';
import { LinkRow } from '@/features/navigation/LinkRow';
import { PlayerCard } from '@/features/profile/PlayerCard';
import { PlayerFigures } from '@/features/profile/PlayerFigures';
import { useRanking } from '@/features/ranking/RankingProvider';
import { useTabBarInsets } from '@/lib/tabBar';
import { useTheme } from '@/lib/theme';
import { Text } from '@/lib/typography';

function Heading({ children }: { children: string }) {
  const theme = useTheme();
  return <Text style={[styles.heading, { color: theme.secondaryText }]}>{children}</Text>;
}

/** The player: who they are, what they have done, their settings, and what Lutèce owes to others. */
export default function ProfileScreen() {
  const theme = useTheme();
  const tabBarInsets = useTabBarInsets();
  const router = useRouter();
  const ranking = useRanking();
  const contribution = useContribution();
  const shared = ranking.available || contribution.available;
  return (
    <>
      <Stack.Screen options={{ title: 'Profil', headerLargeTitle: true }} />
      <ScrollView
        style={{ backgroundColor: theme.background }}
        contentContainerStyle={styles.content}
        contentInsetAdjustmentBehavior="automatic"
        {...tabBarInsets}
      >
        <PlayerCard />
        <PlayerFigures />

        {shared && <Heading>Jeu</Heading>}
        {ranking.available && (
          <LinkRow
            icon="list.number"
            title="Classement"
            detail={ranking.username ?? 'Rejoindre'}
            onPress={() => router.push('/leaderboard')}
          />
        )}
        {contribution.available && (
          <LinkRow
            icon="photo.stack"
            title="Contribuer mes photos"
            detail={contribution.enabled ? 'Activé' : 'Désactivé'}
            onPress={() => router.push('/contribute')}
          />
        )}

        <Heading>Vos données</Heading>
        <LinkRow
          icon="lock.fill"
          title="Confidentialité"
          onPress={() => router.push('/privacy')}
        />

        <Heading>À propos</Heading>
        <LinkRow
          icon="text.book.closed"
          title="Crédits et licences"
          onPress={() => router.push('/credits')}
        />
        <Text style={[styles.version, { color: theme.secondaryText }]}>
          Lutèce {Constants.expoConfig?.version ?? ''}
        </Text>
      </ScrollView>
    </>
  );
}

const styles = StyleSheet.create({
  content: {
    gap: 10,
    paddingTop: 8,
  },
  heading: {
    fontSize: 13,
    fontWeight: '600',
    textTransform: 'uppercase',
    paddingHorizontal: 32,
    paddingTop: 14,
  },
  version: {
    fontSize: 13,
    textAlign: 'center',
    paddingTop: 10,
  },
});
