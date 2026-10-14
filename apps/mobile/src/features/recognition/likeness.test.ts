import type { ReferenceVector } from '@/db/monuments';

import { cosine, likeness } from './likeness';

function reference(levels: number[], rank = 1): ReferenceVector {
  const length = Math.hypot(...levels);
  return { rank, scale: 1 / length, levels: Int8Array.from(levels) };
}

describe('likeness', () => {
  const east = Float32Array.from([1, 0, 0]);

  it('is the cosine with the reference vector, its bytes scaled', () => {
    expect(cosine(east, reference([127, 0, 0]))).toBeCloseTo(1);
    expect(cosine(east, reference([0, 127, 0]))).toBeCloseTo(0);
    expect(cosine(east, reference([90, 90, 0]))).toBeCloseTo(Math.SQRT1_2);
    expect(cosine(east, reference([-127, 0, 0]))).toBeCloseTo(-1);
  });

  it('is the best cosine with the reference photos of a place', () => {
    const photos = [reference([0, 127, 0], 1), reference([90, 90, 0], 2), reference([0, 0, 1], 3)];
    expect(likeness(east, photos)).toBeCloseTo(Math.SQRT1_2);
    expect(likeness(east, [])).toBeNull();
  });
});
