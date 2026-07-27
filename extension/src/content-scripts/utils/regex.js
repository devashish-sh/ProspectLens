// src/content-scripts/utils/regex.js
// ProspectLens — Regular Expression definitions

const RegexPatterns = {
  // Phone regex: matches standard Indian/international mobile and landline formats
  phone: /(?:\+?\d{1,3}[-.\s]?)?\(?\d{3,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}|\+91\s?\d{5}\s?\d{5}/g,
  // Email regex
  email: /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g
};
window.RegexPatterns = RegexPatterns;
