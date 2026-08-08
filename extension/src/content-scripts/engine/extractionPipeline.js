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
    const snapshotLeads = [];
    
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
              snapshotLeads.push({
                lead_id: result.lead_id,
                business_name: lead.business_name,
                listing_url: lead.listing_url
              });
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
    
    if (mode === "deep" && !wasCancelled && snapshotLeads.length > 0) {
      await this.runDeepEnrichment(adapter, batchId, snapshotLeads);
    }

    const isStopped = (StateManager.getState() === StateManager.states.STOPPING || StateManager.getState() === StateManager.states.STOPPED);
    if (isStopped) {
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

  async runDeepEnrichment(adapter, batchId, snapshotLeads) {
    Logger.info(`Entering Stage 2: Building queue for ${snapshotLeads.length} leads.`);
    
    // Synchronize progressManager counts for deep enrichment stage
    this.progressManager.total = snapshotLeads.length;
    this.progressManager.current = 0;
    this.progressManager.sendProgress("Building Enrichment Queue...");
    
    try {
      await Messaging.updateJobProgress(batchId, {
        status: "running",
        metadata_json: { stage: "Stage 2: Building Queue", current_stage_name: "Building Queue" }
      });
      await Messaging.createJobQueue(batchId, snapshotLeads);
    } catch (err) {
      Logger.warn("Failed to create job queue in backend:", err);
    }

    Logger.info(`Entering Stage 3: Sequential listing enrichment.`);
    let completedCount = 0;
    let failedCount = 0;
    let retriesCount = 0;

    for (let idx = 0; idx < snapshotLeads.length; idx++) {
      if (StateManager.getState() === StateManager.states.STOPPING || StateManager.getState() === StateManager.states.STOPPED) {
        Logger.info("Deep Enrichment stopped by user.");
        break;
      }
      while (StateManager.getState() === StateManager.states.PAUSED) {
        await DOMHelpers.sleep(500);
      }

      const item = snapshotLeads[idx];
      Logger.info(`Processing queue item ${idx + 1}/${snapshotLeads.length}: ${item.business_name}`);
      
      // Update progressManager current count
      this.progressManager.current = idx;
      
      try {
        await Messaging.updateQueueItemStatus(batchId, item.lead_id, "running");
        await Messaging.updateJobProgress(batchId, {
          status: "running",
          current_listing: item.business_name,
          progress_percentage: Math.round((idx / snapshotLeads.length) * 100),
          metadata_json: {
            stage: "Stage 3: Detailed Enrichment",
            current_index: idx + 1,
            total_items: snapshotLeads.length,
            completed: completedCount,
            failed: failedCount,
            retries: retriesCount
          }
        });
      } catch (err) {}

      // Update progress label for popup UI
      this.progressManager.sendProgress(`Deep Collect: ${idx + 1} / ${snapshotLeads.length}`);

      let success = false;
      let retryAttempt = 0;
      const maxRetries = 2;

      while (retryAttempt <= maxRetries && !success) {
        if (StateManager.getState() === StateManager.states.STOPPING || StateManager.getState() === StateManager.states.STOPPED) {
          break;
        }

        if (retryAttempt > 0) {
          retriesCount++;
          Logger.info(`Retrying queue item ${item.business_name} (Attempt ${retryAttempt}/${maxRetries})`);
          try {
            await Messaging.updateQueueItemStatus(batchId, item.lead_id, "retrying", retryAttempt);
          } catch (err) {}
        }

        try {
          const cardEl = this.findCardEl(item.business_name, item.listing_url);
          if (!cardEl) {
            throw new Error("Listing card element not found in results panel");
          }

          // Scroll into view & click
          cardEl.scrollIntoView({ block: "center" });
          await DOMHelpers.sleep(800);
          
          // Click the card
          const clickTarget = cardEl.querySelector("a") || cardEl;
          if (typeof clickTarget.click === "function") {
            clickTarget.click();
          } else {
            const event = new MouseEvent("click", {
              bubbles: true,
              cancelable: true,
              view: window
            });
            clickTarget.dispatchEvent(event);
          }

          // Wait for business detail panel to load and stabilize
          const panelSelector = adapter.siteKey === "googlemaps" ? "div[role='main']" : ".store-detail";
          const isLoaded = await this.waitPageStable(panelSelector, 12000);
          
          const panelEl = document.querySelector(panelSelector);
          if (!isLoaded) {
            // Fallback: Proceed if panel exists and contains text content, even if it didn't stabilize in time
            if (!panelEl || panelEl.textContent.trim().length < 50) {
              throw new Error("Detail panel failed to load or stabilize within timeout");
            }
            Logger.warn("Detail panel did not fully stabilize, but content is present. Proceeding with extraction...");
          }

          if (!panelEl) {
            throw new Error("Detail panel DOM element not found");
          }

          // Extract detailed listing data
          const deepData = adapter.extractDeepLead(panelEl);
          
          // Merge with existing snapshot lead in DB
          const mergeRes = await Messaging.mergeLeadData(batchId, item.lead_id, deepData);
          if (mergeRes.status !== "ok") {
            throw new Error(`Merge request failed: ${mergeRes.message}`);
          }

          success = true;
          completedCount++;
          Logger.info(`Successfully enriched lead: ${item.business_name}`);
          try {
            await Messaging.updateQueueItemStatus(batchId, item.lead_id, "completed");
          } catch (err) {}
          
          DOMHelpers.markWebpageListing(cardEl, "Enriched", deepData);
          
          // Small delay for natural pacing
          await DOMHelpers.sleep(1500);

        } catch (err) {
          Logger.error(`Error enriching lead '${item.business_name}':`, err);
          retryAttempt++;
          if (retryAttempt > maxRetries) {
            failedCount++;
            try {
              await Messaging.updateQueueItemStatus(batchId, item.lead_id, "failed");
            } catch (err) {}
          } else {
            await DOMHelpers.sleep(2000); // Wait before retry
          }
        }
      }
    }

    try {
      await Messaging.updateJobProgress(batchId, {
        status: "completed",
        progress_percentage: 100,
        metadata_json: {
          stage: "Completed",
          total_items: snapshotLeads.length,
          completed: completedCount,
          failed: failedCount,
          retries: retriesCount
        }
      });
    } catch (err) {}
  }

  findCardEl(businessName, listingUrl) {
    if (listingUrl) {
      const links = document.querySelectorAll("a");
      for (const link of links) {
        const href = link.getAttribute("href") || "";
        if (href && (href.includes(listingUrl) || listingUrl.includes(href))) {
          return link.closest(".Nv2PK") || link.closest(".store-name") || link;
        }
      }
    }
    const spans = document.querySelectorAll("span, div, a");
    const targetName = businessName.toLowerCase().trim();
    for (const el of spans) {
      const text = el.textContent?.trim() || "";
      if (text && text.toLowerCase().trim() === targetName) {
        return el.closest(".Nv2PK") || el.closest(".store-name") || el;
      }
    }
    return null;
  }

  async waitPageStable(selector, timeoutMs = 12000) {
    return new Promise((resolve) => {
      let lastHTML = "";
      let stableTicks = 0;
      const interval = 100;
      let elapsed = 0;

      const timer = setInterval(() => {
        elapsed += interval;
        const el = document.querySelector(selector);
        if (el) {
          const currentHTML = el.innerHTML;
          // Check if HTML is stable and has loaded content
          if (currentHTML === lastHTML && currentHTML.length > 300) {
            stableTicks++;
            if (stableTicks >= 4) { // stable for 400ms
              clearInterval(timer);
              resolve(true);
            }
          } else {
            stableTicks = 0;
            lastHTML = currentHTML;
          }
        }
        
        if (elapsed >= timeoutMs) {
          clearInterval(timer);
          resolve(false);
        }
      }, interval);
    });
  }
}
window.ExtractionPipeline = ExtractionPipeline;
