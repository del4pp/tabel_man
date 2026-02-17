// Popup script for OKKO Auth Extractor

console.log('Popup script loaded');

document.addEventListener('DOMContentLoaded', function() {
  const statusDiv = document.getElementById('status');
  const authContainer = document.getElementById('auth-container');
  const authHeaderDiv = document.getElementById('auth-header');
  const timestampDiv = document.getElementById('timestamp');
  const urlDiv = document.getElementById('url');
  const copyBtn = document.getElementById('copy-btn');
  const findBtn = document.getElementById('find-btn');
  const clearBtn = document.getElementById('clear-btn');
  const findInstructions = document.getElementById('find-instructions');
  const testResult = document.getElementById('test-result');

  console.log('Popup DOM loaded');

  // Load stored auth data
  loadStoredAuth();

  // Listen for new auth captures from background script or content script
  chrome.runtime.onMessage.addListener((message) => {
    console.log('Popup received message:', message);
    if (message.type === 'authCaptured') {
      updateAuthDisplay(message.authHeader, message.url, message.timestamp, message.source);
    }
  });

  // Copy button functionality
  copyBtn.addEventListener('click', function() {
    const authHeader = authHeaderDiv.textContent;
    navigator.clipboard.writeText(authHeader).then(() => {
      copyBtn.textContent = 'Скопійовано!';
      setTimeout(() => {
        copyBtn.textContent = 'Копіювати';
      }, 2000);
    });
  });

  // Find button functionality
  findBtn.addEventListener('click', function() {
    const isVisible = findInstructions.style.display !== 'none';
    if (isVisible) {
      // Hide instructions
      findInstructions.style.display = 'none';
      testResult.style.display = 'none';
      findBtn.textContent = 'Знайти запит';
    } else {
      // Show instructions and start search
      findInstructions.style.display = 'block';
      findBtn.textContent = 'Шукаю...';
      testResult.style.display = 'block';
      testResult.textContent = 'Шукаю запити до fuel_prices API...';

      // Try to find existing requests via content script
      findExistingRequests();

      // Also try to refresh the page to catch new requests
      setTimeout(() => {
        if (!hasAuthData()) {
          testResult.textContent = 'Не знайдено існуючих запитів. Спробую оновити сторінку...';
          refreshCurrentTab();
        }
      }, 2000);
    }
  });

  // Function to check if we already have auth data
  function hasAuthData() {
    return authContainer.style.display !== 'none';
  }

  // Function to find existing requests via content script
  function findExistingRequests() {
    chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
      if (tabs[0]) {
        chrome.tabs.sendMessage(tabs[0].id, { type: 'findFuelPricesRequests' }, function(response) {
          if (chrome.runtime.lastError) {
            console.log('No content script response (this is normal)');
            return;
          }

          if (response && response.foundRequests && response.foundRequests.length > 0) {
            testResult.textContent = `Знайдено ${response.foundRequests.length} запитів. Шукаю authorization headers...`;
            // Content script will handle the actual token extraction
          }
        });
      }
    });
  }

  // Clear button functionality
  clearBtn.addEventListener('click', function() {
    chrome.storage.local.clear(function() {
      console.log('Storage cleared');
      // Reset UI
      authContainer.style.display = 'none';
      statusDiv.style.display = 'block';
      statusDiv.className = 'status waiting';
      statusDiv.textContent = 'Очікування запиту до fuel_prices API...';
      findInstructions.style.display = 'none';
      testResult.style.display = 'none';
      findBtn.textContent = 'Знайти запит';

      // Show confirmation
      testResult.style.display = 'block';
      testResult.textContent = '✅ Дані очищено!';
      setTimeout(() => {
        testResult.style.display = 'none';
      }, 2000);
    });
  });

  // Function to refresh current tab
  function refreshCurrentTab() {
    chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
      if (tabs[0]) {
        chrome.tabs.reload(tabs[0].id);
        testResult.textContent = 'Сторінка оновлена. Чекаю на запит fuel_prices...';
      }
    });
  }

  function loadStoredAuth() {
    console.log('Loading stored auth data...');
    chrome.runtime.sendMessage({ type: 'getStoredAuth' }, (response) => {
      console.log('Received stored auth response:', response);
      if (chrome.runtime.lastError) {
        console.error('Message error:', chrome.runtime.lastError);
        showWaitingStatus();
        return;
      }

      if (response && response.lastAuthHeader) {
        console.log('Found stored auth header, updating display');
        updateAuthDisplay(response.lastAuthHeader, response.lastAuthUrl, response.lastAuthTime);
      } else {
        console.log('No stored auth header found, showing waiting status');
        showWaitingStatus();
      }
    });
  }

  function updateAuthDisplay(authHeader, url, timestamp, source) {
    // Hide status div when auth data is available
    statusDiv.style.display = 'none';

    authContainer.style.display = 'block';
    authHeaderDiv.textContent = authHeader;

    if (timestamp) {
      const date = new Date(timestamp);
      let sourceText = '';
      if (source === 'manual_import') {
        sourceText = ' (імпортовано з Network)';
      } else if (source) {
        sourceText = ` (${source})`;
      }
      timestampDiv.textContent = `Час: ${date.toLocaleString('uk-UA')}${sourceText}`;
    }

    if (url) {
      urlDiv.textContent = `URL: ${url}`;
    }
  }

  function showWaitingStatus() {
    statusDiv.style.display = 'block';
    statusDiv.className = 'status waiting';
    statusDiv.textContent = 'Очікування запиту до fuel_prices API...';
    authContainer.style.display = 'none';
  }
});
