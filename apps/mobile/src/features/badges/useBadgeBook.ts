import { useSQLiteContext } from 'expo-sqlite';
import { useEffect, useState } from 'react';

import { type MonumentSummary, listMonumentsByIds } from '@/db/monuments';
import { useCaptures } from '@/features/collection/CapturesProvider';
import { type BadgeState, buildBadges, evaluate } from '@/features/game/badges';
import { useGroups } from '@/features/progress/useGroups';

type Places = { key: string; byId: ReadonlyMap<string, MonumentSummary> };

/** Where the player is with every badge; none while the captures' places load. */
export function useBadgeBook(): BadgeState[] | null {
  const db = useSQLiteContext();
  const groups = useGroups();
  const { captures } = useCaptures();
  const [places, setPlaces] = useState<Places | null>(null);

  const key = captures.map((capture) => capture.monumentId).join(',');
  useEffect(() => {
    let current = true;
    void listMonumentsByIds(db, key ? key.split(',') : []).then((found) => {
      if (current) {
        setPlaces({ key, byId: new Map(found.map((monument) => [monument.id, monument])) });
      }
    });
    return () => {
      current = false;
    };
  }, [db, key]);

  // The places of an older list of captures would leave the newest out.
  if (groups === null || places === null || places.key !== key) {
    return null;
  }
  const played = [...captures]
    .sort((a, b) => a.capturedAt.localeCompare(b.capturedAt))
    .map((capture) => {
      const monument = places.byId.get(capture.monumentId);
      return {
        monumentId: capture.monumentId,
        capturedAt: capture.capturedAt,
        latitude: capture.latitude,
        longitude: capture.longitude,
        tier: monument?.rarityTier ?? null,
        arrondissement: monument?.arrondissement ?? null,
      };
    });
  return evaluate(buildBadges(groups), played);
}
