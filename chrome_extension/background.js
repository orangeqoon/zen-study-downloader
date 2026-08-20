// ZEN Study Downloader Background Worker v7.2
// インメモリ同期管理 ＆ ネイティブ画面キャプチャ（真っ白バグ完全解消）

const tabDataStore = new Map();

function getTabData(tabId) {
  if (!tabDataStore.has(tabId)) {
    tabDataStore.set(tabId, { m3u8: null, slides: [], lastSlideTime: 0 });
  }
  return tabDataStore.get(tabId);
}

// メッセージハンドラ
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  const tabId = msg.tabId !== undefined ? msg.tabId : (sender.tab ? sender.tab.id : -1);

  if (msg.action === "GET_TAB_ID") {
    sendResponse(sender.tab ? sender.tab.id : -1);
    return true;
  }

  if (msg.action === "CLEAR_TAB_DATA") {
    if (tabId !== -1) {
      tabDataStore.set(tabId, { m3u8: null, slides: [], lastSlideTime: 0 });
    }
    sendResponse({ status: "cleared" });
    return true;
  }

  if (msg.action === "GET_TAB_DATA") {
    if (tabId !== -1) {
      const data = getTabData(tabId);
      sendResponse({ m3u8: data.m3u8, slides: data.slides, lastSlideTime: data.lastSlideTime });
    } else {
      sendResponse({ m3u8: null, slides: [], lastSlideTime: 0 });
    }
    return true;
  }

  // ネイティブ画面キャプチャ（Blinkエンジンによる確実なピクセル取得）
  if (msg.action === "CAPTURE_TAB_SCREENSHOT") {
    const windowId = sender.tab ? sender.tab.windowId : null;
    chrome.tabs.captureVisibleTab(windowId, { format: "png" }, (dataUrl) => {
      if (chrome.runtime.lastError || !dataUrl) {
        console.error("[ZEN Extension] Screenshot error:", chrome.runtime.lastError);
        sendResponse({ dataUrl: null });
      } else {
        sendResponse({ dataUrl: dataUrl });
      }
    });
    return true;
  }

  return true;
});

// m3u8リクエストおよび画像リクエストの即時・同期キャプチャ
chrome.webRequest.onBeforeRequest.addListener(
  (details) => {
    const url = details.url;
    if (!url) return;

    const tabId = details.tabId;
    if (tabId === -1) return;

    const data = getTabData(tabId);

    // 1. m3u8 動画
    if (url.includes(".m3u8") && url.includes("Policy=") && url.includes("Signature=")) {
      data.m3u8 = url;
    }

    // 2. スライド画像 (private.png, private.jpg 等)
    if (
      (url.includes("private.png") || url.includes("private.jpg") || url.includes("/slides/") || url.includes("materials/images")) &&
      (url.includes("Policy=") || url.includes("cdn-private"))
    ) {
      if (!data.slides.includes(url)) {
        data.slides.push(url);
        data.lastSlideTime = Date.now();
      }
    }
  },
  { urls: ["*://cdn-private.nnn.ed.nico/*"] }
);
