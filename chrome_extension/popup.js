const LOCAL_SERVER = "http://localhost:5000";

document.addEventListener("DOMContentLoaded", async () => {
  const qualitySelect = document.getElementById("quality");
  const folderInput = document.getElementById("download-folder");
  const saveBtn = document.getElementById("save-btn");
  const msg = document.getElementById("msg");
  const statusIndicator = document.getElementById("status-indicator");

  // Local storage settings
  chrome.storage.local.get(["quality", "downloadFolder"], (data) => {
    if (data.quality) qualitySelect.value = data.quality;
    if (data.downloadFolder) folderInput.value = data.downloadFolder;
  });

  // Check server status
  try {
    const res = await fetch(`${LOCAL_SERVER}/status`, { signal: AbortSignal.timeout(2000) });
    if (res.ok) {
      statusIndicator.textContent = "サーバー接続中";
      statusIndicator.className = "status-badge status-online";

      // Load server settings if available
      try {
        const settingsRes = await fetch(`${LOCAL_SERVER}/settings`);
        if (settingsRes.ok) {
          const cfg = await settingsRes.json();
          if (cfg.quality && !qualitySelect.value) qualitySelect.value = cfg.quality;
          if (cfg.download_folder && !folderInput.value) folderInput.value = cfg.download_folder;
        }
      } catch (e) {}
    } else {
      throw new Error();
    }
  } catch (e) {
    statusIndicator.textContent = "サーバー未起動";
    statusIndicator.className = "status-badge status-offline";
  }

  saveBtn.addEventListener("click", async () => {
    const quality = qualitySelect.value;
    const downloadFolder = folderInput.value.trim();

    chrome.storage.local.set({ quality, downloadFolder }, async () => {
      try {
        await fetch(`${LOCAL_SERVER}/settings`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ quality, download_folder: downloadFolder })
        });
      } catch (e) {}

      msg.textContent = "設定を保存しました！";
      msg.style.color = "#34d399";
      msg.style.display = "block";
      setTimeout(() => { msg.style.display = "none"; }, 2500);
    });
  });
});
