// background.js — ProspectLens Background Service Worker
//
// Runs silently in the background at all times while Chrome is open.
// Handles:
// - Extension icon badge (shows lead count)
// - Relaying messages between popup and content scripts
// - Keeping track of active collection jobs

const API_BASE = "http://localhost:8000/api";

// ============================================================
// ON INSTALL — first time extension is loaded
// ============================================================
chrome.runtime.onInstalled.addListener(() => {
  console.log("[ProspectLens] Extension installed successfully");
  updateBadge();
});

// ============================================================
// UPDATE BADGE — shows total lead count on extension icon
// ============================================================
async function updateBadge() {
  try {
    const res  = await fetch(`${API_BASE}/leads/stats`);
    const data = await res.json();
    const total = data.total_leads || 0;

    chrome.action.setBadgeText({
      text: total > 0 ? (total > 999 ? "999+" : String(total)) : ""
    });
    chrome.action.setBadgeBackgroundColor({ color: "#4ade80" });
  } catch {
    // Backend offline — clear badge
    chrome.action.setBadgeText({ text: "" });
  }
}

// ============================================================
// MESSAGE RELAY
// Receives messages from content scripts and popup,
// forwards them to the correct destination.
// ============================================================
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {

  if (message.action === "SAVE_LEAD") {
    fetch(`${API_BASE}/leads`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(message.lead)
    })
    .then(r => r.json())
    .then(data => sendResponse(data))
    .catch(err => {
      console.error("[Background] SAVE_LEAD failed:", err);
      sendResponse({ status: "error", message: err.message });
    });
    return true; // Keep channel open
  }

  if (message.action === "COLLECTION_COMPLETE") {
    fetch(`${API_BASE}/batches/${message.batch_id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "completed" })
    })
    .then(r => r.json())
    .then(data => {
      console.log("[Background] Batch finalized in backend:", data);
      updateBadge();
      
      const batch = data.batch || {};
      const completedMsg = {
        action: "COLLECTION_COMPLETE",
        total: batch.total_listings_found || batch.listings_processed || message.total,
        saved: batch.total_leads_stored !== undefined ? batch.total_leads_stored : batch.successful_records,
        duplicates: batch.duplicate_leads !== undefined ? batch.duplicate_leads : batch.skipped_listings,
        failed: batch.failed_listings || message.failed || 0
      };
      
      // Notify popup
      chrome.runtime.sendMessage(completedMsg);
      sendResponse({ status: "ok", batch: batch });
    })
    .catch(err => {
      console.error("[Background] Finalizing batch failed:", err);
      updateBadge();
      
      const completedMsg = {
        action: "COLLECTION_COMPLETE",
        total: message.total,
        saved: message.saved,
        duplicates: message.duplicates,
        failed: message.failed || 0
      };
      chrome.runtime.sendMessage(completedMsg);
      sendResponse({ status: "error", message: err.message });
    });
    return true; // Keep channel open
  }

  // Popup requesting backend status check
  if (message.action === "CHECK_BACKEND") {
    fetch(`${API_BASE}/health`)
      .then(r => r.json())
      .then(data => sendResponse({ online: data.status === "ok" }))
      .catch(() => sendResponse({ online: false }));
    return true; // Keep message channel open for async response
  }

  return false;
});

// ============================================================
// REFRESH BADGE every 60 seconds
// ============================================================
setInterval(updateBadge, 60000);