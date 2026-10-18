import { type ReactNode, createContext, use, useEffect, useRef, useState } from 'react';
import { AppState } from 'react-native';

import { countSent } from '@/db/contributions';
import { usePlayerDatabase } from '@/db/PlayerDatabase';
import { getSetting, setSetting } from '@/db/settings';
import { useCollect } from '@/features/collect/CollectProvider';
import { useCaptures } from '@/features/collection/CapturesProvider';
import { supabase } from '@/lib/supabase';

import { CONSENT_VERSION } from './rows';
import { deleteContributions, sendPending } from './send';

// The version of the text the player agreed to; nothing while they have not.
const CONSENT = 'contribution_consent';

type Contribution = {
  /** Whether this build knows a server to send to. */
  available: boolean;
  /** Whether the player agreed to the current text and contributes. */
  enabled: boolean;
  setEnabled: (enabled: boolean) => Promise<void>;
  sent: number;
  waiting: number;
  sending: boolean;
  /** Why the last attempt failed; none when it worked. */
  failed: string | null;
  retry: () => void;
  /** Delete all that was sent, and stop contributing. */
  erase: () => Promise<void>;
};

const ContributionContext = createContext<Contribution | null>(null);

/** Send the photos of a player who contributes, whenever there is something new. */
export function ContributeProvider({ children }: { children: ReactNode }) {
  const db = usePlayerDatabase();
  const { captures } = useCaptures();
  const { samples } = useCollect();
  const [enabled, setEnabledState] = useState(false);
  const [counts, setCounts] = useState({ sent: 0, waiting: 0 });
  const [sending, setSending] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  // Read while sending: the player may stop contributing on the way.
  const contributing = useRef(false);
  const running = useRef<Promise<void> | null>(null);
  // Something new came while sending: one more round once it is over.
  const again = useRef(false);

  const refresh = async () => setCounts(await countSent(db));

  const run = async (client: NonNullable<typeof supabase>) => {
    setSending(true);
    try {
      do {
        again.current = false;
        await sendPending(client, db, () => contributing.current);
      } while (again.current && contributing.current);
      setFailed(null);
    } catch (error) {
      setFailed(error instanceof Error ? error.message : String(error));
    } finally {
      running.current = null;
      setSending(false);
      await refresh();
    }
  };
  const send = () => {
    if (supabase === null || !contributing.current) {
      return;
    }
    if (running.current !== null) {
      again.current = true;
      return;
    }
    running.current = run(supabase);
  };

  useEffect(() => {
    void getSetting(db, CONSENT).then((agreed) => {
      contributing.current = agreed === CONSENT_VERSION;
      setEnabledState(contributing.current);
    });
  }, [db]);

  // Something new to send, or the app back in front: try again.
  const pending = captures.length + samples.length;
  useEffect(() => {
    void countSent(db).then((found) => {
      setCounts(found);
      if (enabled) {
        send();
      }
    });
    const watching = AppState.addEventListener('change', (state) => {
      if (state === 'active' && enabled) {
        send();
      }
    });
    return () => watching.remove();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- send reads the latest state
  }, [enabled, pending]);

  const setEnabled = async (next: boolean) => {
    await setSetting(db, CONSENT, next ? CONSENT_VERSION : '');
    contributing.current = next;
    setEnabledState(next);
  };
  const erase = async () => {
    await setEnabled(false);
    // What is on its way arrives first, then goes with the rest.
    await running.current;
    try {
      if (supabase !== null) {
        await deleteContributions(supabase, db);
      }
    } finally {
      await refresh();
    }
  };

  return (
    <ContributionContext
      value={{
        available: supabase !== null,
        enabled,
        setEnabled,
        sent: counts.sent,
        waiting: counts.waiting,
        sending,
        failed,
        retry: send,
        erase,
      }}
    >
      {children}
    </ContributionContext>
  );
}

export function useContribution(): Contribution {
  const contribution = use(ContributionContext);
  if (contribution === null) {
    throw new Error('useContribution must be used under a ContributeProvider');
  }
  return contribution;
}
