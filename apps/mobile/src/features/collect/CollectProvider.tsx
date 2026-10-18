import { type ReactNode, createContext, use, useEffect, useState } from 'react';

import { usePlayerDatabase } from '@/db/PlayerDatabase';
import { type NewSample, type SampleSummary, listSamples, saveSample } from '@/db/samples';
import { getSetting, setSetting } from '@/db/settings';

const COLLECT_MODE = 'collect_mode';

type Collect = {
  /** Whether a shot is taken as a sample of the field test set rather than as a capture. */
  enabled: boolean;
  setEnabled: (enabled: boolean) => Promise<void>;
  /** The samples taken so far, the latest first. */
  samples: SampleSummary[];
  record: (sample: NewSample) => Promise<void>;
};

const CollectContext = createContext<Collect | null>(null);

/** Hold the collect mode and its samples for the capture and collect screens. */
export function CollectProvider({ children }: { children: ReactNode }) {
  const db = usePlayerDatabase();
  const [enabled, setEnabledState] = useState(false);
  const [samples, setSamples] = useState<SampleSummary[]>([]);

  useEffect(() => {
    let current = true;
    void Promise.all([getSetting(db, COLLECT_MODE), listSamples(db)]).then(([mode, found]) => {
      if (current) {
        setEnabledState(mode === '1');
        setSamples(found);
      }
    });
    return () => {
      current = false;
    };
  }, [db]);

  const setEnabled = async (next: boolean) => {
    await setSetting(db, COLLECT_MODE, next ? '1' : '0');
    setEnabledState(next);
  };
  const record = async (sample: NewSample) => {
    await saveSample(db, sample);
    setSamples(await listSamples(db));
  };
  return <CollectContext value={{ enabled, setEnabled, samples, record }}>{children}</CollectContext>;
}

export function useCollect(): Collect {
  const collect = use(CollectContext);
  if (collect === null) {
    throw new Error('useCollect must be used under a CollectProvider');
  }
  return collect;
}
