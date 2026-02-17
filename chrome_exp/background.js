// Background service worker for OKKO Auth Extractor

console.log('🚀 Service worker starting...');

// Try to set up webRequest if available
if (typeof chrome.webRequest !== 'undefined') {
  console.log('✅ webRequest API available, setting up listeners');

  try {
    // Set up webRequest listeners
    chrome.webRequest.onBeforeSendHeaders.addListener(
      onBeforeSendHeaders,
      {
        urls: ["*://ssp-online-back.okko.ua/*"]
      },
      ["requestHeaders", "extraHeaders"]
    );

    chrome.webRequest.onSendHeaders.addListener(
      onSendHeaders,
      {
        urls: ["*://ssp-online-back.okko.ua/*"]
      },
      ["requestHeaders", "extraHeaders"]
    );

    console.log('✅ WebRequest listeners set up successfully');
  } catch (error) {
    console.error('❌ Failed to set up webRequest listeners:', error.message);
  }
} else {
  console.log('⚠️ webRequest API not available, using content script only');
}

// WebRequest handler functions
function onBeforeSendHeaders(details) {
  if (details.url.includes('/userdata-service/fuel_prices')) {
    console.log('🌐 webRequest: Fuel prices request intercepted:', details.url);

    const authHeader = details.requestHeaders.find(header =>
      header.name.toLowerCase() === 'authorization'
    );

    if (authHeader) {
      console.log('✅ webRequest: Found authorization header');
      storeAuthHeader(authHeader.value, details.url, 'webrequest_before');
    }
  }
  return { requestHeaders: details.requestHeaders };
}

function onSendHeaders(details) {
  if (details.url.includes('/userdata-service/fuel_prices')) {
    console.log('📤 webRequest: Send headers for fuel prices');

    const authHeader = details.requestHeaders.find(header =>
      header.name.toLowerCase() === 'authorization'
    );

    if (authHeader) {
      console.log('✅ webRequest: Found authorization header in send headers');
      storeAuthHeader(authHeader.value, details.url, 'webrequest_send');
    }
  }
}

function storeAuthHeader(authHeader, url, source) {
  console.log('🔄 Processing auth header:', authHeader.substring(0, 50) + '...');

  // Remove "Bearer " prefix if present
  const cleanToken = authHeader.replace(/^Bearer\s+/i, '').trim();

  console.log('🧹 Cleaned token:', cleanToken.substring(0, 50) + '...');

  chrome.storage.local.set({
    'lastAuthHeader': cleanToken,
    'lastAuthTime': new Date().toISOString(),
    'lastAuthUrl': url
  }, function() {
    console.log('💾 Auth header stored from', source, '- final token length:', cleanToken.length);

    // Send message to popup
    console.log('📨 Sending auth token to popup - length:', cleanToken.length);
    chrome.runtime.sendMessage({
      type: 'authCaptured',
      authHeader: cleanToken,
      url: url,
      timestamp: new Date().toISOString(),
      source: source
    }).catch(() => {});
  });
}

// Handle messages from popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('📨 Background received message:', message.type);

  if (message.type === 'getStoredAuth') {
    chrome.storage.local.get(['lastAuthHeader', 'lastAuthTime', 'lastAuthUrl'], (result) => {
      console.log('📤 Sending stored auth data:', result.lastAuthHeader ? result.lastAuthHeader.substring(0, 30) + '...' : 'none');
      sendResponse(result);
    });
    return true; // Keep the message channel open for async response
  }

  if (message.type === 'testRequest') {
    console.log('🧪 Making test request to OKKO API...');
    fetch('https://ssp-online-back.okko.ua/userdata-service/fuel_prices', {
      method: 'GET',
      headers: {
        'Authorization': 'Bearer test-token-from-extension-12345',
        'User-Agent': 'Test Request from Extension',
        'Accept': 'application/json'
      }
    }).then(response => {
      console.log('🧪 Test request completed:', response.status);
      sendResponse({ success: true, status: response.status });
    }).catch(error => {
      console.error('🧪 Test request failed:', error);
      sendResponse({ success: false, error: error.message });
    });
    return true;
  }

  if (message.type === 'checkListenerStatus') {
    console.log('🔍 Listener status: using content script interception only');
    sendResponse({ hasListener: false, method: 'content_script' });
    return true;
  }
});
