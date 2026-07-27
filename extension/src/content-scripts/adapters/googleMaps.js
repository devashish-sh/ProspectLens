// src/content-scripts/adapters/googleMaps.js
// ProspectLens — Google Maps Page Adapter Scraper

class GoogleMapsAdapter extends BaseAdapter {
  constructor() {
    super("googlemaps");
  }

  detectSupportedPage(url) {
    return url.includes("google.com/maps") || url.includes("maps.google.com");
  }

  findListingCards() {
    const items = document.querySelectorAll(".Nv2PK");
    return DOMHelpers.filterUniqueCards(items);
  }

  extractLead(card, batchId, mode) {
    // Extract Business Name
    const nameEl = card.querySelector(".qBF1Pd, .fontHeadlineSmall, [class*='name'] span");
    let name = nameEl?.textContent?.trim() || "";
    if (!name) return null;
    
    name = Normalizer.cleanBusinessName(name);

    if (!Validator.isValidBusinessName(name)) {
      Logger.warn(`[GoogleMapsAdapter] Skipped card: invalid name "${name}"`);
      return null;
    }

    // Address / Location
    const addrEl = card.querySelector(".W4Efsd span:not(.W4Efsd), .UsdlK");
    const address = addrEl?.textContent?.trim() || "";

    // Listing URL
    const linkEl = card.querySelector("a[href*='/maps/place/']");
    const listingUrl = linkEl?.href || window.location.href;

    // Category
    const catEl = card.querySelector(".W4Efsd .W4Efsd span");
    const category = catEl?.textContent?.trim() || "";

    // Contacts
    const contacts = this.extractContacts(card);

    // 1. Rating & reviews count
    let rating = null;
    const ratingEl = card.querySelector(".MW4etd, .fontBodyMedium, span[aria-label*='stars']");
    if (ratingEl) {
      const ratingText = ratingEl.textContent?.trim() || "";
      const match = ratingText.match(/(\d+\.\d+|\d+)/);
      if (match) {
        rating = parseFloat(match[1]);
        Logger.log(`Rating detected: ${rating}`);
      }
    }

    let reviewCount = null;
    const reviewsEl = card.querySelector(".UY7F9, .W4Efsd");
    if (reviewsEl) {
      const reviewsText = reviewsEl.textContent || "";
      const match = reviewsText.match(/\((\d{1,3}(?:,\d{3})*|\d+)\)/);
      if (match) {
        reviewCount = parseInt(match[1].replace(/,/g, ""), 10);
        Logger.log(`Reviews count detected: ${reviewCount}`);
      }
    }

    // 2. Open Status
    let openStatus = "";
    const spans = card.querySelectorAll("span");
    for (const span of spans) {
      const txt = span.textContent?.trim() || "";
      if (/^(open|closed|temporarily closed)/i.test(txt)) {
        openStatus = txt;
        Logger.log(`Open status detected: ${openStatus}`);
        break;
      }
    }

    // 3. Website Link & Domain
    let websiteUrl = "";
    const websiteEl = card.querySelector("a[aria-label*='Website'], a[data-value*='Website'], a[href*='http']:not([href*='google.com'])");
    if (websiteEl) {
      websiteUrl = websiteEl.href;
      Logger.log(`Website detected: ${websiteUrl}`);
    }
    
    let websiteDomain = "";
    if (websiteUrl) {
      try {
        const urlObj = new URL(websiteUrl);
        websiteDomain = urlObj.hostname.replace("www.", "");
      } catch {}
    }

    // 4. Hotel prices
    let displayedPrice = "";
    let priceCurrency = "";
    let priceType = "";
    const priceRegex = /([₹$£€])\s?(\d{1,3}(?:,\d{3})*|\d+)/;
    for (const el of card.querySelectorAll("span, div")) {
      const text = el.textContent?.trim() || "";
      const match = text.match(priceRegex);
      if (match) {
        displayedPrice = text;
        priceCurrency = match[1];
        priceType = text.toLowerCase().includes("from") ? "from" : "fixed";
        Logger.log(`Hotel price detected: ${displayedPrice}`);
        break;
      }
    }

    // 5. Price Level for Restaurants
    let priceLevel = "";
    for (const el of card.querySelectorAll("span")) {
      const text = el.textContent?.trim() || "";
      if (/^\$+$|^₹+$/.test(text)) {
        priceLevel = text;
        Logger.log(`Price level detected: ${priceLevel}`);
        break;
      }
    }

    // Flexible Metadata JSON payload
    const flexMeta = {};
    if (displayedPrice) flexMeta.hotel_price = displayedPrice;
    if (priceLevel) flexMeta.price_level = priceLevel;
    if (openStatus) flexMeta.open_status = openStatus;
    if (websiteDomain) flexMeta.website_domain = websiteDomain;

    const context = this.getSearchContext();
    Logger.log(`Search query stored: "${context.search_query}"`);

    return {
      batch_id: batchId,
      source_site: this.siteKey,
      business_name: name,
      search_query: context.search_query,
      search_keyword: context.search_keyword,
      search_location: context.search_location,
      directory_search_url: context.directory_search_url,
      collection_date: context.collection_date,
      collection_time: context.collection_time,
      address: address,
      category: category,
      listing_url: listingUrl,
      collection_mode: mode,
      contacts: contacts,
      
      // New fields
      website: websiteUrl || null,
      website_domain: websiteDomain || null,
      rating: rating,
      review_count: reviewCount,
      open_status: openStatus || null,
      displayed_price: displayedPrice || null,
      price_currency: priceCurrency || null,
      price_type: priceType || null,
      price_level: priceLevel || null,
      flexible_metadata: Object.keys(flexMeta).length > 0 ? flexMeta : null,

      // Sprint 4.4 Universal Schema additions
      sub_category: null, // Sub category if split from category
      source_business_id: (() => {
        const match = listingUrl.match(/\/place\/[^/]+\/([^/?]+)/) || listingUrl.match(/!1s([^!]+)/);
        return match ? match[1] : null;
      })(),
      collector_version: "1.0.0",
      secondary_phones: (() => {
        const phoneContacts = contacts.filter(c => c.contact_type === "phone");
        return phoneContacts.length > 1 ? phoneContacts.slice(1).map(c => c.contact_value).join(", ") : null;
      })()
    };
  }
}
window.GoogleMapsAdapter = GoogleMapsAdapter;
