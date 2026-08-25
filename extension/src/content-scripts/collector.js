// collector.js — ProspectLens content script coordinator
// Coordinates page detection, adapter loading, and triggers the extraction loop.

Logger.info("Content script injected and loaded successfully.");
Logger.log("Current URL:", window.location.href);

// Instantiate supported website adapters
const adapters = [
  new GoogleMapsAdapter(),
  new IndiaMartAdapter(),
  new JustdialAdapter(),
  new TradeIndiaAdapter()
];

// ============================================================
// LISTEN FOR MESSAGES FROM POPUP
// ============================================================
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  Logger.log("Received message from popup:", message);
  
  if (message.action === "PING") {
    sendResponse({ status: "pong" });
    return true;
  }
  
  if (message.action === "START_COLLECTION") {
    sendResponse({ status: "started" });
    
    // Detect active adapter based on current page URL
    const url = window.location.href;
    const adapter = adapters.find(a => a.detectSupportedPage(url));
    
    if (adapter) {
      Logger.info(`Adapter selected: ${adapter.constructor.name}. Initializing pipeline...`);
      const pipeline = new ExtractionPipeline();
      pipeline.run(adapter, message.batch_id, message.mode);
    } else {
      Logger.warn(`No supported adapter found for URL: ${url}`);
      Messaging.sendError("Unsupported page. Open Google Maps, IndiaMART, Justdial, or TradeIndia.");
    }
  } else if (message.action === "PAUSE_COLLECTION") {
    StateManager.setState(StateManager.states.PAUSED);
    Logger.info("Playback: PAUSED requested.");
    sendResponse({ status: "paused" });
  } else if (message.action === "RESUME_COLLECTION") {
    StateManager.setState(StateManager.states.RUNNING);
    Logger.info("Playback: RESUME requested.");
    sendResponse({ status: "resumed" });
  } else if (message.action === "STOP_COLLECTION") {
    StateManager.setState(StateManager.states.STOPPING);
    Logger.info("Playback: STOP requested.");
    sendResponse({ status: "stopping" });
  }
  return true;
});