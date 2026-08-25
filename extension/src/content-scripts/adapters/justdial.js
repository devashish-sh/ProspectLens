// src/content-scripts/adapters/justdial.js
// ProspectLens — Justdial Page Adapter Scraper

class JustdialAdapter extends BaseAdapter {
  constructor() {
    super("justdial");
  }

  detectSupportedPage(url) {
    return url.includes("justdial.com");
  }

  findListingCards() {
    const cardsRaw = document.querySelectorAll(
      ".resultbox_info, .store-details, [class*='resultbox'], .jsx-3473191726"
    );
    return DOMHelpers.filterUniqueCards(cardsRaw);
  }

  extractLead(card, batchId, mode) {
    // Extract Business Name
    const nameEl = card.querySelector(".store-name, .resultbox_title_anchor, [class*='title'] a, h2 a, h3 a, h2, h3");
    let name = nameEl?.textContent?.trim() || "";
    if (!name) return null;
    
    name = Normalizer.cleanBusinessName(name);

    if (!Validator.isValidBusinessName(name)) {
      Logger.warn(`[JustdialAdapter] Skipped card: invalid name "${name}"`);
      return null;
    }

    // Address
    const addrEl = card.querySelector(".addresstxt, [class*='address'], .store-address");
    const address = addrEl?.textContent?.trim() || "";

    // Category
    const catEl = card.querySelector(".resultbox_category, [class*='category']");
    const category = catEl?.textContent?.trim() || "";

    // Listing URL
    const linkEl = card.querySelector("a[href*='justdial']") || card.closest("a");
    const listingUrl = linkEl?.href || window.location.href;

    // Contacts
    const contacts = this.extractContacts(card);

    let rating = null;
    const ratingEl = card.querySelector(".resultbox_rating, .rating, [class*='rating']");
    if (ratingEl) {
      const match = ratingEl.textContent?.trim().match(/(\d+\.\d+|\d+)/);
      if (match) rating = parseFloat(match[1]);
    }

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
      contacts: contacts,
      rating: rating
    }, emptyFields, context);
  }

  extractDeepLead(panel) {
    const result = {
      flexible_metadata: {}
    };

    if (!panel) return result;
    const panelText = panel.textContent || "";

    // 1. Business Name
    const nameEl = panel.querySelector(".store-name, .resultbox_title_anchor, h1, h2, [class*='store-name']");
    if (nameEl) {
      result.business_name = Normalizer.cleanBusinessName(nameEl.textContent?.trim() || "");
    }

    // 2. Address & Location
    const addrEl = panel.querySelector(".addresstxt, [class*='address'], .store-address, .lng_add");
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

    // 4. Rating & Reviews Count
    const ratingEl = panel.querySelector(".resultbox_rating, .rating, [class*='rating'], .star-rating");
    if (ratingEl) {
      const match = ratingEl.textContent?.trim().match(/(\d+\.\d+|\d+)/);
      if (match) result.rating = parseFloat(match[1]);
    }

    const reviewsEl = panel.querySelector(".rating_count, .votes, [class*='votes'], [class*='review']");
    if (reviewsEl) {
      const match = reviewsEl.textContent?.match(/\b(\d{1,3}(?:,\d{3})*|\d+)\b/);
      if (match) result.review_count = parseInt(match[1].replace(/,/g, ""), 10);
    }

    // 5. Website
    const webEl = panel.querySelector("a[href*='http']:not([href*='justdial.com']), a.website-link, a[class*='web']");
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

    // 6. Business Hours / Open Status
    const hoursEl = panel.querySelector(".open-now, .store-timings, [class*='timings'], [class*='hours']");
    if (hoursEl) {
      result.open_status = hoursEl.textContent?.trim() || "";
      result.flexible_metadata.business_hours = result.open_status;
    }

    // 7. Verified Badge / Jd Verified
    if (panelText.includes("Jd Verified") || panelText.includes("Verified") || panelText.includes("Trust")) {
      result.flexible_metadata.verified_status = "Jd Verified";
    }

    return result;
  }
}
window.JustdialAdapter = JustdialAdapter;
