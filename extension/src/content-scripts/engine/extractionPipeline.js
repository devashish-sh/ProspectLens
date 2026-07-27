// src/content-scripts/engine/extractionPipeline.js
// ProspectLens — Core Lead Extraction Pipeline Loop

class ExtractionPipeline {
  constructor() {
    this.queueManager = new QueueManager();
    this.progressManager = new ProgressManager();
    this.scrollManager = new ScrollManager();
  }
  
  async run(adapter, batchId, mode) {
    Logger.log(`Smart Quick Collect started. Selected adapter: ${adapter.constructor.name}`);
    StateManager.setState(StateManager.states.RUNNING);
    this.queueManager.reset();
    
    // 1. Retrieve configured collection limit
    const storage = await chrome.storage.local.get("quickCollectLimit");
    const limitVal = storage.quickCollectLimit || "Unlimited";
    const limit = (limitVal === "Unlimited") ? Infinity : parseInt(limitVal, 10);
    Logger.info(`Configured collection limit: ${limitVal}`);

    // Create managed collection job record in backend
    const context = adapter.getSearchContext();
    Logger.info(`Creating managed collection job: ${batchId}`);
    try {
      await Messaging.createJob(batchId, context, mode, adapter.siteKey);
      await Messaging.updateJobProgress(batchId, { status: "running" });
    } catch (err) {
      Logger.warn("Failed to register collection job in backend:", err);
    }

    this.progressManager.reset(limit === Infinity ? 0 : limit, batchId);
    
    let noNewListingsAttempts = 0;
    let lastScrollHeight = 0;
    let scrollAttemptsWithoutHeightChange = 0;
    let consecutiveAttemptsEmpty = 0;
    
    // Choose appropriate scroll container (role="feed" for Google Maps, window for others)
    let scrollContainer = window;
    if (adapter.siteKey === "googlemaps") {
      const feed = document.querySelector("div[role='feed']");
      if (feed) {
        scrollContainer = feed;
        Logger.log("Google Maps scroll container: div[role='feed']");
      }
    }

    while (true) {
      // 2. Playback State Check: Pause
      if (StateManager.getState() === StateManager.states.PAUSED) {
        Logger.info("Collection Paused. Halting scroll and extraction...");
        this.progressManager.sendProgress("Paused");
        while (StateManager.getState() === StateManager.states.PAUSED) {
          await DOMHelpers.sleep(500);
        }
        if (StateManager.getState() === StateManager.states.RUNNING) {
          Logger.info("Collection Resumed.");
        }
      }
      
      // 3. Playback State Check: Stop
      if (StateManager.getState() === StateManager.states.STOPPING || StateManager.getState() === StateManager.states.STOPPED) {
        Logger.info("Collection Stop requested. Finalizing leads...");
        break;
      }

      // 4. Extraction Phase
      this.progressManager.sendProgress("Extracting...");
      const cards = adapter.findListingCards();
      
      // Filter out cards already processed in this session using queueManager
      const newCards = [];
      for (const card of cards) {
        let name = "";
        try {
          const nameEl = card.querySelector(
            adapter.siteKey === "indiamart" ? ".gcnm, a.gcnm, .comp-name, .company-name" :
            adapter.siteKey === "googlemaps" ? ".qBF1Pd, .fontHeadlineSmall" :
            ".store-name, .resultbox_title_anchor"
          );
          name = nameEl?.textContent?.trim() || "";
        } catch {}
        
        if (name) {
          const fingerprint = name.toLowerCase().trim();
          if (!this.queueManager.isProcessed(fingerprint)) {
            newCards.push(card);
          }
        } else {
          // If name is not found but element exists, process it as a fallback card
          newCards.push(card);
        }
      }

      Logger.log(`Discovered ${newCards.length} new listings (Total found on page: ${cards.length})`);
      
      if (newCards.length > 0) {
        consecutiveAttemptsEmpty = 0;
        
        for (let idx = 0; idx < newCards.length; idx++) {
          // Check limits and playback state inside item iterator
          if (this.progressManager.saved >= limit) {
            Logger.info(`Limit of ${limit} reached. Stopping collection.`);
            break;
          }
          if (StateManager.getState() === StateManager.states.STOPPING || StateManager.getState() === StateManager.states.STOPPED) {
            break;
          }
          if (StateManager.getState() === StateManager.states.PAUSED) {
            break; // Will enter wait loop on next outer loop iteration
          }

          const card = newCards[idx];
          this.progressManager.incrementCurrent();
          
          try {
            const lead = adapter.extractLead(card, batchId, mode);
            if (!lead) {
              Logger.warn(`Lead extraction failed or was skipped for card ${idx + 1}`);
              this.progressManager.incrementFailed();
              this.progressManager.sendProgress("Extracting...");
              continue;
            }
            
            // Mark processed in local session queue to prevent scrolling duplicate processing
            this.queueManager.markProcessed(lead.business_name.toLowerCase().trim());
            
            Logger.log(`Saving lead: "${lead.business_name}"`);
            const result = await Messaging.saveLead(lead);
            Logger.log(`Backend save response for "${lead.business_name}":`, result);
            
            if (result.status === "saved") {
              this.progressManager.incrementSaved();
              DOMHelpers.markWebpageListing(card, "Collected", lead);
            } else if (result.status === "duplicate") {
              this.progressManager.incrementDuplicates();
              DOMHelpers.markWebpageListing(card, "Collected (Duplicate)", lead);
            } else {
              this.progressManager.incrementFailed();
            }
          } catch (err) {
            Logger.error(`Exception while processing card ${idx + 1}:`, err);
            this.progressManager.incrementFailed();
          }
          
          this.progressManager.sendProgress("Extracting...");
          await DOMHelpers.sleep(100);
        }
      } else {
        consecutiveAttemptsEmpty++;
      }

      // Check limit again
      if (this.progressManager.saved >= limit) {
        break;
      }

      // Check if stopped
      if (StateManager.getState() === StateManager.states.STOPPING || StateManager.getState() === StateManager.states.STOPPED) {
        break;
      }

      // 5. Scroll Phase
      this.progressManager.sendProgress("Scrolling...");
      Logger.log("Scroll performed.");
      
      let currentScrollHeight = 0;
      if (scrollContainer === window) {
        currentScrollHeight = document.body.scrollHeight;
        window.scrollBy({ top: 500, behavior: "smooth" });
      } else {
        currentScrollHeight = scrollContainer.scrollHeight;
        scrollContainer.scrollBy({ top: 500, behavior: "smooth" });
      }
      
      // Wait for dynamic listings lazy load
      this.progressManager.sendProgress("Waiting for New Listings...");
      await DOMHelpers.sleep(1500);

      // 6. End-of-Results Detection
      if (currentScrollHeight === lastScrollHeight) {
        scrollAttemptsWithoutHeightChange++;
      } else {
        scrollAttemptsWithoutHeightChange = 0;
        lastScrollHeight = currentScrollHeight;
      }

      // Google Maps specific end of list label check
      let mapsEndTextFound = false;
      if (adapter.siteKey === "googlemaps") {
        const bodyText = document.body.innerText;
        if (bodyText.includes("You've reached the end of the list") || bodyText.includes("reached the end of the list")) {
          mapsEndTextFound = true;
          Logger.info("Google Maps: reached end of list banner detected.");
        }
      }

      // Automatically stop if scroll height is stuck, or multiple scroll attempts find 0 new items
      if (scrollAttemptsWithoutHeightChange >= 5 || consecutiveAttemptsEmpty >= 5 || mapsEndTextFound) {
        Logger.info("End of results detected.");
        this.progressManager.sendProgress("Collection Complete.");
        break;
      }
    }
    
    const wasCancelled = (StateManager.getState() === StateManager.states.STOPPING || StateManager.getState() === StateManager.states.STOPPED);
    Logger.info(`Smart Quick Collect finished. Was cancelled: ${wasCancelled}`);
    
    if (wasCancelled) {
      StateManager.setState(StateManager.states.STOPPED);
      this.progressManager.sendComplete(batchId);
      try {
        await Messaging.updateJobStatus(batchId, "cancelled");
      } catch (err) {}
    } else {
      StateManager.setState(StateManager.states.COMPLETED);
      this.progressManager.sendComplete(batchId);
    }
  }
}
window.ExtractionPipeline = ExtractionPipeline;
