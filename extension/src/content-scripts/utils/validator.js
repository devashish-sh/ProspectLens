// src/content-scripts/utils/validator.js
// ProspectLens — Extracted lead validation utilities

const Validator = {
  isValidBusinessName(name) {
    if (!name || name.length < 3) return false;
    
    const lowerName = name.toLowerCase();
    const blacklist = [
      "contact supplier",
      "leading supplier",
      "call now",
      "get quotes",
      "verified supplier",
      "inquire now",
      "get best quote",
      "contact us"
    ];
    
    return !blacklist.some(term => lowerName.includes(term) || lowerName === term);
  }
};
window.Validator = Validator;
