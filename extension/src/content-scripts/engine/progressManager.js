// src/content-scripts/engine/progressManager.js
// ProspectLens — Collection progress manager

class ProgressManager {
  constructor() {
    this.total = 0;
    this.saved = 0;
    this.duplicates = 0;
    this.failed = 0;
    this.current = 0;
  }
  
  reset(total, jobId = null) {
    this.total = total;
    this.saved = 0;
    this.duplicates = 0;
    this.failed = 0;
    this.current = 0;
    this.jobId = jobId;
  }
  
  incrementCurrent() {
    this.current++;
  }
  
  incrementSaved() {
    this.saved++;
  }
  
  incrementDuplicates() {
    this.duplicates++;
  }
  
  incrementFailed() {
    this.failed++;
  }
  
  sendProgress(status = "Extracting...") {
    Messaging.sendProgress(this.current, this.total, this.saved, this.duplicates, this.failed, status, StateManager.getState());
    if (this.jobId) {
      const pct = this.total > 0 ? Math.min(Math.round((this.current / this.total) * 100), 100) : 0;
      Messaging.updateJobProgress(this.jobId, {
        status: StateManager.getState()?.toLowerCase() || "running",
        saved: this.saved,
        duplicates: this.duplicates,
        errors: this.failed,
        skipped: 0,
        total_seen: this.current,
        progress_percentage: pct
      });
    }
  }
  
  sendComplete(batchId) {
    Messaging.sendComplete(batchId, this.total, this.saved, this.duplicates, this.failed);
    if (batchId) {
      Messaging.updateJobStatus(batchId, "completed");
    }
  }
}
window.ProgressManager = ProgressManager;
