// src/content-scripts/engine/queueManager.js
// ProspectLens — Collection local run queue manager

class QueueManager {
  constructor() {
    this.processedLeads = new Set();
  }
  
  reset() {
    this.processedLeads.clear();
  }
  
  isProcessed(leadFingerprint) {
    return this.processedLeads.has(leadFingerprint);
  }
  
  markProcessed(leadFingerprint) {
    this.processedLeads.add(leadFingerprint);
  }
}
window.QueueManager = QueueManager;
