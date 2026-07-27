// src/content-scripts/utils/normalizer.js
// ProspectLens — Field normalization and cleaning utility

const Normalizer = {
  cleanBusinessName(name) {
    if (!name) return "";
    return name.replace(/\s*Contact\s*Supplier\s*$/i, "")
               .replace(/\s*Leading\s*Supplier\s*$/i, "")
               .replace(/\s*Call\s*Now\s*$/i, "")
               .trim();
  }
};
window.Normalizer = Normalizer;
