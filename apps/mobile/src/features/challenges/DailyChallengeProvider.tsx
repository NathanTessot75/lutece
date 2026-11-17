import { useSQLiteContext } from 'expo-sqlite';
import { type ReactNode, createContext, use, useEffect, useState } from 'react';
import { AppState } from 'react-native';

import { type MonumentPlace, listAllPlaces } from '@/db/monuments';
import { usePlayerDatabase } from '@/db/PlayerDatabase';
import { useCaptures } from '@/features/collection/CapturesProvider';
import { parisDay } from '@/features/game/time';

import { drawDailyPlace, today, untilMidnight } from './daily';
import { challengeSeed } from './seed';

type DailyChallenge = {
  /** The day in Paris: « 2026-11-18 ». */
  day: string;
  /** The place of the day; none until loaded, or once every place is captured. */
  place: MonumentPlace | null;
  /** Whether the player has captured it today. */
  done: boolean;
  /** Whether the seed and the places are loaded: without a place then, all are captured. */
  ready: boolean;
};

const DailyChallengeContext = createContext<DailyChallenge | null>(null);

/** Hold the place of the day of the player, for the capture and the challenges. */
export function DailyChallengeProvider({ children }: { children: ReactNode }) {
  const bundle = useSQLiteContext();
  const playerDb = usePlayerDatabase();
  const { captures } = useCaptures();
  const [seed, setSeed] = useState<string | null>(null);
  const [places, setPlaces] = useState<MonumentPlace[] | null>(null);
  const [day, setDay] = useState(() => today(new Date()));

  useEffect(() => {
    void challengeSeed(playerDb).then(setSeed);
  }, [playerDb]);

  useEffect(() => {
    void listAllPlaces(bundle).then(setPlaces);
  }, [bundle]);

  // A new day at midnight in Paris, or when the app comes back the next day.
  useEffect(() => {
    const turn = () => setDay(today(new Date()));
    const timer = setTimeout(turn, untilMidnight(new Date()) + 1000);
    const watching = AppState.addEventListener('change', (state) => {
      if (state === 'active') {
        turn();
      }
    });
    return () => {
      clearTimeout(timer);
      watching.remove();
    };
  }, [day]);

  // Only the captures before the day count: a capture of the day leaves the
  // place of the day as it is.
  const capturedBefore = new Set(
    captures
      .filter((capture) => parisDay(capture.capturedAt) < day)
      .map((capture) => capture.monumentId),
  );
  const ready = seed !== null && places !== null;
  const place = ready ? drawDailyPlace(seed, day, places, capturedBefore) : null;
  const done = place !== null && captures.some((capture) => capture.monumentId === place.id);
  return (
    <DailyChallengeContext value={{ day, place, done, ready }}>{children}</DailyChallengeContext>
  );
}

export function useDailyChallenge(): DailyChallenge {
  const challenge = use(DailyChallengeContext);
  if (challenge === null) {
    throw new Error('useDailyChallenge needs a DailyChallengeProvider');
  }
  return challenge;
}
