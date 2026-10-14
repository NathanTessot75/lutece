const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

// The monuments ship with the app as a SQLite file (assets/data/lutece.db).
config.resolver.assetExts.push('db');
// The image model runs on the phone (assets/models/dinov2-small-int8.onnx).
config.resolver.assetExts.push('onnx');

module.exports = config;
