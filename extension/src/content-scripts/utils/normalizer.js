// src/content-scripts/utils/normalizer.js
// ProspectLens — Field normalization and cleaning utility

const Normalizer = {
  cleanBusinessName(name) {
    if (!name) return "";
    return name.replace(/\s*Contact\s*Supplier\s*$/i, "")
               .replace(/\s*Leading\s*Supplier\s*$/i, "")
               .replace(/\s*Call\s*Now\s*$/i, "")
               .trim();
  },

  cleanWebsiteUrl(url) {
    if (!url) return "";
    let clean = url.trim();
    if (clean.includes("google.com/url") || clean.includes("google.co.in/url")) {
      try {
        const urlObj = new URL(clean);
        const q = urlObj.searchParams.get("q");
        if (q) {
          clean = q;
        }
      } catch {}
    }
    return clean;
  }
};
window.Normalizer = Normalizer;
