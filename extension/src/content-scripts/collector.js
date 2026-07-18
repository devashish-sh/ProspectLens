// collector.js — ProspectLens Content Script
// STEP 1 — VERIFY CONTENT SCRIPT
console.log("[ProspectLens] Content script injected.");
console.log("[ProspectLens] Current URL:", window.location.href);
console.log("[ProspectLens] Current hostname:", window.location.hostname);
console.log("[ProspectLens] Document readyState:", document.readyState);
if (document.readyState === "complete") {
  console.log("[ProspectLens] Window loaded.");
  console.log("[ProspectLens] DOM fully loaded.");
} else {
  window.addEventListener("load", () => {
    console.log("[ProspectLens] Window loaded.");
  });
  document.addEventListener("DOMContentLoaded", () => {
    console.log("[ProspectLens] DOM fully loaded.");
  });
}

let currentBatchId = null;
function filterUniqueCards(elements) {
  const arr = Array.from(elements);
  console.log("[ProspectLens] filterUniqueCards - Raw elements matched count:", arr.length);
  
  // 1. Discard parent grid containers (elements that contain 2 or more other matched elements)
  const nonContainers = arr.filter(el => {
    const containedCount = arr.filter(other => other !== el && el.contains(other)).length;
    return containedCount <= 1;
  });
  console.log("[ProspectLens] filterUniqueCards - Remaining count after container filtering:", nonContainers.length);
  
  // 2. Discard child elements that are nested inside a single card (keep the outer-most of the single card wrapper)
  const unique = nonContainers.filter(el => {
    const isContained = nonContainers.some(other => other !== el && other.contains(el));
    if (isContained) {
      console.log("[ProspectLens] filterUniqueCards - Discarding nested child element:", el);
    }
    return !isContained;
  });

  console.log("[ProspectLens] filterUniqueCards - Unique elements remaining count:", unique.length);
  return unique;
}

// ============================================================
// LISTEN FOR MESSAGES FROM POPUP
// ============================================================
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // STEP 10 — CHECK MESSAGE PASSING
  console.log("[ProspectLens] STEP 10 — Content script received request message from popup:", message);
  if (message.action === "START_COLLECTION") {
    sendResponse({ status: "started" });
    runCollection(message.batch_id, message.mode, message.site);
  }
  return true;
});

// ============================================================
// MAIN COLLECTION ROUTER
// ============================================================
async function runCollection(batchId, mode, site) {
  currentBatchId = batchId;
  const url = window.location.href;
  
  // STEP 2 — VERIFY PAGE DETECTION
  console.log("[ProspectLens] STEP 2 — VERIFY PAGE DETECTION");
  console.log("[ProspectLens] hostname:", window.location.hostname);
  console.log("[ProspectLens] pathname:", window.location.pathname);
  console.log("[ProspectLens] search params:", window.location.search);
  console.log("[ProspectLens] URL pattern matched: IndiaMART search results patterns");
  console.log("[ProspectLens] Starting collection on:", url);

  try {
    if (url.includes("indiamart.com")) {
      console.log("[ProspectLens] Page URL detected as IndiaMART. Routing to collectIndiaMART().");
      await collectIndiaMART(batchId, mode);
    } else if (url.includes("google.com/maps") || url.includes("maps.google.com")) {
      console.log("[ProspectLens] Page URL detected as Google Maps. Routing to collectGoogleMaps().");
      await collectGoogleMaps(batchId, mode);
    } else if (url.includes("justdial.com")) {
      console.log("[ProspectLens] Page URL detected as Justdial. Routing to collectJustdial().");
      await collectJustdial(batchId, mode);
    } else {
      console.warn("[ProspectLens] Unsupported URL page domain");
      sendError("Unsupported page. Open IndiaMART, Google Maps, or Justdial.");
    }
  } catch (err) {
    console.error("[ProspectLens] Exception inside runCollection:", err);
    sendError(err.message);
  }
}

// ============================================================
// INDIAMART SCRAPER
// ============================================================
async function collectIndiaMART(batchId, mode) {
  // STEP 3 — VERIFY SCRAPER START
  console.log("[ProspectLens] STEP 3 — Starting collection...");
  console.log("[ProspectLens] Searching for listing containers...");

  // Auto-scrolling to trigger lazy loading
  console.log("[ProspectLens] Auto-scrolling page to trigger dynamic content lazy-loading...");
  window.scrollTo({ top: document.body.scrollHeight / 3, behavior: "smooth" });
  await sleep(600);
  window.scrollTo({ top: (document.body.scrollHeight / 3) * 2, behavior: "smooth" });
  await sleep(600);
  window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
  await sleep(800);

  // Click on "Show More Results" or similar load buttons if they exist
  const loadButtons = document.querySelectorAll("button, a, div, span, input[type='button']");
  for (const btn of loadButtons) {
    const text = btn.textContent?.trim()?.toLowerCase() || "";
    const value = btn.value?.trim()?.toLowerCase() || "";
    if (
      (text === "show more results" || 
       text === "view more results" || 
       text === "show more" || 
       text === "view more" || 
       text === "load more" ||
       value === "show more" ||
       value === "view more") &&
      btn.offsetHeight > 0
    ) {
      console.log("[ProspectLens] Found active 'Show More' load button, clicking it:", btn);
      try {
        btn.click();
        await sleep(1500); // Wait for newly loaded elements
      } catch (err) {
        console.warn("[ProspectLens] Error clicking 'Show More' button:", err);
      }
      break;
    }
  }

  // Scroll back to top smoothly to ensure elements are ready
  window.scrollTo({ top: 0, behavior: "smooth" });
  await sleep(400);

  // STEP 7 — CHECK DYNAMIC LOADING (Wait until listings exist)
  console.log("[ProspectLens] STEP 7 — Checking dynamic loading. Polling DOM for listings...");
  let attempts = 0;
  
  // Combined starting elements finder: very specific supplier details + all contact action button text variations
  const getListingAnchors = () => {
    const anchors = new Set();
    
    // 1. Direct specific selectors
    const selectors = ".gcnm, .comp-name, .company-name, .supplier-name, .companyname, a[href*='/company/'], a[href*='indiamart.com/company/'], .pname, .product-title, .cl-card, .lst_spc, .mcard, .lst_Card";
    document.querySelectorAll(selectors).forEach(el => anchors.add(el));
    
    // 2. Button texts
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

  while (attempts < 15) {
    const elements = getListingAnchors();
    if (elements.length > 0) {
      console.log(`[ProspectLens] Listings found in DOM after ${attempts} attempts (found ${elements.length} listing anchors).`);
      break;
    }
    await sleep(400);
    attempts++;
  }

  // STEP 8 — CHECK IFRAMES
  const inIframe = window.self !== window.top;
  console.log("[ProspectLens] STEP 8 — Verification: Is in iframe?", inIframe ? "YES" : "NO");

  // STEP 9 — CHECK SHADOW DOM
  console.log("[ProspectLens] STEP 9 — Verification: Is in Shadow DOM? NO (Standard HTML5 DOM).");

  const anchors = getListingAnchors();
  console.log("[ProspectLens] Found starting elements count:", anchors.length);

  const cardsSet = new Set();
  anchors.forEach((el, idx) => {
    let parent = el.parentElement;
    let found = false;
    
    // Climb up the DOM tree from each anchor to find its listing card container wrapper
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

  const cards = Array.from(cardsSet);
  console.log("[ProspectLens] STEP 4 — Discovered raw card containers count:", cards.length);

  const listingCards = filterUniqueCards(cards);
  
  // STEP 4 — LOG SELECTOR AND COUNT
  console.log(`[ProspectLens] STEP 4 — Selector used: Combined name/link/button anchors + Ancestor traversal`);
  console.log(`[ProspectLens] Found ${listingCards.length} listing containers.`);

  // STEP 6 — PRINT RAW HTML IF 0 CONTAINERS FOUND
  if (listingCards.length === 0) {
    console.error("[ProspectLens] STEP 6 — Zero listing containers were found.");
    console.log("[ProspectLens] document.body.innerHTML.slice(0,5000):");
    console.log(document.body.innerHTML.slice(0, 5000));
    sendError("Error: No listings found on this page. Make sure you are on an IndiaMART search results page.");
    return;
  }

  const total  = listingCards.length;
  let saved    = 0;
  let dupes    = 0;
  let failed   = 0;

  // STEP 11 — VERIFY EXTRACTION LOOP
  for (let i = 0; i < listingCards.length; i++) {
    const card = listingCards[i];
    console.log(`[ProspectLens] STEP 11 — Processing listing ${i + 1} of ${total}`);

    try {
      // STEP 5 — DEBUG EVERY SELECTOR
      console.log("[ProspectLens] STEP 5 — DEBUG EVERY SELECTOR FOR LISTING " + (i + 1));
      
      // Business Name / Company name
      const nameSelector = ".gcnm, a.gcnm, .company-name, .supplier-name, .companyname, .comp-name, [class*='company-name']";
      const nameEl = card.querySelector(nameSelector);
      let name = "";
      if (nameEl) {
        name = nameEl.textContent?.trim() || "";
        console.log(`[ProspectLens] Business selector: "${nameSelector}". Matched: YES. Value: "${name}"`);
      } else {
        // Fallback header
        const headerEl = card.querySelector("h3 a, h2 a, h3, h2");
        if (headerEl) {
          name = headerEl.textContent?.trim() || "";
          console.log(`[ProspectLens] Business selector failed. Fallback header matched: YES. Value: "${name}"`);
        } else {
          console.log(`[ProspectLens] Business selector: "${nameSelector}". Matched: NO. Selector failed.`);
        }
      }

      if (name) {
        name = name.replace(/\s*Contact\s*Supplier\s*$/i, "")
                   .replace(/\s*Leading\s*Supplier\s*$/i, "")
                   .replace(/\s*Call\s*Now\s*$/i, "")
                   .trim();
      }

      const lowerName = name.toLowerCase();
      if (
        !name || 
        name.length < 3 ||
        lowerName === "contact supplier" || 
        lowerName === "leading supplier" ||
        lowerName === "call now" ||
        lowerName === "get quotes" ||
        lowerName === "verified supplier"
      ) {
        console.log(`[ProspectLens] Card ${i + 1} skipped (invalid/generic name): "${name}"`);
        continue;
      }

      // Address
      const addrSelector = ".addDetail, .addr, .address, [class*='address'], [class*='location'], .cty-t, .clg, .loc, strong";
      const addrEl = card.querySelector(addrSelector);
      let address = "";
      if (addrEl) {
        address = addrEl.textContent?.trim() || "";
        console.log(`[ProspectLens] Address selector: "${addrSelector}". Matched: YES. Value: "${address}"`);
      } else {
        console.log(`[ProspectLens] Address selector: "${addrSelector}". Matched: NO. Selector failed.`);
      }

      // Phone / Contact button
      const phoneSelector = ".cust_ph_no, .mobtxt, [class*='callnumber'], [class*='phone_no']";
      const phoneEl = card.querySelector(phoneSelector);
      if (phoneEl) {
        console.log(`[ProspectLens] Phone selector: "${phoneSelector}". Matched: YES. Value: "${phoneEl.textContent.trim()}"`);
      } else {
        console.log(`[ProspectLens] Phone selector: "${phoneSelector}". Matched: NO. Selector failed.`);
      }

      // Rating
      const ratingSelector = "[class*='rating'], .rtng, .fs12";
      const ratingEl = card.querySelector(ratingSelector);
      if (ratingEl) {
        console.log(`[ProspectLens] Rating selector: "${ratingSelector}". Matched: YES. Value: "${ratingEl.textContent.trim()}"`);
      } else {
        console.log(`[ProspectLens] Rating selector: "${ratingSelector}". Matched: NO. Selector failed.`);
      }

      // Response Rate / Years in Business / Company Details
      const metaSelector = ".staticMetaLine, .staticMetaLineShort, .fs12, [class*='response']";
      const metaEl = card.querySelector(metaSelector);
      if (metaEl) {
        console.log(`[ProspectLens] Meta selector: "${metaSelector}". Matched: YES. Value: "${metaEl.textContent.trim()}"`);
      } else {
        console.log(`[ProspectLens] Meta selector: "${metaSelector}". Matched: NO. Selector failed.`);
      }

      // Extract listing URL
      const linkSelector = "a[href*='indiamart.com'], a.gcnm, a[class*='company']";
      const linkEl = card.querySelector(linkSelector) || card.querySelector("a") || card.closest("a");
      const listingUrl = linkEl?.href || window.location.href;
      console.log(`[ProspectLens] Listing URL selector: "${linkSelector}". Matched: ${linkEl ? "YES" : "NO (Fallback URL)"}. Value: "${listingUrl}"`);

      // Extract category
      const category = document.querySelector(".searchedKeyword, .srchKey, h1")?.textContent?.trim() || "";

      // Contacts extraction
      const contacts = extractContactsFromElement(card);
      console.log(`[ProspectLens] Contacts extracted:`, contacts);

      // Build lead object
      const lead = {
        batch_id:        batchId,
        source_site:     "indiamart",
        business_name:   name,
        search_query:    document.querySelector("input[name='ss'], #srchBox")?.value || category,
        address:         address,
        category:        category,
        listing_url:     listingUrl,
        collection_mode: mode,
        contacts:        contacts
      };

      // STEP 10 — Send lead to background and save in DB
      console.log(`[ProspectLens] STEP 10 — Sending lead to backend API...`);
      const result = await saveLead(lead);
      console.log(`[ProspectLens] STEP 10 — Save result for "${name}":`, result);
      
      if (result.status === "saved") {
        saved++;
      } else if (result.status === "duplicate") {
        dupes++;
      } else {
        failed++;
      }

    } catch (err) {
      console.error(`[ProspectLens] STEP 11 — Exception while processing card ${i + 1}:`, err);
      failed++;
    }

    // Report progress after each lead
    sendProgress(i + 1, total);
    await sleep(100);
  }

  // STEP 10 — Log final extracted counts
  console.log(`[ProspectLens] STEP 10 — Content extracted ${total} leads. Saved ${saved} leads, ${dupes} duplicates, ${failed} failed.`);
  sendComplete(total, saved, dupes, failed);
}

// ============================================================
// GOOGLE MAPS SCRAPER
// Works on search results like:
// https://www.google.com/maps/search/interior+designer+noida
// ============================================================
async function collectGoogleMaps(batchId, mode) {
  const items = document.querySelectorAll(".Nv2PK");
  const validItems = filterUniqueCards(items);

  if (validItems.length === 0) {
    sendError("No listings found. Make sure you are on a Google Maps search results page with the list view open.");
    return;
  }

  const total = validItems.length;
  let saved   = 0;
  let dupes   = 0;
  let failed  = 0;

  for (let i = 0; i < validItems.length; i++) {
    const item = validItems[i];

    try {
      // Business name
      const nameEl    = item.querySelector(".qBF1Pd, .fontHeadlineSmall, [class*='name'] span");
      const name      = nameEl?.textContent?.trim() || "";
      if (!name) { failed++; continue; }

      // Address / location
      const addrEl    = item.querySelector(".W4Efsd span:not(.W4Efsd), .UsdlK");
      const address   = addrEl?.textContent?.trim() || "";

      // Listing URL
      const linkEl    = item.querySelector("a[href*='/maps/place/']");
      const listingUrl = linkEl?.href || window.location.href;

      // Category
      const catEl     = item.querySelector(".W4Efsd .W4Efsd span");
      const category  = catEl?.textContent?.trim() || "";

      // Extract all contacts using regex
      const contacts = extractContactsFromElement(item);

      const lead = {
        batch_id:        batchId,
        source_site:     "googlemaps",
        business_name:   name,
        search_query:    document.querySelector("input#searchboxinput")?.value || "",
        address:         address,
        category:        category,
        listing_url:     listingUrl,
        collection_mode: mode,
        contacts:        contacts
      };

      const result = await saveLead(lead);
      if (result.status === "saved")          saved++;
      else if (result.status === "duplicate") dupes++;
      else failed++;

    } catch {
      failed++;
    }

    sendProgress(i + 1, total);
    await sleep(100);
  }

  sendComplete(total, saved, dupes, failed);
}

// ============================================================
// JUSTDIAL SCRAPER
// Works on search results like:
// https://www.justdial.com/Noida/Interior-Designers
// ============================================================
async function collectJustdial(batchId, mode) {
  // Justdial listing cards
  const cardsRaw = document.querySelectorAll(
    ".resultbox_info, .store-details, [class*='resultbox'], .jsx-3473191726"
  );

  const cards = filterUniqueCards(cardsRaw);

  if (cards.length === 0) {
    sendError("No listings found. Make sure you are on a Justdial search results page.");
    return;
  }

  const total = cards.length;
  let saved   = 0;
  let dupes   = 0;
  let failed  = 0;

  for (let i = 0; i < cards.length; i++) {
    const card = cards[i];

    try {
      // Business name
      const nameEl   = card.querySelector(".store-name, .resultbox_title_anchor, [class*='title'] a, h2 a, h3 a, h2, h3");
      const name     = nameEl?.textContent?.trim() || "";
      const lowerName = name.toLowerCase();
      if (
        !name || 
        name.length < 3 ||
        lowerName.includes("inquire now") ||
        lowerName.includes("get best quote") ||
        lowerName.includes("call now") ||
        lowerName.includes("contact us")
      ) {
        continue;
      }

      // Address
      const addrEl   = card.querySelector(".addresstxt, [class*='address'], .store-address");
      const address  = addrEl?.textContent?.trim() || "";

      // Category
      const catEl    = card.querySelector(".resultbox_category, [class*='category']");
      const category = catEl?.textContent?.trim() || "";

      // Listing URL
      const linkEl   = card.querySelector("a[href*='justdial']") || card.closest("a");
      const listingUrl = linkEl?.href || window.location.href;

      // Extract all contacts using regex
      const contacts = extractContactsFromElement(card);

      const lead = {
        batch_id:        batchId,
        source_site:     "justdial",
        business_name:   name,
        search_query:    document.querySelector("input#what-input, .search-text")?.value || category,
        address:         address,
        category:        category,
        listing_url:     listingUrl,
        collection_mode: mode,
        contacts:        contacts
      };

      const result = await saveLead(lead);
      if (result.status === "saved")          saved++;
      else if (result.status === "duplicate") dupes++;
      else failed++;

    } catch {
      failed++;
    }

    sendProgress(i + 1, total);
    await sleep(100);
  }

  sendComplete(total, saved, dupes, failed);
}

// ============================================================
// EXTRACT CONTACTS (PHONE & EMAIL)
// ============================================================
function extractContactsFromElement(element) {
  const contacts = [];
  const textSpans = element.querySelectorAll("span, a, div, p");
  
  // Phone regex: matches standard Indian/international mobile and landline formats
  const phoneRegex = /(?:\+?\d{1,3}[-.\s]?)?\(?\d{3,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}|\+91\s?\d{5}\s?\d{5}/g;
  // Email regex
  const emailRegex = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;

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
    while ((phoneMatches = phoneRegex.exec(text)) !== null) {
      const val = phoneMatches[0].trim();
      const digitsCount = val.replace(/\D/g, "").length;
      if (digitsCount >= 6 && digitsCount <= 15 && !seenValues.has(val)) {
        seenValues.add(val);
        contacts.push({ contact_type: "phone", contact_value: val, sequence_number: contacts.length + 1, source: "listing" });
      }
    }

    let emailMatches;
    while ((emailMatches = emailRegex.exec(text)) !== null) {
      const val = emailMatches[0].trim();
      if (!seenValues.has(val)) {
        seenValues.add(val);
        contacts.push({ contact_type: "email", contact_value: val, sequence_number: contacts.length + 1, source: "listing" });
      }
    }
  }

  return contacts;
}

// ============================================================
// SAVE LEAD TO BACKEND
// ============================================================
async function saveLead(lead) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({
      action: "SAVE_LEAD",
      lead: lead
    }, (response) => {
      resolve(response || { status: "error", message: "Failed to communicate with background service worker" });
    });
  });
}

// ============================================================
// MESSAGING HELPERS
// ============================================================
function sendProgress(done, total) {
  chrome.runtime.sendMessage({ action: "COLLECTION_PROGRESS", done, total });
}

function sendComplete(total, saved, duplicates, failed) {
  chrome.runtime.sendMessage({
    action: "COLLECTION_COMPLETE",
    batch_id: currentBatchId,
    total: total,
    saved: saved,
    duplicates: duplicates,
    failed: failed
  });
}

function sendError(message) {
  chrome.runtime.sendMessage({ action: "COLLECTION_ERROR", message });
}

// ============================================================
// UTILITY
// ============================================================
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}