import { Directory, File, Paths } from 'expo-file-system';

const FOLDER = 'captures';

/**
 * Keep the picture of a capture: out of the cache, where the camera wrote it,
 * and under the name of its monument. Gives the name to record.
 */
export async function keepPhoto(uri: string, monumentId: string): Promise<string> {
  const folder = new Directory(Paths.document, FOLDER);
  folder.create({ intermediates: true, idempotent: true });
  const name = `${monumentId}.jpg`;
  await new File(uri).move(new File(folder, name), { overwrite: true });
  return name;
}

/** Where a recorded picture is now: the folder of the app moves between installs. */
export function photoUri(name: string): string {
  return new File(Paths.document, FOLDER, name).uri;
}
