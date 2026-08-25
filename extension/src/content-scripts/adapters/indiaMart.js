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
    const getListingAnchors = () => {
      const anchors = new Set();
      const selectors = ".gcnm, a.gcnm, .comp-name, .company-name, .supplier-name, .companyname, a[href*='/company/'], a[href*='indiamart.com/company/'], .pname, .product-title, .cl-card, .lst_spc, .mcard, .lst_Card";
      document.querySelectorAll(selectors).forEach(el => anchors.add(el));
      
      const elms = document.querySelectorAll("button, a, div, span, input[type='button']");
      elms.forEach(el => {
        const txt = el.textContent?.trim()?.toLowerCase() || "";
        const val = el.value?.trim()?.toLowerCase() || "";
        if (
          txt.includes("contact supplier") || val.includes("contact supplier") ||
          txt.includes("contact seller") || val.includes("contact seller") ||
          txt.includes("get best price") || val.includes("get best price") ||
          txt.includes("send inquiry") || val.includes("send inquiry") ||
          txt.includes("call now") || val.includes("call now") ||
          txt.includes("get quotes") || val.includes("get quotes")
        ) {
          anchors.add(el);
        }
      });
      
      return Array.from(anchors);
    };

    const anchors = getListingAnchors();
    const cardsSet = new Set();
    
    anchors.forEach(el => {
      let parent = el.parentElement;
      let found = false;
      
      for (let depth = 0; depth < 7 && parent; depth++) {
        if (parent.tagName === "BODY" || parent.tagName === "HTML" || parent.id === "page-container") {
          break;
        }
        
        const cls = parent.className || "";
        const classStr = typeof cls === "string" ? cls.toLowerCase() : "";
        
        if (
          classStr.includes("card") || 
          classStr.includes("lst_spc") || 
          classStr.includes("mcard") || 
          classStr.includes("lst_card") || 
          classStr.includes("q_cb") ||
          classStr.includes("item") || 
          classStr.includes("listing") ||
          classStr.includes("widget") ||
          parent.tagName === "LI" ||
          parent.tagName === "SECTION"
        ) {
          cardsSet.add(parent);
          found = true;
          break;
        }
        parent = parent.parentElement;
      }
      
      if (!found && el.parentElement && el.parentElement.parentElement) {
        cardsSet.add(el.parentElement.parentElement.parentElement || el.parentElement.parentElement);
      }
    });

    return DOMHelpers.filterUniqueCards(Array.from(cardsSet));
  }

  extractLead(card, batchId, mode) {
    // Extract Business Name
    const nameSelector = ".gcnm, a.gcnm, .company-name, .supplier-name, .companyname, .comp-name, [class*='company-name']";
    const nameEl = card.querySelector(nameSelector);
    let name = "";
    if (nameEl) {
      name = nameEl.textContent?.trim() || "";
    } else {
      const headerEl = card.querySelector("h3 a, h2 a, h3, h2");
      if (headerEl) {
        name = headerEl.textContent?.trim() || "";
      }
    }

    if (!name) return null;
    
    name = Normalizer.cleanBusinessName(name);

    if (!Validator.isValidBusinessName(name)) {
      Logger.warn(`[IndiaMartAdapter] Skipped card: invalid name "${name}"`);
      return null;
    }

    // Address
    const addrSelector = ".addDetail, .addr, .address, [class*='address'], [class*='location'], .cty-t, .clg, .loc, strong";
    const addrEl = card.querySelector(addrSelector);
    const address = addrEl?.textContent?.trim() || "";

    // Listing URL
    const linkSelector = "a[href*='indiamart.com'], a.gcnm, a[class*='company']";
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
    const nameEl = panel.querySelector(".gcnm, .comp-name, .company-name, #company_name_div, h1, h2");
    if (nameEl) {
      result.business_name = Normalizer.cleanBusinessName(nameEl.textContent?.trim() || "");
    }

    // 2. Address & Location
    const addrEl = panel.querySelector(".addDetail, .addr, .address, [class*='address'], [class*='location'], .cty-t, .loc");
    const address = addrEl?.textContent?.trim() || "";
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

    if (panelText.includes("Verified Exporter") || panelText.includes("TrustSEAL") || panelText.includes("Verified Supplier")) {
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
