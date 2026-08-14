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
    
    // Strip tracking parameters (utm_*, gclid, fbclid, s, ref, etc.)
    try {
      if (clean.startsWith("http://") || clean.startsWith("https://")) {
        const urlObj = new URL(clean);
        const keysToRemove = [];
        for (const key of urlObj.searchParams.keys()) {
          if (key.startsWith("utm_") || key === "gclid" || key === "fbclid" || key === "s" || key === "ref") {
            keysToRemove.push(key);
          }
        }
        keysToRemove.forEach(key => urlObj.searchParams.delete(key));
        clean = urlObj.toString();
      }
    } catch {}

    // Reject Google domains
    try {
      const urlObj = new URL(clean);
      const host = urlObj.hostname.toLowerCase();
      if (host.includes("google.com") || 
          host.includes("google.co.in") || 
          host.includes("googleusercontent.com") || 
          host.includes("gstatic.com")) {
        return "";
      }
    } catch {}
    
    return clean;
  },

  normalizeIndianPhone(phoneStr) {
    if (!phoneStr) return "";
    
    // Clean all non-digit and non-plus characters
    let cleaned = phoneStr.replace(/[^\d+]/g, "");
    
    // Check if it is a toll-free number
    if (/^(1800|1860|1600)/.test(cleaned)) {
      return cleaned; // Preserve toll-free numbers as is
    }

    // Check if it has +91 prefix
    if (cleaned.startsWith("+91")) {
      const digits = cleaned.replace("+91", "");
      return `+91-${digits}`;
    }

    if (cleaned.startsWith("91") && cleaned.length > 10) {
      const digits = cleaned.substring(2);
      return `+91-${digits}`;
    }

    // Check if it starts with leading domestic 0
    if (cleaned.startsWith("0")) {
      const rest = cleaned.substring(1);
      // If it is 0 + 10-digit mobile starting with 6-9
      if (rest.length === 10 && /^[6-9]/.test(rest)) {
        return `+91-${rest}`;
      } else {
        // Landline with STD code (e.g. 01123456789)
        // Keep the leading 0, preserve the STD code
        return cleaned;
      }
    }

    // If it is a 10-digit mobile starting with 6-9
    if (cleaned.length === 10 && /^[6-9]/.test(cleaned)) {
      return `+91-${cleaned}`;
    }

    return cleaned;
  }
};
window.Normalizer = Normalizer;
