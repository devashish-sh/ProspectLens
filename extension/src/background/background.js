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

  // Content script finished collecting — update the badge
  if (message.action === "COLLECTION_COMPLETE") {
    updateBadge();
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