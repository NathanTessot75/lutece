const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

// The monuments ship with the app as a SQLite file (assets/data/lutece.db).
config.resolver.assetExts.push('db');

module.exports = config;
