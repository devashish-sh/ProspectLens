// src/content-scripts/utils/logger.js
// ProspectLens — Standardized logging utility

const Logger = {
  log(message, ...args) {
    console.log(`[ProspectLens][Log] ${message}`, ...args);
  },
  info(message, ...args) {
    console.info(`[ProspectLens][Info] ${message}`, ...args);
  },
  warn(message, ...args) {
    console.warn(`[ProspectLens][Warn] ${message}`, ...args);
  },
  error(message, ...args) {
    console.error(`[ProspectLens][Error] ${message}`, ...args);
  }
};
window.Logger = Logger;
