// background.js — ProspectLens Background Service Worker
//
// Runs silently in the background at all times while Chrome is open.
// Handles:
// - Extension icon badge (shows lead count)
// - Relaying messages between popup and content scripts
// - Keeping track of active collection jobs

import { EngineManager } from "./engine_manager.js";

const API_BASE = "http://localhost:8000/api";

// Initialize Engine Manager
EngineManager.init();

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

const jobTimings = {};

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {

  if (message.action === "START_ENGINE") {
    EngineManager.startEngine().then(result => sendResponse(result));
    return true; // Keep channel open
  }

  if (message.action === "STOP_ENGINE") {
    EngineManager.stopEngine().then(result => sendResponse(result));
    return true; // Keep channel open
  }

  if (message.action === "RESTORE_DEFAULT_LAUNCHER") {
    EngineManager.restoreDefaultLauncherPath().then(() => sendResponse({ success: true }));
    return true; // Keep channel open
  }

  if (message.action === "SAVE_LAUNCHER_PATH") {
    EngineManager.setLauncherPath(message.path).then(() => sendResponse({ success: true }));
    return true; // Keep channel open
  }

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
    chrome.storage.local.set({
      activeJobId: null,
      activeJobTabId: null
    });
    const finalStatus = message.isCancelled ? "cancelled" : "completed";
    fetch(`${API_BASE}/batches/${message.batch_id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: finalStatus })
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
        failed: batch.failed_listings || message.failed || 0,
        isCancelled: !!message.isCancelled,
        mode: batch.collection_mode || message.mode || "quick"
      };
      
      // Notify popup
      chrome.runtime.sendMessage(completedMsg);
      
      // Trigger system notification if not manually stopped
      if (!message.isCancelled) {
        showCollectionNotification(message.batch_id, completedMsg);
      }
      
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
        failed: message.failed || 0,
        isCancelled: !!message.isCancelled,
        mode: message.mode || "quick"
      };
      chrome.runtime.sendMessage(completedMsg);
      
      // Trigger system notification if not manually stopped
      if (!message.isCancelled) {
        showCollectionNotification(message.batch_id, completedMsg);
      }
      
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

  if (message.action === "CREATE_JOB") {
    // Record snapshot start time
    const jobId = message.jobId;
    const tabId = sender.tab ? sender.tab.id : null;
    chrome.storage.local.set({
      activeJobId: jobId,
      activeJobTabId: tabId
    });
    jobTimings[jobId] = {
      snapshot_start: Date.now(),
      snapshot_time: 0,
      queue_start: 0,
      queue_time: 0,
      merge_start_times: {},
      merge_times: []
    };

    fetch(`${API_BASE}/collection-jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_id: message.jobId,
        source: message.source,
        mode: message.mode,
        search_keyword: message.searchKeyword,
        search_query: message.searchQuery,
        search_location: message.searchLocation,
        search_url: message.searchUrl
      })
    })
    .then(r => r.json())
    .then(data => sendResponse(data))
    .catch(err => {
      console.error("[Background] CREATE_JOB failed:", err);
      sendResponse({ status: "error", message: err.message });
    });
    return true; // Keep channel open
  }

  if (message.action === "UPDATE_JOB_PROGRESS") {
    fetch(`${API_BASE}/collection-jobs/${message.jobId}/progress`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(message.progress)
    })
    .then(r => r.json())
    .then(data => sendResponse(data))
    .catch(err => {
      console.error("[Background] UPDATE_JOB_PROGRESS failed:", err);
      sendResponse({ status: "error", message: err.message });
    });
    return true; // Keep channel open
  }

  if (message.action === "UPDATE_JOB_STATUS") {
    if (["completed", "failed", "cancelled"].includes(message.status)) {
      chrome.storage.local.set({
        activeJobId: null,
        activeJobTabId: null
      });
    }
    const jobId = message.jobId;
    let metadata = null;
    if (jobTimings[jobId]) {
      const timings = jobTimings[jobId];
      const totalMergeTime = timings.merge_times.reduce((a, b) => a + b, 0);
      metadata = {
        snapshot_time: timings.snapshot_time || 0.0,
        queue_time: timings.queue_time || 0.0,
        merge_time: totalMergeTime || 0.0
      };
      delete jobTimings[jobId];
    }

    fetch(`${API_BASE}/collection-jobs/${message.jobId}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
        status: message.status,
        metadata_json: metadata
      })
    })
    .then(r => r.json())
    .then(data => sendResponse(data))
    .catch(err => {
      console.error("[Background] UPDATE_JOB_STATUS failed:", err);
      sendResponse({ status: "error", message: err.message });
    });
    return true; // Keep channel open
  }

  if (message.action === "CREATE_JOB_QUEUE") {
    const jobId = message.jobId;
    if (jobTimings[jobId]) {
      jobTimings[jobId].snapshot_time = (Date.now() - jobTimings[jobId].snapshot_start) / 1000;
      jobTimings[jobId].queue_start = Date.now();
    }

    fetch(`${API_BASE}/collection-jobs/${message.jobId}/queue`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: message.items })
    })
    .then(r => r.json())
    .then(data => {
      if (jobTimings[message.jobId] && jobTimings[message.jobId].queue_start) {
        jobTimings[message.jobId].queue_time = (Date.now() - jobTimings[message.jobId].queue_start) / 1000;
      }
      sendResponse(data);
    })
    .catch(err => {
      console.error("[Background] CREATE_JOB_QUEUE failed:", err);
      sendResponse({ status: "error", message: err.message });
    });
    return true; // Keep channel open
  }

  if (message.action === "UPDATE_QUEUE_ITEM_STATUS") {
    fetch(`${API_BASE}/collection-jobs/${message.jobId}/queue/${message.leadId}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: message.status, retry_count: message.retryCount })
    })
    .then(r => r.json())
    .then(data => sendResponse(data))
    .catch(err => {
      console.error("[Background] UPDATE_QUEUE_ITEM_STATUS failed:", err);
      sendResponse({ status: "error", message: err.message });
    });
    return true; // Keep channel open
  }

  if (message.action === "MERGE_LEAD_DATA") {
    const jobId = message.jobId;
    const leadId = message.leadId;
    if (jobTimings[jobId]) {
      jobTimings[jobId].merge_start_times[leadId] = Date.now();
    }

    fetch(`${API_BASE}/collection-jobs/${message.jobId}/queue/${message.leadId}/merge`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(message.deepData)
    })
    .then(r => r.json())
    .then(data => {
      if (jobTimings[message.jobId] && jobTimings[message.jobId].merge_start_times[message.leadId]) {
        const dur = (Date.now() - jobTimings[message.jobId].merge_start_times[message.leadId]) / 1000;
        jobTimings[message.jobId].merge_times.push(dur);
      }
      sendResponse(data);
    })
    .catch(err => {
      console.error("[Background] MERGE_LEAD_DATA failed:", err);
      sendResponse({ status: "error", message: err.message });
    });
    return true; // Keep channel open
  }

  if (message.action === "COLLECTION_ERROR") {
    chrome.storage.local.set({
      activeJobId: null,
      activeJobTabId: null
    });
    return false;
  }

  return false;
});

// ============================================================
// REFRESH BADGE every 60 seconds
// ============================================================
setInterval(updateBadge, 60000);

// ============================================================
// SYSTEM NOTIFICATIONS
// ============================================================
const shownNotifications = new Set();

function showCollectionNotification(batchId, details) {
  if (!batchId) return;
  if (shownNotifications.has(batchId)) {
    console.log(`[Background] Notification already shown for job ${batchId}. Ignoring.`);
    return;
  }
  shownNotifications.add(batchId);

  const isDeep = details.mode === "deep";
  const title = "ProspectLens";
  let messageText = "";

  if (isDeep) {
    messageText = `Deep Collect Complete\n${details.total} processed • ${details.saved} enriched • ${details.failed} failed`;
  } else {
    messageText = `Quick Collect Complete\n${details.total} processed • ${details.saved} saved • ${details.duplicates} duplicates`;
  }

  chrome.notifications.create(batchId, {
    type: "basic",
    iconUrl: "icons/icon128.png",
    title: title,
    message: messageText,
    priority: 2
  }, (id) => {
    if (chrome.runtime.lastError) {
      console.error("[Background] Notification creation failed:", chrome.runtime.lastError);
    } else {
      console.log("[Background] Notification shown successfully:", id);
    }
  });
}