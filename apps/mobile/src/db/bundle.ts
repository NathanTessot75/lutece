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
