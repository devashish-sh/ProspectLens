// src/content-scripts/adapters/baseAdapter.js
// ProspectLens — Abstract Base Scraper Adapter class

class BaseAdapter {
  constructor(siteKey) {
    if (new.target === BaseAdapter) {
      throw new Error("BaseAdapter cannot be instantiated directly.");
    }
    this.siteKey = siteKey;
  }

  detectSupportedPage(url) {
    throw new Error("detectSupportedPage() must be implemented by subclass");
  }

  findListingCards() {
    throw new Error("findListingCards() must be implemented by subclass");
  }

  extractLead(card, batchId, mode) {
    throw new Error("extractLead() must be implemented by subclass");
  }

  extractContacts(element) {
    const contacts = [];
    const textSpans = element.querySelectorAll("span, a, div, p");
    const seenValues = new Set();
    
    for (const el of textSpans) {
      if (el.href) {
        if (el.href.startsWith("tel:")) {
          const telVal = el.href.replace("tel:", "").trim();
          if (telVal && !seenValues.has(telVal)) {
            seenValues.add(telVal);
            contacts.push({ contact_type: "phone", contact_value: telVal, sequence_number: contacts.length + 1, source: "listing" });
          }
        }
        if (el.href.startsWith("mailto:")) {
          const mailVal = el.href.replace("mailto:", "").trim();
          if (mailVal && !seenValues.has(mailVal)) {
            seenValues.add(mailVal);
            contacts.push({ contact_type: "email", contact_value: mailVal, sequence_number: contacts.length + 1, source: "listing" });
          }
        }
      }

      const text = el.textContent.trim();
      if (!text) continue;

      let phoneMatches;
      // Reset index for global regex exec loop
      RegexPatterns.phone.lastIndex = 0;
      while ((phoneMatches = RegexPatterns.phone.exec(text)) !== null) {
        const val = phoneMatches[0].trim();
        const digitsCount = val.replace(/\D/g, "").length;
        if (digitsCount >= 6 && digitsCount <= 30 && !seenValues.has(val)) {
          seenValues.add(val);
          contacts.push({ contact_type: "phone", contact_value: val, sequence_number: contacts.length + 1, source: "listing" });
        }
      }

      let emailMatches;
      RegexPatterns.email.lastIndex = 0;
      while ((emailMatches = RegexPatterns.email.exec(text)) !== null) {
        const val = emailMatches[0].trim();
        if (!seenValues.has(val)) {
          seenValues.add(val);
          contacts.push({ contact_type: "email", contact_value: val, sequence_number: contacts.length + 1, source: "listing" });
        }
      }
    }

    return contacts;
  }

  getSearchContext() {
    const url = window.location.href;
    let query = "";
    
    if (this.siteKey === "googlemaps") {
      query = document.querySelector("input#searchboxinput")?.value || "";
    } else if (this.siteKey === "indiamart") {
      query = document.querySelector("input[name='ss'], #srchBox")?.value || "";
    } else if (this.siteKey === "justdial") {
      query = document.querySelector("input#what-input, .search-text, #srchbx")?.value || "";
    }

    if (!query) {
      // Fallback: extract search keyword from title or headings
      const h1El = document.querySelector("h1");
      query = h1El?.textContent?.trim() || "";
    }

    let keyword = query;
    let location = "";
    
    const separators = [" in ", " near ", " at "];
    for (const sep of separators) {
      if (query.toLowerCase().includes(sep)) {
        const parts = query.split(new RegExp(sep, "i"));
        keyword = parts[0].trim();
        location = parts.slice(1).join(sep).trim();
        break;
      }
    }

    const now = new Date();
    const dateStr = now.toISOString().split("T")[0];
    const timeStr = now.toTimeString().split(" ")[0];

    return {
      search_query: query,
      search_keyword: keyword,
      search_location: location,
      directory_search_url: url,
      collection_date: dateStr,
      collection_time: timeStr
    };
  }

  getEmptyMetadataFields() {
    return {
      search_keyword: null,
      search_location: null,
      collection_date: null,
      collection_time: null,
      website: null,
      website_domain: null,
      rating: null,
      review_count: null,
      open_status: null,
      displayed_price: null,
      price_currency: null,
      price_type: null,
      price_level: null,
      flexible_metadata: null,
      sub_category: null,
      source_business_id: null,
      collector_version: "1.0.0",
      secondary_phones: null
    };
  }
}
window.BaseAdapter = BaseAdapter;
