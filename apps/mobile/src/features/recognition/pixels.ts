// The photo of a capture must be prepared exactly as the pipeline prepares the
// reference photos (pipeline/src/lutece_pipeline/vision.py, SPEC §6.3).

/** The side, in pixels, of the square that the model reads. */
export const SIDE = 224;
// The reference photos were read 500 px wide (fetch_reference_photos).
const REFERENCE_WIDTH = 500;
// The colours are scaled with the statistics of ImageNet, as when the model was trained.
const MEAN = [0.485, 0.456, 0.406];
const STD = [0.229, 0.224, 0.225];

export type Square = { originX: number; originY: number; width: number; height: number };

/** The square at the centre of a photo: the framing called "crop" in the pipeline. */
export function centreSquare(width: number, height: number): Square {
  const side = Math.min(width, height);
  return {
    originX: Math.floor((width - side) / 2),
    originY: Math.floor((height - side) / 2),
    width: side,
    height: side,
  };
}

/**
 * Scale the colours of a framed photo, given as interleaved channels: 3 planes
 * of SIDE × SIDE numbers, red then green then blue, as the model reads them.
 */
export function toPixels(
  data: ArrayLike<number>,
  channels: number,
  depth = 8,
  side = SIDE,
): Float32Array {
  const plane = side * side;
  const top = 2 ** depth - 1;
  const pixels = new Float32Array(3 * plane);
  for (let index = 0; index < plane; index++) {
    for (let colour = 0; colour < 3; colour++) {
      const value = data[index * channels + colour] / top;
      pixels[colour * plane + index] = (value - MEAN[colour]) / STD[colour];
    }
  }
  return pixels;
}

/** The address of a reference photo at the width the pipeline read it. */
export function referencePhotoUrl(thumbUrl: string): string {
  return thumbUrl.replace(/\/\d+px-/, `/${REFERENCE_WIDTH}px-`);
}
