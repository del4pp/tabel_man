// Content script for OKKO Auth Extractor
// This runs in the ISOLATED world

console.log('🌟 OKKO Auth Extractor content script loaded on:', window.location.href);

// Listen for messages from the Main World script
window.addEventListener('message', function (event) {
  // We only accept messages from ourselves
  if (event.source !== window) return;

  if (event.data.type === 'OKKO_AUTH_CAPTURED') {
    console.log('📨 Content script received token from Main World');
    const payload = event.data.payload;

    // Relay to background script
    chrome.runtime.sendMessage({
      type: 'authCaptured',
      authHeader: payload.authHeader,
      url: payload.url,
      timestamp: payload.timestamp,
      source: payload.source
    }).catch(err => console.error('Error sending to background:', err));
  }
});

// Listen for network requests from this page (Performance API)
// This helps us know if requests are happening, even if we can't read headers here
if (window.performance && window.performance.getEntriesByType) {
  // Check for existing network entries
  const networkEntries = window.performance.getEntriesByType('resource');
  const okkoRequests = networkEntries.filter(entry =>
    entry.name.includes('ssp-online-back.okko.ua')
  );

  if (okkoRequests.length > 0) {
    console.log('📊 Found existing OKKO requests:', okkoRequests.map(r => r.name));
  }
}

// Monitor for new requests (using PerformanceObserver if available)
if (window.PerformanceObserver) {
  const observer = new PerformanceObserver((list) => {
    const entries = list.getEntries();
    entries.forEach(entry => {
      if (entry.name.includes('ssp-online-back.okko.ua')) {
        console.log('📡 New OKKO request observed:', entry.name);
      }
    });
  });

  observer.observe({ entryTypes: ['resource'] });
}

// Handle messages from popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'findFuelPricesRequests') {
    // Try to find fuel prices requests in current page
    const foundRequests = [];

    // Check Performance API for existing requests
    if (window.performance && window.performance.getEntriesByType) {
      const networkEntries = window.performance.getEntriesByType('resource');
      const fuelPricesRequests = networkEntries.filter(entry =>
        entry.name.includes('ssp-online-back.okko.ua/userdata-service/fuel_prices')
      );

      foundRequests.push(...fuelPricesRequests.map(entry => ({
        url: entry.name,
        startTime: entry.startTime,
        duration: entry.duration
      })));
    }

    // Also try to check if there are any stored tokens in localStorage or sessionStorage
    checkForStoredTokens();

    sendResponse({ foundRequests: foundRequests });
  }
});

// Function to check for stored tokens in browser storage
function checkForStoredTokens() {
  try {
    // Check localStorage for auth tokens
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      const value = localStorage.getItem(key);

      if (key && key.toLowerCase().includes('auth') && value && value.includes('eyJ')) {
        console.log('🔍 Found potential auth token in localStorage:', key);
        // We could potentially send this too if we're desperate
      }
    }
  } catch (error) {
    console.log('Could not check storage:', error.message);
  }
}
