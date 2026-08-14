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

    const panelText = panel.textContent || "";

    // 1. Description
    const descEl = panel.querySelector(".PYv55, .WeSNe, [class*='description']");
    if (descEl) result.flexible_metadata.description = descEl.textContent.trim();

    // 2. Business Hours
    const hoursTable = panel.querySelector("table.e24EBf, [class*='hours'] table");
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

    // 3. Category (Robust detail panel category detection)
    const categoryEl = panel.querySelector("button[class*='DkE7Z'], [class*='fontBodyMedium'][class*='R812Of']");
    if (categoryEl) {
      result.category = categoryEl.textContent.trim();
    } else {
      const ratingEl = panel.querySelector(".F7nice");
      if (ratingEl && ratingEl.nextElementSibling) {
        result.category = ratingEl.nextElementSibling.textContent.trim();
      }
    }

    // 4. Address, City, State, Country, Postal Code (Robust Address Fallbacks)
    let address = "";
    // Scan all interactive elements inside panel for address indicators
    const panelElements = panel.querySelectorAll("button, a, div.CsEnBe");
    for (const el of panelElements) {
      const itemId = el.getAttribute("data-item-id") || "";
      const label = el.getAttribute("aria-label") || "";
      const text = el.textContent?.trim() || "";
      
      if (itemId === "address" || itemId.includes("address")) {
        const io = el.querySelector(".Io6YTe")?.textContent?.trim() || text;
        if (io) { address = io; break; }
      }
      
      if (label && /address:/i.test(label)) {
        address = label.replace(/address:/i, "").trim();
        break;
      }
      
      // If the text contains a 6-digit PIN code (India) and is short enough
      if (/\b[1-9][0-9]{5}\b/.test(text) && text.length < 150) {
        if (!text.includes("+91") && !text.includes("tel:") && !text.includes("http") && !text.includes("reviews") && !text.includes("stars")) {
          address = text;
          break;
        }
      }
    }

    // Direct element fallbacks if list scanner missed it
    if (!address) {
      const addrEl = panel.querySelector("[data-item-id*='address'], [data-item-id='address']");
      if (addrEl) {
        address = addrEl.querySelector(".Io6YTe")?.textContent?.trim() || addrEl.textContent?.trim();
      }
    }
    if (!address) {
      const addrButton = panel.querySelector("button[aria-label*='Address:'], button[aria-label*='address:'], a[aria-label*='Address:'], a[aria-label*='address:']");
      if (addrButton) {
        const label = addrButton.getAttribute("aria-label");
        const match = label.match(/Address:\s*(.*)/i);
        address = match ? match[1].trim() : addrButton.textContent.trim();
      }
    }

    if (address) {
      result.address = address;
      const pinMatch = address.match(/\b([1-9][0-9]{5})\b/);
      if (pinMatch) {
        result.postal_code = pinMatch[1];
      }

      const parts = address.split(",").map(p => p.trim());
      if (parts.length >= 2) {
        const statePart = parts[parts.length - 1];
        const cityPart = parts[parts.length - 2];
        result.city = cityPart.replace(/\d+/g, "").trim();
        result.state = statePart.replace(/\d+/g, "").trim();
      }
    }

    console.debug("[ProspectLens Debug] Address element details:", { 
      timestamp: Date.now(),
      addressEl: panel.querySelector("[data-item-id*='address'], [data-item-id='address']"), 
      extracted: address 
    });

    // 5. Phone numbers & Alternate phones (Robust Phone Fallbacks)
    let phone = "";
    const telLink = panel.querySelector("a[href^='tel:']");
    if (telLink) {
      phone = telLink.getAttribute("href").replace("tel:", "").trim();
    }
    if (!phone) {
      const phoneEl = panel.querySelector("[data-item-id*='phone']");
      if (phoneEl) {
        phone = phoneEl.querySelector(".Io6YTe")?.textContent?.trim() || phoneEl.textContent?.trim();
      }
    }
    if (!phone) {
      const phoneButton = panel.querySelector("button[aria-label*='Phone:'], button[aria-label*='phone:'], a[aria-label*='Phone:'], a[aria-label*='phone:']");
      if (phoneButton) {
        const label = phoneButton.getAttribute("aria-label");
        const match = label.match(/Phone:\s*(.*)/i);
        phone = match ? match[1].trim() : phoneButton.textContent.trim();
      }
    }
    if (!phone) {
      const phoneRegex = /\b(?:\+?91|0)?[-\s]?[6-9]\d{2,4}[-\s]?\d{2,4}[-\s]?\d{3,5}\b|\b0\d{2,4}[-\s]?\d{3,4}[-\s]?\d{3,4}\b|\b1800[-\s]?\d{3,4}[-\s]?\d{3,4}\b/;
      const match = panelText.match(phoneRegex);
      if (match) {
        phone = match[0];
      }
    }

    if (phone) {
      result.primary_phone = Normalizer.normalizeIndianPhone(phone);
    }

    const phoneRegexAll = /\b(?:\+?91|0)?[-\s]?[6-9]\d{2,4}[-\s]?\d{2,4}[-\s]?\d{3,5}\b|\b0\d{2,4}[-\s]?\d{3,4}[-\s]?\d{3,4}\b|\b1800[-\s]?\d{3,4}[-\s]?\d{3,4}\b/g;
    const allPhones = panelText.match(phoneRegexAll);
    if (allPhones && allPhones.length > 0) {
      const normalizedList = allPhones.map(p => Normalizer.normalizeIndianPhone(p)).filter(p => p !== "");
      const uniquePhones = Array.from(new Set(normalizedList));
      const primaryNorm = result.primary_phone || "";
      const alternates = uniquePhones.filter(p => p !== primaryNorm);
      if (alternates.length > 0) {
        result.secondary_phones = alternates.slice(0, 3).join(", ");
      }
    }

    // 6. Website & Domain (Robust Website Fallbacks)
    let website = "";
    const webEl = panel.querySelector("[data-item-id='authority']");
    if (webEl) {
      website = (webEl.tagName === "A" ? webEl.getAttribute("href") : null) || 
                webEl.querySelector("a")?.getAttribute("href") || 
                webEl.textContent?.trim();
    }
    if (!website) {
      const webButton = panel.querySelector("a[aria-label*='Website'], a[data-value*='Website']");
      if (webButton) {
        website = webButton.getAttribute("href") || webButton.textContent.trim();
      }
    }
    if (!website) {
      const links = panel.querySelectorAll("a");
      for (const link of links) {
        const href = link.getAttribute("href") || "";
        if (href.startsWith("http") || href.includes("google.com/url") || href.includes("google.co.in/url")) {
          const cleanUrl = Normalizer.cleanWebsiteUrl(href);
          if (cleanUrl && !/youtube\.com|facebook\.com|instagram\.com|twitter\.com|linkedin\.com|x\.com/.test(cleanUrl)) {
            website = cleanUrl;
            break;
          }
        }
      }
    }

    if (website) {
      const cleanUrl = Normalizer.cleanWebsiteUrl(website);
      if (cleanUrl) {
        result.website = cleanUrl;
        try {
          const parsed = new URL(cleanUrl);
          result.website_domain = parsed.hostname.replace("www.", "");
        } catch {}
      }
    }

    console.debug("[ProspectLens Debug] Website element details:", { 
      timestamp: Date.now(),
      webEl: panel.querySelector("[data-item-id='authority']"), 
      extracted: website 
    });

    // 6.5 Email heuristic fallback
    const emails = panelText.match(/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b/g);
    if (emails && emails.length > 0) {
      result.primary_email = emails[0];
    }

    // 7. Links (Reservation, Booking, Menu, Directions, Socials)
    const reservEl = panel.querySelector("[data-item-id='action:1'], [data-item-id='reservations'], a[href*='reserve'], a[href*='booking']");
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

    // 8. Coordinates
    const url_href = window.location.href;
    const coordMatch = url_href.match(/@(-?\d+\.\d+),(-?\d+\.\d+)/);
    if (coordMatch) {
      result.flexible_metadata.latitude = parseFloat(coordMatch[1]);
      result.flexible_metadata.longitude = parseFloat(coordMatch[2]);
    }

    // 9. Plus Code
    const plusEl = panel.querySelector("[data-item-id='oloc']");
    if (plusEl) result.flexible_metadata.plus_code = plusEl.querySelector(".Io6YTe")?.textContent?.trim() || null;

    // 10. Attributes / Amenities / Accessibility
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

    // 11. Popular times
    const popEl = panel.querySelector("[aria-label*='Popular times'], [aria-label*='busy']");
    if (popEl) {
      result.flexible_metadata.popular_times = popEl.getAttribute("aria-label") || popEl.textContent?.trim();
    }

    // 12. Photos
    const photoBtns = panel.querySelectorAll("button[aria-label*='Photo'], button[aria-label*='Image']");
    const photoUrls = [];
    photoBtns.forEach(btn => {
      const img = btn.querySelector("img");
      if (img) photoUrls.push(img.src);
    });
    if (photoUrls.length > 0) result.flexible_metadata.photo_urls = photoUrls;

    // 13. Owner claimed
    const unclaimed = panelText.includes("Claim this business");
    result.flexible_metadata.owner_claimed = !unclaimed;

    // 14. Hotel Prices
    const hotelPriceMatch = panelText.match(/(?:Rs\.?|INR|₹|\$)\s*\d+(?:,\d+)*(?:\.\d+)?/g);
    if (hotelPriceMatch && (panelText.toLowerCase().includes("hotel") || panelText.toLowerCase().includes("stay"))) {
      result.flexible_metadata.hotel_prices = Array.from(new Set(hotelPriceMatch));
    }

    // 15. Price Level
    const priceLevelEl = panel.querySelector(".fontBodyMedium");
    const priceLevelMatch = priceLevelEl?.textContent?.match(/([$₹€£]+)/);
    if (priceLevelMatch) {
      result.price_level = priceLevelMatch[1];
    }

    // 16. Business Status
    if (panelText.includes("Temporarily closed")) {
      result.flexible_metadata.business_status = "Temporarily Closed";
    } else if (panelText.includes("Permanently closed")) {
      result.flexible_metadata.business_status = "Permanently Closed";
    } else {
      result.flexible_metadata.business_status = "Active";
    }

    // 17. Rating & Reviews
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

    // Format Contacts Array
    const contacts = [];
    if (result.primary_phone) {
      contacts.push({ contact_type: "phone", contact_value: result.primary_phone, sequence_number: 1, source: "deep_collect" });
    }
    if (result.primary_email) {
      contacts.push({ contact_type: "email", contact_value: result.primary_email, sequence_number: 1, source: "deep_collect" });
    }
    if (result.secondary_phones) {
      const secPhones = result.secondary_phones.split(",").map(p => p.trim());
      secPhones.forEach((p, index) => {
        contacts.push({ contact_type: "phone", contact_value: p, sequence_number: index + 2, source: "deep_collect" });
      });
    }
    if (result.flexible_metadata.social_links) {
      result.flexible_metadata.social_links.forEach(link => {
        let type = "social";
        if (link.includes("facebook")) type = "facebook";
        else if (link.includes("instagram")) type = "instagram";
        else if (link.includes("linkedin")) type = "linkedin";
        else if (link.includes("twitter") || link.includes("x.com")) type = "twitter";
        else if (link.includes("youtube")) type = "youtube";
        contacts.push({ contact_type: type, contact_value: link, sequence_number: 1, source: "deep_collect" });
      });
    }
    if (contacts.length > 0) {
      result.contacts = contacts;
    }

    return result;
  }
}
window.GoogleMapsAdapter = GoogleMapsAdapter;
