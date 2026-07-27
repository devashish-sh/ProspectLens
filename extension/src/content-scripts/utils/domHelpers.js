// src/content-scripts/utils/domHelpers.js
// ProspectLens — Reusable DOM traversal and manipulation helper utilities

const DOMHelpers = {
  sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  },

  filterUniqueCards(elements) {
    const arr = Array.from(elements);
    Logger.log("filterUniqueCards - Raw elements matched count:", arr.length);
    
    // 1. Discard parent grid containers (elements that contain 2 or more other matched elements)
    const nonContainers = arr.filter(el => {
      const containedCount = arr.filter(other => other !== el && el.contains(other)).length;
      return containedCount <= 1;
    });
    Logger.log("filterUniqueCards - Remaining count after container filtering:", nonContainers.length);
    
    // 2. Discard child elements that are nested inside a single card (keep the outer-most wrapper)
    const unique = nonContainers.filter(el => {
      const isContained = nonContainers.some(other => other !== el && other.contains(el));
      return !isContained;
    });

    Logger.log("filterUniqueCards - Unique elements remaining count:", unique.length);
    return unique;
  },

  markWebpageListing(container, statusText, lead) {
    if (!container) return;
    
    // Clean old badges to prevent duplicates
    const old = container.querySelector(".prospectlens-collected-badge");
    if (old) old.remove();

    const badge = document.createElement("div");
    badge.className = "prospectlens-collected-badge";
    badge.style.cssText = "background: #1e1e24; color: #76A544; border: 1px solid #3a3a42; border-radius: 6px; padding: 8px 12px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 10px; margin-top: 8px; display: flex; flex-direction: column; gap: 4px; z-index: 9999; text-align: left; box-shadow: 0 4px 6px rgba(0,0,0,0.1); width: fit-content; max-width: 90%;";
    
    const contactText = lead.contacts && lead.contacts.length 
      ? lead.contacts.map(c => `${c.contact_type === 'phone' ? '📞' : '✉️'} ${c.contact_value}`).join(", ")
      : "No contacts found";
    
    badge.innerHTML = `
      <div style="font-weight: bold; color: #76A544; display: flex; align-items: center; gap: 4px;">
        <span style="font-size: 11px;">✓</span> ${statusText}
      </div>
      <div style="color: #c9c9d4; margin-top: 2px; line-height: 1.4;">
        <strong>Name:</strong> ${lead.business_name}<br/>
        <strong>Location:</strong> ${lead.address || "—"}<br/>
        <strong>Contacts:</strong> ${contactText}
      </div>
    `;
    container.appendChild(badge);
  }
};
window.DOMHelpers = DOMHelpers;
