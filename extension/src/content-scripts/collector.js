// collector.js — ProspectLens Content Script
//
// This file is injected into IndiaMART, Google Maps, and Justdial pages.
// It reads the DOM (the HTML structure of the page) and extracts
// business listing data, then sends it to the backend via the popup.
//
// HOW IT WORKS:
// 1. Popup sends START_COLLECTION message with batch_id
// 2. This script detects which site it's on
// 3. Calls the correct scraper function for that site
// 4. Sends each lead to the backend API
// 5. Reports progress back to the popup

const API_BASE = "http://localhost:8000/api";

// ============================================================
// LISTEN FOR MESSAGES FROM POPUP
// ============================================================
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "START_COLLECTION") {
    sendResponse({ status: "started" });
    runCollection(message.batch_id, message.mode, message.site);
  }
  return true;
});

// ============================================================
// MAIN COLLECTION ROUTER
// Detects the current site and calls the right scraper
// ============================================================
async function runCollection(batchId, mode, site) {
  const url = window.location.href;

  try {
    if (url.includes("indiamart.com")) {
      await collectIndiaMART(batchId, mode);
    } else if (url.includes("google.com/maps") || url.includes("maps.google.com")) {
      await collectGoogleMaps(batchId, mode);
    } else if (url.includes("justdial.com")) {
      await collectJustdial(batchId, mode);
    } else {
      sendError("Unsupported page. Open IndiaMART, Google Maps, or Justdial.");
    }
  } catch (err) {
    sendError(err.message);
  }
}

// ============================================================
// INDIAMART SCRAPER
// Works on search results pages like:
// https://dir.indiamart.com/search.mp?ss=interior+designer
// ============================================================
async function collectIndiaMART(batchId, mode) {
  // IndiaMART listing card selector — each card is a business
  const cards = document.querySelectorAll(".company-name-box, .supplier-info, .brdcrumb-supplier");

  // Fallback — try alternate selectors if main one finds nothing
  const listingCards = cards.length > 0
    ? cards
    : document.querySelectorAll("[class*='supplier'], [class*='company'], .producttitle");

  if (listingCards.length === 0) {
    sendError("No listings found on this page. Make sure you are on an IndiaMART search results page.");
    return;
  }

  const total  = listingCards.length;
  let saved    = 0;
  let dupes    = 0;
  let failed   = 0;

  for (let i = 0; i < listingCards.length; i++) {
    const card = listingCards[i];

    try {
      // Extract business name
      const nameEl  = card.querySelector("a[class*='company'], .companyname, h3 a, .supplierName") || card;
      const name    = nameEl?.textContent?.trim() || "";

      if (!name) { failed++; continue; }

      // Extract address
      const addrEl  = card.closest("[class*='card'], [class*='supplier'], li")
                        ?.querySelector("[class*='address'], [class*='location'], .addDetail");
      const address = addrEl?.textContent?.trim() || "";

      // Extract phone (sometimes hidden behind click)
      const phoneEl = card.closest("[class*='card'], [class*='supplier'], li")
                        ?.querySelector("[class*='mobile'], [class*='phone'], .call-supp-btn");
      const phone   = phoneEl?.textContent?.trim()?.replace(/[^0-9+\-\s]/g, "") || "";

      // Extract listing URL
      const linkEl  = card.querySelector("a") || card.closest("a");
      const listingUrl = linkEl?.href || window.location.href;

      // Extract category from page title or breadcrumb
      const category = document.querySelector(".searchedKeyword, .srchKey, h1")
                          ?.textContent?.trim() || "";

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
        contacts:        phone ? [{ contact_type: "phone", contact_value: phone, sequence_number: 1, source: "listing" }] : []
      };

      // Send to backend
      const result = await saveLead(lead);
      if (result.status === "saved")      saved++;
      else if (result.status === "duplicate") dupes++;
      else failed++;

    } catch {
      failed++;
    }

    // Report progress after each lead
    sendProgress(i + 1, total);

    // Small delay between saves to avoid hammering the backend
    await sleep(100);
  }

  sendComplete(total, saved, dupes, failed);
}

// ============================================================
// GOOGLE MAPS SCRAPER
// Works on search results like:
// https://www.google.com/maps/search/interior+designer+noida
// ============================================================
async function collectGoogleMaps(batchId, mode) {
  // Google Maps listing items in the sidebar
  const items = document.querySelectorAll(
    "[role='feed'] > div, .Nv2PK, .THOPZb, [class*='result']"
  );

  if (items.length === 0) {
    sendError("No listings found. Make sure you are on a Google Maps search results page with the list view open.");
    return;
  }

  const total = items.length;
  let saved   = 0;
  let dupes   = 0;
  let failed  = 0;

  for (let i = 0; i < items.length; i++) {
    const item = items[i];

    try {
      // Business name
      const nameEl    = item.querySelector(".qBF1Pd, .fontHeadlineSmall, [class*='name'] span");
      const name      = nameEl?.textContent?.trim() || "";
      if (!name) { failed++; continue; }

      // Address / location
      const addrEl    = item.querySelector(".W4Efsd span:not(.W4Efsd), .UsdlK");
      const address   = addrEl?.textContent?.trim() || "";

      // Rating (bonus data point)
      const ratingEl  = item.querySelector(".MW4etd, .ZkP5I");
      const rating    = ratingEl?.textContent?.trim() || "";

      // Listing URL
      const linkEl    = item.querySelector("a[href*='/maps/place/']");
      const listingUrl = linkEl?.href || window.location.href;

      // Category
      const catEl     = item.querySelector(".W4Efsd .W4Efsd span");
      const category  = catEl?.textContent?.trim() || "";

      const lead = {
        batch_id:        batchId,
        source_site:     "googlemaps",
        business_name:   name,
        search_query:    document.querySelector("input#searchboxinput")?.value || "",
        address:         address,
        category:        category,
        listing_url:     listingUrl,
        collection_mode: mode,
        contacts:        []
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
  const cards = document.querySelectorAll(
    ".resultbox_info, .store-details, [class*='resultbox'], .jsx-3473191726"
  );

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
      const nameEl   = card.querySelector(".store-name, .resultbox_title_anchor, [class*='title'] a, h2 a");
      const name     = nameEl?.textContent?.trim() || "";
      if (!name) { failed++; continue; }

      // Address
      const addrEl   = card.querySelector(".addresstxt, [class*='address'], .store-address");
      const address  = addrEl?.textContent?.trim() || "";

      // Phone (Justdial hides numbers — we get what's visible)
      const phoneEl  = card.querySelector(".contact-info span, [class*='phone'], .callnowbutton");
      const phone    = phoneEl?.textContent?.trim()?.replace(/[^0-9+\-\s]/g, "") || "";

      // Category
      const catEl    = card.querySelector(".resultbox_category, [class*='category']");
      const category = catEl?.textContent?.trim() || "";

      // Listing URL
      const linkEl   = card.querySelector("a[href*='justdial']") || card.closest("a");
      const listingUrl = linkEl?.href || window.location.href;

      const lead = {
        batch_id:        batchId,
        source_site:     "justdial",
        business_name:   name,
        search_query:    document.querySelector("input#what-input, .search-text")?.value || category,
        address:         address,
        category:        category,
        listing_url:     listingUrl,
        collection_mode: mode,
        contacts:        phone ? [{ contact_type: "phone", contact_value: phone, sequence_number: 1, source: "listing" }] : []
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
// SAVE LEAD TO BACKEND
// ============================================================
async function saveLead(lead) {
  const res = await fetch(`${API_BASE}/leads`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(lead)
  });
  return await res.json();
}

// ============================================================
// MESSAGING HELPERS
// ============================================================
function sendProgress(done, total) {
  chrome.runtime.sendMessage({ action: "COLLECTION_PROGRESS", done, total });
}

function sendComplete(total, saved, duplicates, failed) {
  chrome.runtime.sendMessage({ action: "COLLECTION_COMPLETE", total, saved, duplicates, failed });
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