// Main World Content Script for OKKO Auth Extractor
// This runs in the MAIN world (same context as the page) to intercept actual network requests

console.log('🌟 OKKO Auth Extractor Main World script loaded');

// Helper to broadcast token
function broadcastToken(token, url, source) {
  if (!token) return;
  
  // Clean the token
  const cleanToken = token.replace(/^Bearer\s+/i, '').trim();
  
  console.log(`✅ OKKO Main World: Found token in ${source}:`, cleanToken.substring(0, 20) + '...');
  
  window.postMessage({
    type: 'OKKO_AUTH_CAPTURED',
    payload: {
      authHeader: cleanToken,
      url: url,
      timestamp: new Date().toISOString(),
      source: `main_world_${source}`
    }
  }, '*');
}

// INTERCEPT FETCH REQUESTS
const originalFetch = window.fetch;
window.fetch = function(...args) {
  const url = args[0];
  const options = args[1] || {};

  if (typeof url === 'string' && url.includes('ssp-online-back.okko.ua/userdata-service/fuel_prices')) {
    // Check for authorization header in options
    if (options.headers) {
      // Headers can be a simple object or a Headers object
      let authHeader = null;
      
      if (options.headers instanceof Headers) {
        authHeader = options.headers.get('Authorization') || options.headers.get('authorization');
      } else {
        authHeader = options.headers.Authorization || options.headers.authorization;
      }

      if (authHeader) {
        broadcastToken(authHeader, url, 'fetch');
      }
    }
  }

  return originalFetch.apply(this, args);
};

// INTERCEPT XMLHttpRequest
const originalOpen = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function(method, url, ...args) {
  if (typeof url === 'string' && url.includes('ssp-online-back.okko.ua/userdata-service/fuel_prices')) {
    this._okkoUrl = url;
  }
  return originalOpen.call(this, method, url, ...args);
};

const originalSetRequestHeader = XMLHttpRequest.prototype.setRequestHeader;
XMLHttpRequest.prototype.setRequestHeader = function(header, value) {
  if (this._okkoUrl && header.toLowerCase() === 'authorization') {
    broadcastToken(value, this._okkoUrl, 'xhr');
  }
  return originalSetRequestHeader.call(this, header, value);
};
