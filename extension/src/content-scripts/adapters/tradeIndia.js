// src/content-scripts/adapters/tradeIndia.js
// ProspectLens — Skeleton adapter for future TradeIndia support

class TradeIndiaAdapter extends BaseAdapter {
  constructor() {
    super("tradeindia");
  }

  detectSupportedPage(url) {
    return url.includes("tradeindia.com");
  }

  findListingCards() {
    Logger.warn("[TradeIndiaAdapter] findListingCards() not implemented yet.");
    return [];
  }

  extractLead(card, batchId, mode) {
    Logger.warn("[TradeIndiaAdapter] extractLead() not implemented yet.");
    return null;
  }
}
window.TradeIndiaAdapter = TradeIndiaAdapter;
