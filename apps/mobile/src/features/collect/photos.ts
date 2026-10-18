import { Directory, File, Paths } from 'expo-file-system';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';

import { fitWithin } from './sample';

const FOLDER = 'samples';
// Lighter than the camera's own file, with no visible loss.
const QUALITY = 0.85;

/**
 * Keep the photo of a sample, its longest side brought down to the size kept,
 * under the name of the sample. Gives the name to record.
 */
export async function keepSamplePhoto(uri: string, sampleId: string): Promise<string> {
  const original = await ImageManipulator.manipulate(uri).renderAsync();
  const size = fitWithin(original.width, original.height);
  const image = size === null ? original : await ImageManipulator.manipulate(original).resize(size).renderAsync();
  const saved = await image.saveAsync({ format: SaveFormat.JPEG, compress: QUALITY });
  const folder = new Directory(Paths.document, FOLDER);
  folder.create({ intermediates: true, idempotent: true });
  const name = `${sampleId}.jpg`;
  await new File(saved.uri).move(new File(folder, name), { overwrite: true });
  return name;
}
