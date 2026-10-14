// Before fast-png, which needs a Latin-1 decoder as it loads.
import '@/lib/latin1';

import { File } from 'expo-file-system';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import { decode } from 'fast-png';

import { SIDE, centreSquare, toPixels } from './pixels';

/** Bring a photo to the square that the model reads, and give its pixels. */
export async function preparePhoto(uri: string): Promise<Float32Array> {
  const original = await ImageManipulator.manipulate(uri).renderAsync();
  const framed = await ImageManipulator.manipulate(original)
    .crop(centreSquare(original.width, original.height))
    .resize({ width: SIDE, height: SIDE })
    .renderAsync();
  // A lossless file, read back pixel by pixel.
  const saved = await framed.saveAsync({ format: SaveFormat.PNG });
  const image = decode(await new File(saved.uri).bytes());
  if (image.width !== SIDE || image.height !== SIDE) {
    throw new Error(`The framed photo measures ${image.width} × ${image.height}`);
  }
  return toPixels(image.data, image.channels, image.depth);
}
