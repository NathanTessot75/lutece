import { Stack, useRouter } from 'expo-router';
import { ScrollView, StyleSheet } from 'react-native';

import { useBadgeBook } from '@/features/badges/useBadgeBook';
import { LinkRow } from '@/features/navigation/LinkRow';
import { useRanking } from '@/features/ranking/RankingProvider';
import { useTabBarInsets } from '@/lib/tabBar';
import { useTheme } from '@/lib/theme';

/** What the player can aim for: the progress, the badges and the leaderboards. */
export default function ChallengesScreen() {
  const theme = useTheme();
  const tabBarInsets = useTabBarInsets();
  const router = useRouter();
  const badges = useBadgeBook();
  const won = badges?.filter((state) => state.wonAt !== null).length;
  const ranking = useRanking();
  return (
    <>
      <Stack.Screen options={{ title: 'Défis', headerLargeTitle: true }} />
      <ScrollView
        style={{ backgroundColor: theme.background }}
        contentContainerStyle={styles.content}
        contentInsetAdjustmentBehavior="automatic"
        {...tabBarInsets}
      >
        <LinkRow
          icon="chart.bar.fill"
          title="Progression"
          onPress={() => router.push('/progress')}
        />
        <LinkRow
          icon="rosette"
          title="Badges"
          detail={badges === null ? undefined : `${won}/${badges.length}`}
          onPress={() => router.push('/badges')}
        />
        {ranking.available && (
          <LinkRow
            icon="list.number"
            title="Classement"
            detail={ranking.username ?? 'Rejoindre'}
            onPress={() => router.push('/leaderboard')}
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
