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
}
window.JustdialAdapter = JustdialAdapter;
