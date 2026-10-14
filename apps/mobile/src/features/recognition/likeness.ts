import type { ReferenceVector } from '@/db/monuments';

/** The cosine between the vector of a photo, of length 1, and a reference vector. */
export function cosine(vector: Float32Array, reference: ReferenceVector): number {
  let sum = 0;
  for (let index = 0; index < vector.length; index++) {
    sum += vector[index] * reference.levels[index];
  }
  return sum * reference.scale;
}

/**
 * How much a photo looks like a place: the best cosine with the reference
 * photos of the place (SPEC §6.1). None when the place has no reference photo.
 */
export function likeness(
  vector: Float32Array,
  references: readonly ReferenceVector[],
): number | null {
  if (references.length === 0) {
    return null;
  }
  return Math.max(...references.map((reference) => cosine(vector, reference)));
}
