// src/content-scripts/adapters/tradeIndia.js
// ProspectLens — TradeIndia Page Adapter Scraper

class TradeIndiaAdapter extends BaseAdapter {
  constructor() {
    super("tradeindia");
  }

  detectSupportedPage(url) {
    return url.includes("tradeindia.com");
  }

  findListingCards() {
    const rawCards = document.querySelectorAll(
      ".product-info-cnt, .responsive-card, .product-details, .ilcl-listing-cont, .fullwidthcard, [class*='product-info-cnt'], [class*='responsive-card'], [class*='fullwidthcard']"
    );
    
    const validCards = [];
    rawCards.forEach(card => {
      if (!card.closest("header") && !card.closest("nav") && !card.closest("footer")) {
        if (card.innerText && card.innerText.length > 30 && card.innerText.length < 2000) {
          validCards.push(card);
        }
      }
    });

    if (validCards.length > 0) {
      return DOMHelpers.filterUniqueCards(validCards);
    }

    // Fallback: search for cards via action triggers
    const anchors = new Set();
    const elms = document.querySelectorAll("button, a, div, span, p");
    elms.forEach(el => {
      const txt = el.textContent?.trim()?.toLowerCase() || "";
      if (
        txt === "view number" || txt === "send inquiry" ||
        txt === "contact seller" || txt === "get best price" ||
        txt === "trusted seller" || txt === "contact supplier" ||
        txt === "get best quote" || txt.includes("inquiries only")
      ) {
        if (!el.closest("header") && !el.closest("nav") && !el.closest("footer")) {
          anchors.add(el);
        }
      }
    });

    const cardsSet = new Set();
    anchors.forEach(el => {
      let parent = el;
      for (let depth = 0; depth < 8 && parent; depth++) {
        if (parent.tagName === "BODY" || parent.tagName === "HTML") break;
        const cls = parent.className || "";
        const classStr = typeof cls === "string" ? cls.toLowerCase() : "";
        if (
          classStr.includes("card") || 
          classStr.includes("product") || 
          classStr.includes("listing") || 
          classStr.includes("item") ||
          parent.tagName === "LI" ||
          parent.tagName === "ARTICLE"
        ) {
          if (parent.innerText && parent.innerText.length > 30 && parent.innerText.length < 2000) {
            cardsSet.add(parent);
            break;
          }
        }
        parent = parent.parentElement;
      }
    });

    return DOMHelpers.filterUniqueCards(Array.from(cardsSet));
  }

  extractLead(card, batchId, mode) {
    // Extract Business / Seller Name
    let name = "";
    
    // 1. Direct class selectors
    const nameSelector = ".co-name, .company_name, .seller-name, .listing-link, [class*='seller_name'], [class*='company_name'], h2 a, h3 a, h2, h3";
    const nameEl = card.querySelector(nameSelector);
    if (nameEl) {
      name = nameEl.textContent?.trim() || "";
    }
    
    // 2. Scan text lines for seller / company name
    if (!name) {
      const textLines = (card.innerText || "").split("\n").map(l => l.trim()).filter(l => l.length > 2 && l.length < 80);
      for (const line of textLines) {
        const lower = line.toLowerCase();
        if (
          !lower.includes("made in india") &&
          !lower.includes("price:") &&
          !lower.includes("moq") &&
          !lower.includes("inquiry") &&
          !lower.includes("view number") &&
          !lower.includes("trusted seller") &&
          !lower.includes("get best quote") &&
          !lower.includes("years")
        ) {
          name = line;
          break;
        }
      }
    }

    if (!name) return null;
    
    name = Normalizer.cleanBusinessName(name);

    if (!Validator.isValidBusinessName(name)) {
      name = name.replace(/^(verified|trusted|leading|top)\s+/i, "").trim();
      if (!Validator.isValidBusinessName(name)) {
        Logger.warn(`[TradeIndiaAdapter] Skipped card: invalid name "${name}"`);
        return null;
      }
    }

    // Address & City
    let address = "";
    const addrEl = card.querySelector(".location, .city, .address, .seller-location, [class*='location'], [class*='city']");
    if (addrEl) {
      address = addrEl.textContent?.trim() || "";
    }
    if (!address) {
      const cardText = card.innerText || "";
      const cityMatch = cardText.match(/\b(Delhi|New Delhi|Noida|Gurugram|Gurgaon|Faridabad|Ghaziabad|Mumbai|Pune|Bengaluru|Bangalore|Hyderabad|Chennai|Kolkata|Ahmedabad|Surat|Jaipur|Lucknow|Kanpur|Indore|Bhopal|Chandigarh|Ludhiana|Agra|Nagpur|Vadodara|Patna|Coimbatore)\b/i);
      if (cityMatch) {
        address = cityMatch[0];
      }
    }

    // Listing URL
    const linkSelector = "a[href*='tradeindia.com/products/'], a[href*='/products/'], a[href*='tradeindia.com/Seller-'], a[href*='/Seller-'], a[href*='/company/']";
    const linkEl = card.querySelector(linkSelector) || card.querySelector("a") || card.closest("a");
    const listingUrl = linkEl?.href || window.location.href;

    // Category / Product
    const prodEl = card.querySelector(".product-title--desc, h2, h3, a[href*='/products/'], .product-title");
    const category = prodEl?.textContent?.trim() || document.querySelector("h1, .keyword")?.textContent?.trim() || "";

    // Contacts
    const contacts = this.extractContacts(card);

    const context = this.getSearchContext();
    const emptyFields = this.getEmptyMetadataFields();

    return Object.assign({
      batch_id: batchId,
      source_site: this.siteKey,
      business_name: name,
      address: address,
      category: category,
      listing_url: listingUrl,
      collection_mode: mode,
      contacts: contacts
    }, emptyFields, context);
  }

  extractDeepLead(panel) {
    const result = {
      flexible_metadata: {}
    };

    if (!panel) return result;
    const panelText = panel.textContent || "";

    // 1. Business Name
    const nameEl = panel.querySelector(".co-name, .company_name, .seller-name, .listing-link, h1, h2, [class*='company_name']");
    if (nameEl) {
      result.business_name = Normalizer.cleanBusinessName(nameEl.textContent?.trim() || "");
    }

    // 2. Address & Location
    const addrEl = panel.querySelector(".location, .city, .address, .seller-location, [class*='location'], [class*='address']");
    let address = addrEl?.textContent?.trim() || "";
    if (!address) {
      const cityMatch = panelText.match(/\b(Delhi|New Delhi|Noida|Gurugram|Gurgaon|Faridabad|Ghaziabad|Mumbai|Pune|Bengaluru|Bangalore|Hyderabad|Chennai|Kolkata|Ahmedabad|Surat|Jaipur|Lucknow)\b/i);
      if (cityMatch) address = cityMatch[0];
    }

    if (address) {
      result.address = address;
      const pinMatch = address.match(/\b([1-9][0-9]{5})\b/);
      if (pinMatch) {
        result.postal_code = pinMatch[1];
      }
      const parts = address.split(",").map(p => p.trim());
      if (parts.length >= 2) {
        result.city = parts[parts.length - 2].replace(/\d+/g, "").trim();
        result.state = parts[parts.length - 1].replace(/\d+/g, "").trim();
      }
    }

    // 3. Contacts
    const contacts = this.extractContacts(panel);
    result.contacts = contacts;

    const phones = contacts.filter(c => c.contact_type === "phone").map(c => c.contact_value);
    if (phones.length > 0) {
      result.primary_phone = Normalizer.normalizeIndianPhone(phones[0]);
      if (phones.length > 1) {
        result.secondary_phones = phones.slice(1, 4).map(p => Normalizer.normalizeIndianPhone(p)).join(", ");
      }
    }

    const emails = contacts.filter(c => c.contact_type === "email").map(c => c.contact_value);
    if (emails.length > 0) {
      result.primary_email = emails[0];
    }

    // 4. Website
    const webEl = panel.querySelector("a[href*='http']:not([href*='tradeindia.com']), a.website-link, a[class*='web']");
    if (webEl && webEl.href) {
      const cleanUrl = Normalizer.cleanWebsiteUrl(webEl.href);
      if (cleanUrl) {
        result.website = cleanUrl;
        try {
          const parsed = new URL(cleanUrl);
          result.website_domain = parsed.hostname.replace("www.", "");
        } catch {}
      }
    }

    // 5. TrustStamp & Verification
    if (panelText.includes("Trust") || panelText.includes("Super Seller") || panelText.includes("Verified Supplier") || panelText.includes("Verified") || panelText.includes("ti-stamp")) {
      result.flexible_metadata.verified_status = "Trusted Seller";
    }

    const yearMatch = panelText.match(/(\d+)\s*Years?/i) || panelText.match(/Member Since\s*[:\-]?\s*(\d{4})|Established\s*[:\-]?\s*(\d{4})/i);
    if (yearMatch) {
      result.flexible_metadata.established_year = yearMatch[1];
    }

    const gstMatch = panelText.match(/\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}\b/);
    if (gstMatch) {
      result.flexible_metadata.gstin = gstMatch[0];
    }

    return result;
  }
}
window.TradeIndiaAdapter = TradeIndiaAdapter;
