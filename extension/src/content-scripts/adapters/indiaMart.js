// src/content-scripts/adapters/indiaMart.js
// ProspectLens — IndiaMART Page Adapter Scraper

class IndiaMartAdapter extends BaseAdapter {
  constructor() {
    super("indiamart");
  }

  detectSupportedPage(url) {
    return url.includes("indiamart.com");
  }

  findListingCards() {
    const anchors = new Set();
    
    // 1. Semantic card and company selectors
    const selectors = ".staticProductInfo, .staticListingGrid, .product-card, .mcard, .lst_spc, .cl-card, .listing-card, [class*='ProductInfo'], [class*='ListingCard'], [class*='mcard'], .gcnm, a.gcnm, .comp-name, .company-name, .supplier-name, a[href*='/company/']";
    document.querySelectorAll(selectors).forEach(el => {
      if (!el.closest("header") && !el.closest("nav") && !el.closest("aside") && !el.closest("footer")) {
        anchors.add(el);
      }
    });
    
    // 2. Action buttons
    const elms = document.querySelectorAll("button, a, div, span, input[type='button']");
    elms.forEach(el => {
      const txt = el.textContent?.trim()?.toLowerCase() || "";
      const val = el.value?.trim()?.toLowerCase() || "";
      if (
        txt.includes("contact supplier") || val.includes("contact supplier") ||
        txt.includes("contact seller") || val.includes("contact seller") ||
        txt.includes("get best price") || val.includes("get best price") ||
        txt.includes("send inquiry") || val.includes("send inquiry") ||
        txt.includes("call now") || val.includes("call now")
      ) {
        if (!el.closest("header") && !el.closest("nav") && !el.closest("aside") && !el.closest("footer")) {
          anchors.add(el);
        }
      }
    });

    const cardsSet = new Set();
    anchors.forEach(el => {
      let parent = el;
      let found = false;
      
      for (let depth = 0; depth < 8 && parent; depth++) {
        if (parent.tagName === "BODY" || parent.tagName === "HTML" || parent.id === "page-container") {
          break;
        }
        
        const cls = parent.className || "";
        const classStr = typeof cls === "string" ? cls.toLowerCase() : "";
        
        if (
          classStr.includes("staticproductinfo") ||
          classStr.includes("staticlistinggrid") ||
          classStr.includes("card") || 
          classStr.includes("lst_spc") || 
          classStr.includes("mcard") || 
          classStr.includes("lst_card") || 
          classStr.includes("product") ||
          classStr.includes("item") || 
          classStr.includes("listing") ||
          parent.tagName === "LI" ||
          parent.tagName === "SECTION" ||
          parent.tagName === "ARTICLE"
        ) {
          // Avoid top level containers and headers
          if (parent.innerText && parent.innerText.length < 1500 && parent.children.length >= 1) {
            cardsSet.add(parent);
            found = true;
            break;
          }
        }
        parent = parent.parentElement;
      }
      
      if (!found && el.parentElement && el.parentElement.parentElement) {
        const candidate = el.parentElement.parentElement.parentElement || el.parentElement.parentElement;
        if (!candidate.closest("header") && !candidate.closest("nav")) {
          cardsSet.add(candidate);
        }
      }
    });

    return DOMHelpers.filterUniqueCards(Array.from(cardsSet));
  }

  extractLead(card, batchId, mode) {
    // Extract Business Name
    let name = "";
    
    // Check known company name selectors
    const nameSelector = ".company-name, .comp-name, .gcnm, a.gcnm, [class*='company-name'], [class*='supplier-name'], [class*='cname'], a[href*='indiamart.com/company/'], a[href*='/company/']";
    const nameEl = card.querySelector(nameSelector);
    if (nameEl) {
      name = nameEl.textContent?.trim() || "";
    }
    
    if (!name) {
      // Check headings (h2, h3, h4)
      const headings = card.querySelectorAll("h2, h3, h4, strong");
      for (const h of headings) {
        const text = h.textContent?.trim() || "";
        if (text && text.length > 2 && text.length < 80 && !text.toLowerCase().includes("contact") && !text.toLowerCase().includes("price")) {
          name = text;
          break;
        }
      }
    }

    if (!name) {
      // Fallback: check inner links for company profile links
      const compLink = card.querySelector("a[href*='indiamart.com']:not([href*='search.mp']), a[href*='/proddetail/']");
      if (compLink && compLink.textContent?.trim()) {
        name = compLink.textContent.trim();
      }
    }

    if (!name) return null;
    
    name = Normalizer.cleanBusinessName(name);

    if (!Validator.isValidBusinessName(name)) {
      // If validation fails on exact string, sanitize common prefixes like "Verified ... supplier"
      name = name.replace(/^(verified|trusted|leading|top)\s+/i, "").trim();
      if (!Validator.isValidBusinessName(name)) {
        Logger.warn(`[IndiaMartAdapter] Skipped card: invalid name "${name}"`);
        return null;
      }
    }

    // Address & City
    const addrSelector = ".location, .city, .addDetail, .addr, .address, [class*='location'], [class*='city'], .cty-t, [class*='addr']";
    const addrEl = card.querySelector(addrSelector);
    let address = addrEl?.textContent?.trim() || "";

    if (!address) {
      // Try to match standard Indian cities in card text
      const cardText = card.innerText || "";
      const cityMatch = cardText.match(/\b(Delhi|New Delhi|Noida|Gurugram|Gurgaon|Faridabad|Ghaziabad|Mumbai|Pune|Bengaluru|Bangalore|Hyderabad|Chennai|Kolkata|Ahmedabad|Surat|Jaipur|Lucknow|Kanpur|Indore|Bhopal|Chandigarh|Ludhiana|Agra|Nagpur|Vadodara|Patna|Coimbatore)\b/i);
      if (cityMatch) {
        address = cityMatch[0];
      }
    }

    // Listing URL
    const linkSelector = "a[href*='indiamart.com'], a[href*='/proddetail/'], a.gcnm, a[class*='company']";
    const linkEl = card.querySelector(linkSelector) || card.querySelector("a") || card.closest("a");
    const listingUrl = linkEl?.href || window.location.href;

    // Category
    const category = document.querySelector(".searchedKeyword, .srchKey, h1")?.textContent?.trim() || "";

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
    const nameEl = panel.querySelector(".company-name, .comp-name, .gcnm, a.gcnm, #company_name_div, h1, h2, h3");
    if (nameEl) {
      result.business_name = Normalizer.cleanBusinessName(nameEl.textContent?.trim() || "");
    }

    // 2. Address & Location
    const addrEl = panel.querySelector(".addDetail, .addr, .address, [class*='address'], [class*='location'], .cty-t, .loc");
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

    // 3. Contacts (Phone, Email, Alternate Numbers)
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
    const webEl = panel.querySelector("a[href*='http']:not([href*='indiamart.com']), a.website-link, a[class*='web']");
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

    // 5. Metadata / Verification Badges
    const gstMatch = panelText.match(/\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}\b/);
    if (gstMatch) {
      result.flexible_metadata.gstin = gstMatch[0];
    }

    if (panelText.includes("Verified Exporter") || panelText.includes("TrustSEAL") || panelText.includes("Verified Supplier") || panelText.includes("Verified")) {
      result.flexible_metadata.verified_status = "Verified Supplier";
    }

    const yearMatch = panelText.match(/Member Since\s*[:\-]?\s*(\d{4})|Established\s*[:\-]?\s*(\d{4})/i);
    if (yearMatch) {
      result.flexible_metadata.established_year = yearMatch[1] || yearMatch[2];
    }

    return result;
  }
}
window.IndiaMartAdapter = IndiaMartAdapter;
