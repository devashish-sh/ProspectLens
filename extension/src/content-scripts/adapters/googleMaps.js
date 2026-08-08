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
    const websiteEl = card.querySelector("a[aria-label*='Website'], a[data-value*='Website'], a[href*='http']");
    if (websiteEl) {
      const rawUrl = websiteEl.href;
      const cleanUrl = Normalizer.cleanWebsiteUrl(rawUrl);
      if (cleanUrl && !cleanUrl.includes("google.com")) {
        websiteUrl = cleanUrl;
        Logger.log(`Website detected: ${websiteUrl}`);
      }
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

  extractDeepLead(panel) {
    const result = {
      flexible_metadata: {}
    };

    // 1. Description
    const descEl = panel.querySelector(".PYv55, .WeSNe");
    if (descEl) result.flexible_metadata.description = descEl.textContent.trim();

    // 2. Business Hours
    const hoursTable = panel.querySelector("table.e24EBf");
    if (hoursTable) {
      const rows = Array.from(hoursTable.querySelectorAll("tr"));
      const hoursMap = {};
      rows.forEach(row => {
        const day = row.querySelector("td:nth-child(1)")?.textContent?.trim();
        const hours = row.querySelector("td:nth-child(2)")?.textContent?.trim();
        if (day && hours) hoursMap[day] = hours;
      });
      result.flexible_metadata.business_hours = hoursMap;
    }

    // 3. Website & Domain
    const webEl = panel.querySelector("[data-item-id='authority']");
    if (webEl) {
      const url = webEl.querySelector("a")?.getAttribute("href") || webEl.textContent?.trim();
      if (url) {
        const cleanUrl = Normalizer.cleanWebsiteUrl(url);
        result.website = cleanUrl;
        try {
          const parsed = new URL(cleanUrl);
          result.website_domain = parsed.hostname.replace("www.", "");
        } catch {}
      }
    }

    // 3.5 Regex heuristics from panel text content (Emails & Alt Phones)
    const panelText = panel.textContent || "";
    const emails = panelText.match(/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b/g);
    if (emails && emails.length > 0) {
      result.primary_email = emails[0];
    }

    // 4. Phone numbers
    const phoneEl = panel.querySelector("[data-item-id*='phone']");
    if (phoneEl) {
      const phoneText = phoneEl.querySelector(".Io6YTe")?.textContent?.trim();
      if (phoneText) {
        result.primary_phone = phoneText;
      }
    }

    // 4.5 Extract alternate phone numbers using a standard regex fallback
    const phoneRegex = /\b(?:(?:\+|0{0,2})91[\s\-]*)?[6-9]\d{9}\b/g;
    const phones = panelText.match(phoneRegex);
    if (phones && phones.length > 0) {
      const uniquePhones = Array.from(new Set(phones.map(p => p.trim())));
      const primaryDigits = result.primary_phone ? result.primary_phone.replace(/\D/g, "") : "";
      const alternates = uniquePhones.filter(p => p.replace(/\D/g, "") !== primaryDigits);
      if (alternates.length > 0) {
        result.secondary_phones = alternates.slice(0, 3).join(", ");
      }
    }

    // 5. Links (Reservation, Booking, Menu, Directions, Socials)
    const reservEl = panel.querySelector("[data-item-id='action:1'], [data-item-id='reservations']");
    if (reservEl) result.flexible_metadata.reservation_link = reservEl.querySelector("a")?.getAttribute("href") || reservEl.getAttribute("href") || null;

    const bookingEl = panel.querySelector("[data-item-id='action:2'], [data-item-id='booking']");
    if (bookingEl) result.flexible_metadata.booking_link = bookingEl.querySelector("a")?.getAttribute("href") || bookingEl.getAttribute("href") || null;

    const menuEl = panel.querySelector("[data-item-id='menu'], a[href*='menu'], [aria-label*='Menu']");
    if (menuEl) result.flexible_metadata.order_link = menuEl.querySelector("a")?.getAttribute("href") || menuEl.getAttribute("href") || null;

    const directionsEl = panel.querySelector("a[href*='dir/'], [aria-label*='Directions']");
    if (directionsEl) result.flexible_metadata.directions_url = directionsEl.getAttribute("href") || directionsEl.querySelector("a")?.getAttribute("href") || null;

    const socialLinks = [];
    panel.querySelectorAll("a").forEach(a => {
      const href = a.getAttribute("href") || "";
      if (/facebook\.com|instagram\.com|twitter\.com|linkedin\.com|youtube\.com|x\.com/.test(href)) {
        socialLinks.push(href);
      }
    });
    if (socialLinks.length > 0) {
      result.flexible_metadata.social_links = socialLinks;
    }

    // 6. Coordinates (from page URL)
    const url_href = window.location.href;
    const coordMatch = url_href.match(/@(-?\d+\.\d+),(-?\d+\.\d+)/);
    if (coordMatch) {
      result.flexible_metadata.latitude = parseFloat(coordMatch[1]);
      result.flexible_metadata.longitude = parseFloat(coordMatch[2]);
    }

    // 7. Plus Code
    const plusEl = panel.querySelector("[data-item-id='oloc']");
    if (plusEl) result.flexible_metadata.plus_code = plusEl.querySelector(".Io6YTe")?.textContent?.trim() || null;

    // 8. Attributes / Amenities / Accessibility
    const attrRows = panel.querySelectorAll(".fontBodyMedium");
    const amenities = [];
    attrRows.forEach(row => {
      const text = row.textContent?.trim();
      if (text && text.includes("·")) {
        amenities.push(text);
      }
    });
    if (amenities.length > 0) {
      result.flexible_metadata.amenities = amenities;
    }

    const accessibility = [];
    const accessibilityTerms = [
      "Wheelchair accessible entrance",
      "Wheelchair accessible restroom",
      "Wheelchair accessible seating",
      "Wheelchair accessible parking lot"
    ];
    accessibilityTerms.forEach(term => {
      if (panelText.includes(term)) {
        accessibility.push(term);
      }
    });
    if (accessibility.length > 0) {
      result.flexible_metadata.accessibility_features = accessibility;
    }

    // 9. Popular times
    const popEl = panel.querySelector("[aria-label*='Popular times'], [aria-label*='busy']");
    if (popEl) {
      result.flexible_metadata.popular_times = popEl.getAttribute("aria-label") || popEl.textContent?.trim();
    }

    // 10. Photos
    const photoBtns = panel.querySelectorAll("button[aria-label*='Photo'], button[aria-label*='Image']");
    const photoUrls = [];
    photoBtns.forEach(btn => {
      const img = btn.querySelector("img");
      if (img) photoUrls.push(img.src);
    });
    if (photoUrls.length > 0) result.flexible_metadata.photo_urls = photoUrls;

    // 11. Owner Information (Claimed vs Unclaimed)
    const unclaimed = panelText.includes("Claim this business");
    result.flexible_metadata.owner_claimed = !unclaimed;

    // 12. Hotel Prices (If hotel)
    const hotelPriceMatch = panelText.match(/(?:Rs\.?|INR|₹|\$)\s*\d+(?:,\d+)*(?:\.\d+)?/g);
    if (hotelPriceMatch && (panelText.toLowerCase().includes("hotel") || panelText.toLowerCase().includes("stay"))) {
      result.flexible_metadata.hotel_prices = Array.from(new Set(hotelPriceMatch));
    }

    // 13. Price Level
    const priceLevelEl = panel.querySelector(".fontBodyMedium");
    const priceLevelMatch = priceLevelEl?.textContent?.match(/([$₹€£]+)/);
    if (priceLevelMatch) {
      result.price_level = priceLevelMatch[1];
    }

    // 14. Business Status
    if (panelText.includes("Temporarily closed")) {
      result.flexible_metadata.business_status = "Temporarily Closed";
    } else if (panelText.includes("Permanently closed")) {
      result.flexible_metadata.business_status = "Permanently Closed";
    } else {
      result.flexible_metadata.business_status = "Active";
    }

    // 15. Rating & Reviews fallback
    const ratingEl = panel.querySelector(".F7nice");
    if (ratingEl) {
      const ratingText = ratingEl.querySelector("span[aria-hidden='true']")?.textContent?.trim();
      const reviewsText = ratingEl.querySelector("span[aria-label*='reviews']")?.getAttribute("aria-label") || ratingEl.querySelector("span[aria-label*='Reviews']")?.getAttribute("aria-label");
      if (ratingText) result.rating = parseFloat(ratingText);
      if (reviewsText) {
        const count = parseInt(reviewsText.replace(/\D/g, ""));
        if (!isNaN(count)) result.review_count = count;
      }
    }

    return result;
  }
}
window.GoogleMapsAdapter = GoogleMapsAdapter;
