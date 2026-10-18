import { Stack } from 'expo-router';

import { Leaderboard } from '@/features/ranking/Leaderboard';

export default function LeaderboardScreen() {
  return (
    <>
      <Stack.Screen options={{ title: 'Classement', headerBackTitle: 'Retour' }} />
      <Leaderboard />
    </>
  );
}
