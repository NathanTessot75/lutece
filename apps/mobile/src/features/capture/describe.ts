import { formatDistance } from '@/lib/format';

import type { Candidate } from './candidates';

// Under this many degrees aside, a monument is straight ahead.
const AHEAD_DEG = 5;

/** Where a candidate stands: « 25 m · 6° à droite ». */
export function describeCandidate({ distanceM, offsetDeg }: Candidate): string {
  if (distanceM === 0) {
    return 'Tu es dedans';
  }
  const distance = formatDistance(distanceM);
  if (offsetDeg === null) {
    return distance;
  }
  const aside = Math.round(Math.abs(offsetDeg));
  if (aside < AHEAD_DEG) {
    return `${distance} · en face`;
  }
  return `${distance} · ${aside}° à ${offsetDeg < 0 ? 'gauche' : 'droite'}`;
}
