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
  
  sendComplete(batchId, total, saved, duplicates, failed, isCancelled = false, mode = "quick") {
    chrome.storage.local.set({
      collectionProgress: {
        state: isCancelled ? "Stopped" : "Completed",
        current: total,
        total,
        saved,
        duplicates,
        failed,
        status: isCancelled ? "Collection Stopped" : "Collection Complete",
        mode: mode
      }
    });
    chrome.runtime.sendMessage({
      action: "COLLECTION_COMPLETE",
      batch_id: batchId,
      total: total,
      saved: saved,
      duplicates: duplicates,
      failed: failed,
      isCancelled: isCancelled,
      mode: mode
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
  },

  createJobQueue(jobId, items) {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage({
        action: "CREATE_JOB_QUEUE",
        jobId: jobId,
        items: items
      }, (response) => {
        resolve(response || { status: "error" });
      });
    });
  },

  updateQueueItemStatus(jobId, leadId, status, retryCount = 0) {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage({
        action: "UPDATE_QUEUE_ITEM_STATUS",
        jobId: jobId,
        leadId: leadId,
        status: status,
        retryCount: retryCount
      }, (response) => {
        resolve(response || { status: "error" });
      });
    });
  },

  mergeLeadData(jobId, leadId, deepLeadData) {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage({
        action: "MERGE_LEAD_DATA",
        jobId: jobId,
        leadId: leadId,
        deepData: deepLeadData
      }, (response) => {
        resolve(response || { status: "error" });
      });
    });
  }
};
window.Messaging = Messaging;
