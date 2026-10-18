import type { SQLiteDatabase } from 'expo-sqlite';

import { listUnscoredCaptures, setCapturePoints } from '@/db/captures';
import { listMonumentsByIds } from '@/db/monuments';

import { pointsFor } from './rarity';

/**
 * Give the captures made before the points those of the rarity of their
 * monument today. A monument that left the bundle counts as common.
 */
export async function fillMissingPoints(
  player: SQLiteDatabase,
  bundle: SQLiteDatabase,
): Promise<void> {
  const ids = await listUnscoredCaptures(player);
  if (ids.length === 0) {
    return;
  }
  const tiers = new Map(
    (await listMonumentsByIds(bundle, ids)).map((monument) => [monument.id, monument.rarityTier]),
  );
  for (const id of ids) {
    await setCapturePoints(player, id, pointsFor(tiers.get(id) ?? null));
  }
}
