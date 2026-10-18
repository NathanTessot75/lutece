import { Directory, File, Paths } from 'expo-file-system';

import bundle from '../../assets/data/bundle.json';

/**
 * The monuments, as a SQLite file built by the pipeline (`export_bundle`).
 * Metro hands it over as an asset; expo-sqlite copies it on first use.
 */
export const BUNDLE_ASSET: number = require('../../assets/data/lutece.db');

/**
 * The name of the copy on the phone. It carries the version of the content,
 * so a new bundle is copied instead of the old one being reopened. The
 * captures of the player live in another database, which no update replaces.
 */
export const BUNDLE_DATABASE_NAME = `monuments-${bundle.version}.db`;

export const BUNDLE_MONUMENT_COUNT: number = bundle.monuments;

/** The version of the content, and the fingerprint of the image model that goes with it. */
export const BUNDLE_VERSION: string = bundle.version;
export const BUNDLE_MODEL: string = bundle.model;

// Where expo-sqlite keeps its databases, under the documents of the app.
const SQLITE_FOLDER = 'SQLite';
// A copy of a bundle, with the files that SQLite may write next to it.
const BUNDLE_COPY = /^monuments-[0-9a-f]{12}\.db(-wal|-shm|-journal)?$/;

/**
 * Remove the copies of earlier bundles: every update of the monuments leaves
 * its predecessor behind, a few megabytes each time.
 */
export function removeStaleBundles(): void {
  const folder = new Directory(Paths.document, SQLITE_FOLDER);
  if (!folder.exists) {
    return;
  }
  for (const entry of folder.list()) {
    const stale = BUNDLE_COPY.test(entry.name) && !entry.name.startsWith(BUNDLE_DATABASE_NAME);
    if (entry instanceof File && stale) {
      entry.delete();
    }
  }
}
