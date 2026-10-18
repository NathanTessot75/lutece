import { type ReactNode, createContext, use, useEffect, useRef, useState } from 'react';
import { AppState } from 'react-native';

import { type RankCounts, countRanked } from '@/db/ranking';
import { usePlayerDatabase } from '@/db/PlayerDatabase';
import { getSetting, setSetting } from '@/db/settings';
import { useCaptures } from '@/features/collection/CapturesProvider';
import { supabase } from '@/lib/supabase';

import {
  LEADERBOARD_CONSENT_VERSION,
  joinLeaderboards,
  leaveLeaderboards,
  sendRankings,
} from './send';

// The version of the text the player agreed to, and their pseudonym.
const CONSENT = 'leaderboard_consent';
const USERNAME = 'leaderboard_username';

type Ranking = {
  /** Whether this build knows a server to send to. */
  available: boolean;
  /** The pseudonym of a player who agreed to the current text; none otherwise. */
  username: string | null;
  join: (username: string) => Promise<void>;
  leave: () => Promise<void>;
  counts: RankCounts;
  sending: boolean;
  /** Why the last attempt failed; none when it worked. */
  failed: string | null;
  retry: () => void;
  /** Grows each time captures reach the server, to fetch the leaderboard again. */
  round: number;
};

const RankingContext = createContext<Ranking | null>(null);

const NO_COUNTS: RankCounts = { accepted: 0, pending_review: 0, rejected: 0, waiting: 0 };

/** Send the captures of a player who takes part in the leaderboards. */
export function RankingProvider({ children }: { children: ReactNode }) {
  const db = usePlayerDatabase();
  const { captures } = useCaptures();
  const [username, setUsername] = useState<string | null>(null);
  const [counts, setCounts] = useState<RankCounts>(NO_COUNTS);
  const [sending, setSending] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const [round, setRound] = useState(0);
  // Read while sending: the player may leave on the way.
  const taking = useRef(false);
  const running = useRef<Promise<void> | null>(null);
  // Something new came while sending: one more round once it is over.
  const again = useRef(false);

  const refresh = async () => setCounts(await countRanked(db));

  const run = async (client: NonNullable<typeof supabase>) => {
    setSending(true);
    try {
      do {
        again.current = false;
        await sendRankings(client, db, () => taking.current);
      } while (again.current && taking.current);
      setFailed(null);
    } catch (error) {
      setFailed(error instanceof Error ? error.message : String(error));
    } finally {
      running.current = null;
      setSending(false);
      setRound((value) => value + 1);
      await refresh();
    }
  };
  const send = () => {
    if (supabase === null || !taking.current) {
      return;
    }
    if (running.current !== null) {
      again.current = true;
      return;
    }
    running.current = run(supabase);
  };

  useEffect(() => {
    void Promise.all([getSetting(db, CONSENT), getSetting(db, USERNAME)]).then(([agreed, name]) => {
      taking.current = agreed === LEADERBOARD_CONSENT_VERSION && Boolean(name);
      setUsername(taking.current ? name : null);
    });
  }, [db]);

  // A new capture, or the app back in front: send what waits.
  const joined = username !== null;
  useEffect(() => {
    void countRanked(db).then((found) => {
      setCounts(found);
      if (joined) {
        send();
      }
    });
    const watching = AppState.addEventListener('change', (state) => {
      if (state === 'active' && joined) {
        send();
      }
    });
    return () => watching.remove();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- send reads the latest state
  }, [joined, captures.length]);

  const join = async (name: string) => {
    if (supabase === null) {
      return;
    }
    await joinLeaderboards(supabase, name);
    await setSetting(db, USERNAME, name);
    await setSetting(db, CONSENT, LEADERBOARD_CONSENT_VERSION);
    taking.current = true;
    setUsername(name);
  };
  const leave = async () => {
    taking.current = false;
    // What is on its way arrives first, then goes with the rest.
    await running.current;
    if (supabase !== null) {
      await leaveLeaderboards(supabase, db);
    }
    await setSetting(db, CONSENT, '');
    setUsername(null);
    await refresh();
  };

  return (
    <RankingContext
      value={{
        available: supabase !== null,
        username,
        join,
        leave,
        counts,
        sending,
        failed,
        retry: send,
        round,
      }}
    >
      {children}
    </RankingContext>
  );
}

export function useRanking(): Ranking {
  const ranking = use(RankingContext);
  if (ranking === null) {
    throw new Error('useRanking must be used under a RankingProvider');
  }
  return ranking;
}
