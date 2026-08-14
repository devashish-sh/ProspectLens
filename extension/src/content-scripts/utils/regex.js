// src/content-scripts/utils/regex.js
// ProspectLens — Regular Expression definitions

const RegexPatterns = {
  // Phone regex: matches standard Indian/international mobile and landline formats
  phone: /\b(?:\+?91|0)?[-\s]?[6-9]\d{2,4}[-\s]?\d{2,4}[-\s]?\d{3,5}\b|\b0\d{2,4}[-\s]?\d{3,4}[-\s]?\d{3,4}\b|\b1800[-\s]?\d{3,4}[-\s]?\d{3,4}\b|\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}\b/g,
  // Email regex
  email: /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g
};
window.RegexPatterns = RegexPatterns;
