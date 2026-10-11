import { useSQLiteContext } from 'expo-sqlite';
import { useEffect, useState } from 'react';

import { type CapturableMonument, listCapturableAround } from '@/db/monuments';
import { parseFootprint } from '@/features/map/footprint';
import { type CompassReading, type Position, useCompass, usePosition } from '@/lib/location';

import { type Candidate, type Target, FURTHEST_LIMIT_M, findCandidates } from './candidates';
import { type Coordinates, distanceBetween } from './geometry';

/** A monument that can be aimed at, with what a screen shows of it. */
export type AimTarget = Target & {
  monument: CapturableMonument;
};

export type Aim = {
  position: Position | null;
  compass: CompassReading | null;
  /** The monuments within reach, those the phone points at first. */
  candidates: Candidate<AimTarget>[];
};

// The monuments are read again once the player has walked this far, and each
// time for as far around again: none can come within reach unnoticed.
const REFRESH_DISTANCE_M = 50;

type Surroundings = {
  centre: Coordinates;
  targets: AimTarget[];
};

/** Follow the position and the compass, and tell which monuments are aimed at. */
export function useAim(enabled: boolean): Aim {
  const db = useSQLiteContext();
  const position = usePosition(enabled);
  const compass = useCompass(enabled);
  const [surroundings, setSurroundings] = useState<Surroundings | null>(null);

  const latitude = position?.latitude;
  const longitude = position?.longitude;
  const centre = surroundings?.centre;
  useEffect(() => {
    if (latitude === undefined || longitude === undefined) {
      return;
    }
    const here = { latitude, longitude };
    if (centre !== undefined && distanceBetween(centre, here) < REFRESH_DISTANCE_M) {
      return;
    }
    let current = true;
    void listCapturableAround(db, here, FURTHEST_LIMIT_M, REFRESH_DISTANCE_M).then((monuments) => {
      if (current) {
        const targets = monuments.map((monument) => ({
          id: monument.id,
          reachM: monument.reachM,
          outlines: parseFootprint(monument.footprint),
          monument,
        }));
        setSurroundings({ centre: here, targets });
      }
    });
    return () => {
      current = false;
    };
  }, [db, latitude, longitude, centre]);

  const candidates =
    position === null || surroundings === null
      ? []
      : findCandidates(position, compass, surroundings.targets);
  return { position, compass, candidates };
}
