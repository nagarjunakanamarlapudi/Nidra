module.exports = function (api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
    // Reanimated 4: the worklets babel plugin lives in react-native-worklets
    // and MUST be listed last.
    plugins: ['react-native-worklets/plugin'],
  };
};
