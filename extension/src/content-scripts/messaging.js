// src/content-scripts/messaging.js
// ProspectLens — Extension message relay system

const Messaging = {
  saveLead(lead) {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage({
        action: "SAVE_LEAD",
        lead: lead
      }, (response) => {
        resolve(response || { status: "error", message: "Failed to communicate with background service worker" });
      });
    });
  },
  
  sendProgress(done, total, saved, duplicates, failed, status, state = "Running") {
    chrome.storage.local.set({
      collectionProgress: {
        state,
        current: done,
        total,
        saved,
        duplicates,
        failed,
        status
      }
    });
    chrome.runtime.sendMessage({ action: "COLLECTION_PROGRESS", done, total, saved, duplicates, failed, status });
  },
  
  sendComplete(batchId, total, saved, duplicates, failed) {
    chrome.storage.local.set({
      collectionProgress: {
        state: "Completed",
        current: total,
        total,
        saved,
        duplicates,
        failed,
        status: "Collection Complete"
      }
    });
    chrome.runtime.sendMessage({
      action: "COLLECTION_COMPLETE",
      batch_id: batchId,
      total: total,
      saved: saved,
      duplicates: duplicates,
      failed: failed
    });
  },
  
  sendError(message) {
    chrome.storage.local.set({
      collectionProgress: {
        state: "Failed",
        status: `Error: ${message}`
      }
    });
    chrome.runtime.sendMessage({ action: "COLLECTION_ERROR", message });
  },

  createJob(jobId, context, mode, source) {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage({
        action: "CREATE_JOB",
        jobId: jobId,
        source: source,
        mode: mode,
        searchKeyword: context.search_keyword,
        searchQuery: context.search_query,
        searchLocation: context.search_location,
        searchUrl: context.directory_search_url
      }, (response) => {
        resolve(response || { status: "error" });
      });
    });
  },

  updateJobProgress(jobId, progressData) {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage({
        action: "UPDATE_JOB_PROGRESS",
        jobId: jobId,
        progress: progressData
      }, (response) => {
        resolve(response || { status: "error" });
      });
    });
  },

  updateJobStatus(jobId, finalStatus) {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage({
        action: "UPDATE_JOB_STATUS",
        jobId: jobId,
        status: finalStatus
      }, (response) => {
        resolve(response || { status: "error" });
      });
    });
  }
};
window.Messaging = Messaging;
