import { type ReactNode, createContext, use, useEffect, useState } from 'react';

import { type Capture, type NewCapture, listCaptures, saveCapture } from '@/db/captures';
import { usePlayerDatabase } from '@/db/PlayerDatabase';

type Captures = {
  /** What the player has captured, the latest first. */
  captures: Capture[];
  /** The capture of each captured monument, by its identifier. */
  byMonument: ReadonlyMap<string, Capture>;
  /** Record a capture; every screen that shows captures follows. */
  record: (capture: NewCapture) => Promise<void>;
};

const CapturesContext = createContext<Captures | null>(null);

/** Hold the captures of the player for the map, the pages and the collection. */
export function CapturesProvider({ children }: { children: ReactNode }) {
  const db = usePlayerDatabase();
  const [captures, setCaptures] = useState<Capture[]>([]);

  useEffect(() => {
    let current = true;
    void listCaptures(db).then((found) => {
      if (current) {
        setCaptures(found);
      }
    });
    return () => {
      current = false;
    };
  }, [db]);

  const record = async (capture: NewCapture) => {
    await saveCapture(db, capture);
    setCaptures(await listCaptures(db));
  };
  const byMonument = new Map(captures.map((capture) => [capture.monumentId, capture]));
  return <CapturesContext value={{ captures, byMonument, record }}>{children}</CapturesContext>;
}

export function useCaptures(): Captures {
  const captures = use(CapturesContext);
  if (captures === null) {
    throw new Error('useCaptures must be used under a CapturesProvider');
  }
  return captures;
}
