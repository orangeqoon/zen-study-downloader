// ZEN Study Downloader Content Script v1.0.0
// 完全同期キャプチャ ＆ スライド順序保証 ＆ 授業・動画番号付き命名 ＆ フォルダ名完全統一
(function () {
  'use strict';
  console.log("[ZEN Downloader v1.0.0] Content script initialized.");

  const LOCAL_SERVER = "http://localhost:5000/download";
  let isProcessing = false;
  let myTabId = -1;

  // 章タイトルの整形（01. 01. 等の重複数字や第1章などのプレフィックスを完全整理）
  function formatChapterTitle(rawTitle, fallbackIndex) {
    if (!rawTitle) rawTitle = "";
    let clean = rawTitle.replace(/^(?:第?\s*\d+\s*[章回\.\:\-]?\s*)+/i, '').trim();
    if (!clean) clean = rawTitle.trim() || `第${fallbackIndex || 1}章`;

    let chapNum = fallbackIndex;
    if (!chapNum) {
      const m = rawTitle.match(/\d+/);
      chapNum = m ? parseInt(m[0], 10) : 1;
    }
    const numPrefix = String(chapNum).padStart(2, '0');
    return `${numPrefix}. ${clean}`;
  }

  async function getCsrfToken() {
    try {
      const res = await fetch("https://api.nnn.ed.nico/v1/tokens/csrf", { method: "POST", credentials: "include" });
      if (res.ok) {
        const data = await res.json();
        return data.token || "";
      }
    } catch (e) {}
    return "";
  }

  function getPageInfo() {
    const pathname = location.pathname;
    const chapterMatch = pathname.match(/\/courses\/(\d+)\/chapters\/(\d+)/);
    if (chapterMatch) return { type: "chapter", courseId: chapterMatch[1], chapterId: chapterMatch[2] };
    const courseMatch = pathname.match(/\/courses\/(\d+)/);
    if (courseMatch) return { type: "course", courseId: courseMatch[1] };
    return null;
  }

  function extractChaptersFromDOM(courseId) {
    const links = Array.from(document.querySelectorAll('a[href*="/chapters/"]'));
    const chapterMap = new Map();
    links.forEach((a) => {
      const m = a.href.match(/\/courses\/(\d+)\/chapters\/(\d+)/);
      if (m && m[1] === courseId) {
        const chapId = m[2];
        if (!chapterMap.has(chapId)) {
          let titleText = (a.innerText || a.textContent || "").replace(/[\r\n]+/g, " ").trim();
          chapterMap.set(chapId, { courseId, chapterId: chapId, title: titleText || `第${chapterMap.size + 1}章` });
        }
      }
    });
    return Array.from(chapterMap.values());
  }

  async function getCourseChapters(courseId, csrfToken) {
    let chapters = extractChaptersFromDOM(courseId);
    if (chapters.length > 0) return chapters;
    try {
      const res = await fetch(`https://api.nnn.ed.nico/v2/material/courses/${courseId}?revision=1`, { credentials: "include", headers: csrfToken ? { "X-CSRF-Token": csrfToken } : {} });
      if (res.ok) {
        const data = await res.json();
        const apiChapters = data.course?.chapters || data.chapters || [];
        return apiChapters.map((c, idx) => ({ courseId, chapterId: String(c.id), title: c.title || `第${idx + 1}章` }));
      }
    } catch (e) {}
    return chapters;
  }

  async function fetchChapterDetails(courseId, chapterId, csrfToken) {
    const res = await fetch(`https://api.nnn.ed.nico/v2/material/courses/${courseId}/chapters/${chapterId}?revision=1`, { credentials: "include", headers: csrfToken ? { "X-CSRF-Token": csrfToken } : {} });
    if (!res.ok) throw new Error(`API error`);
    const data = await res.json();
    const sections = data.chapter?.sections || [];
    const chapterTitle = data.chapter?.title || "";
    const movies = sections.filter((s) => s.resource_type === "movie").map((s, idx) => ({ index: idx + 1, title: s.title, contentUrl: s.content_url, movieId: s.id }));
    return { chapterTitle, movies };
  }

  async function initTabId() {
    if (myTabId === -1) {
      myTabId = await new Promise((r) => chrome.runtime.sendMessage({ action: "GET_TAB_ID" }, r));
    }
  }

  function getCapturedDataFromBackground() {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage({ action: "GET_TAB_DATA", tabId: myTabId }, (res) => {
        resolve(res || { m3u8: null, slides: [], lastSlideTime: 0 });
      });
    });
  }

  function clearCapturedDataInBackground() {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage({ action: "CLEAR_TAB_DATA", tabId: myTabId }, (res) => {
        resolve(res);
      });
    });
  }

  async function inspectMovieResources(item) {
    await clearCapturedDataInBackground();

    return new Promise((resolve) => {
      let resolved = false;

      const iframe = document.createElement("iframe");
      iframe.style.cssText = "position:fixed;bottom:0;right:0;width:1px;height:1px;opacity:0.01;pointer-events:none;border:none;";
      iframe.src = item.contentUrl;

      const startTime = Date.now();
      let lastSlideCount = 0;
      let stableCountSince = Date.now();

      const interval = setInterval(async () => {
        if (resolved) return;

        const captured = await getCapturedDataFromBackground();
        const slideCount = captured.slides.length;

        if (slideCount !== lastSlideCount) {
          lastSlideCount = slideCount;
          stableCountSince = Date.now();
        }

        const elapsed = Date.now() - startTime;
        const stableDuration = Date.now() - stableCountSince;

        if (captured.m3u8 && ( (slideCount > 0 && stableDuration >= 1200) || elapsed >= 4500 )) {
          finish(captured);
          return;
        }

        if (elapsed >= 7500) {
          finish(captured);
          return;
        }
      }, 300);

      function finish(captured) {
        if (!resolved) {
          resolved = true;
          clearInterval(interval);
          try { iframe.remove(); } catch (e) {}
          resolve({ m3u8Url: captured.m3u8, images: captured.slides });
        }
      }

      document.body.appendChild(iframe);
    });
  }

  // -----------------------------------------------------------
  // モード1: スライド画像だけを一括ダウンロード（授業単位）
  // -----------------------------------------------------------
  async function runSlidesOnlyBatch(courseId, btn) {
    chrome.storage.local.set({ batchInProgress: true });
    btn.innerHTML = `<span>⏳</span><span>スライド解析中...</span>`;

    await initTabId();
    const csrfToken = await getCsrfToken();
    const chapters = await getCourseChapters(courseId, csrfToken);

    if (!chapters || chapters.length === 0) {
      alert("チャプターを取得できませんでした。");
      isProcessing = false;
      return;
    }

    const totalChapters = chapters.length;
    let grandTotalSlides = 0;

    for (let chapIdx = 0; chapIdx < totalChapters; chapIdx++) {
      const chap = chapters[chapIdx];
      const chapNum = chapIdx + 1;

      let chapterTitle = "", movies = [];
      try {
        const data = await fetchChapterDetails(courseId, chap.chapterId, csrfToken);
        const rawTitle = data.chapterTitle || chap.title || "";
        chapterTitle = formatChapterTitle(rawTitle, chapNum);
        movies = data.movies || [];
      } catch (e) {}

      const chapterSlidesList = [];
      if (movies.length > 0) {
        for (let mIdx = 0; mIdx < movies.length; mIdx++) {
          const item = movies[mIdx];
          btn.innerHTML = `<span>⏳</span><span>[章 ${chapNum}/${totalChapters}] [動画 ${item.index}/${movies.length}] スライド抽出中...</span>`;
          const res = await inspectMovieResources(item);

          (res.images || []).forEach((imgUrl, sIdx) => {
            chapterSlidesList.push({
              url: imgUrl,
              movie_index: item.index,
              movie_title: item.title,
              slide_index: sIdx + 1
            });
          });
        }
      }

      if (chapterSlidesList.length > 0) {
        grandTotalSlides += chapterSlidesList.length;
        await new Promise((resDone) => {
          chrome.storage.local.get(["downloadFolder"], async (settings) => {
            const payload = {
              type: "slides_only",
              chapter_title: chapterTitle,
              images: chapterSlidesList,
              download_folder: settings.downloadFolder || ""
            };
            try {
              await fetch(LOCAL_SERVER, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
            } catch (e) {
              alert("ZEN Downloader サーバーが起動していません。ZEN_Downloader.exe を起動してください。");
            }
            resDone();
          });
        });
      }
    }

    btn.style.opacity = "1";
    btn.innerHTML = `<span style="font-size:16px;">🎉</span><span>全${totalChapters}章 (${grandTotalSlides}枚) のスライド保存完了！</span>`;
    chrome.storage.local.set({ batchInProgress: false });
    setTimeout(() => { isProcessing = false; renderButtons(); }, 8000);
  }

  // -----------------------------------------------------------
  // モード2: 全コース（動画 ＋ スライド画像）を一括ダウンロード
  // -----------------------------------------------------------
  async function runFullCourseBatch(courseId, btn) {
    chrome.storage.local.set({ batchInProgress: true });
    btn.innerHTML = `<span>⏳</span><span>解析中...</span>`;

    await initTabId();
    const csrfToken = await getCsrfToken();
    const chapters = await getCourseChapters(courseId, csrfToken);

    if (!chapters || chapters.length === 0) {
      alert("チャプターを取得できませんでした。");
      isProcessing = false;
      return;
    }

    const totalChapters = chapters.length;

    for (let chapIdx = 0; chapIdx < totalChapters; chapIdx++) {
      const chap = chapters[chapIdx];
      const chapNum = chapIdx + 1;

      let chapterTitle = "", movies = [];
      try {
        const data = await fetchChapterDetails(courseId, chap.chapterId, csrfToken);
        const rawTitle = data.chapterTitle || chap.title || "";
        chapterTitle = formatChapterTitle(rawTitle, chapNum);
        movies = data.movies || [];
      } catch (e) {}

      if (movies.length > 0) {
        const totalMovies = movies.length;
        for (let mIdx = 0; mIdx < totalMovies; mIdx++) {
          const item = movies[mIdx];
          btn.innerHTML = `<span>⏳</span><span>[章 ${chapNum}/${totalChapters}] [${item.index}/${totalMovies}] 抽出中...</span>`;

          const res = await inspectMovieResources(item);
          const formattedSlides = (res.images || []).map((imgUrl, sIdx) => ({
            url: imgUrl,
            movie_index: item.index,
            movie_title: item.title,
            slide_index: sIdx + 1
          }));

          if (res.m3u8Url || formattedSlides.length > 0) {
            await new Promise((resDone) => {
              chrome.storage.local.get(["quality", "downloadFolder"], async (settings) => {
                const payload = {
                  type: "video",
                  url: res.m3u8Url,
                  title: item.title,
                  chapter_title: chapterTitle,
                  index: item.index,
                  total: totalMovies,
                  quality: settings.quality || "best",
                  download_folder: settings.downloadFolder || "",
                  slide_images: formattedSlides
                };
                try {
                  await fetch(LOCAL_SERVER, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
                } catch (e) {
                  alert("ZEN Downloader サーバーが起動していません。ZEN_Downloader.exe を起動してください。");
                }
                resDone();
              });
            });
          }
        }
      }
    }

    btn.style.opacity = "1";
    btn.innerHTML = `<span style="font-size:16px;">🎉</span><span>全${totalChapters}章 (動画＋画像) 送信完了！</span>`;
    chrome.storage.local.set({ batchInProgress: false });
    setTimeout(() => { isProcessing = false; renderButtons(); }, 8000);
  }

  // -----------------------------------------------------------
  // モード3: 単一章の動画を一括ダウンロード
  // -----------------------------------------------------------
  async function runSingleChapterBatch(courseId, chapterId, btn) {
    chrome.storage.local.set({ batchInProgress: true });
    btn.innerHTML = `<span>⏳</span><span>この章の解析中...</span>`;

    await initTabId();
    const csrfToken = await getCsrfToken();

    let chapterTitle = "", movies = [];
    try {
      const data = await fetchChapterDetails(courseId, chapterId, csrfToken);
      const rawTitle = data.chapterTitle || "";
      chapterTitle = formatChapterTitle(rawTitle, 1);
      movies = data.movies || [];
    } catch (e) {
      alert("章データの取得に失敗しました。");
      isProcessing = false;
      return;
    }

    if (movies.length === 0) {
      alert("動画が見つかりませんでした。");
      isProcessing = false;
      return;
    }

    const totalMovies = movies.length;
    for (let mIdx = 0; mIdx < totalMovies; mIdx++) {
      const item = movies[mIdx];
      btn.innerHTML = `<span>⏳</span><span>[${item.index}/${totalMovies}] 抽出中...</span>`;

      const res = await inspectMovieResources(item);
      const formattedSlides = (res.images || []).map((imgUrl, sIdx) => ({
        url: imgUrl,
        movie_index: item.index,
        movie_title: item.title,
        slide_index: sIdx + 1
      }));

      if (res.m3u8Url || formattedSlides.length > 0) {
        await new Promise((resDone) => {
          chrome.storage.local.get(["quality", "downloadFolder"], async (settings) => {
            const payload = {
              type: "video",
              url: res.m3u8Url,
              title: item.title,
              chapter_title: chapterTitle,
              index: item.index,
              total: totalMovies,
              quality: settings.quality || "best",
              download_folder: settings.downloadFolder || "",
              slide_images: formattedSlides
            };
            try {
              await fetch(LOCAL_SERVER, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
            } catch (e) {
              alert("ZEN Downloader サーバーが起動していません。ZEN_Downloader.exe を起動してください。");
            }
            resDone();
          });
        });
      }
    }

    btn.style.opacity = "1";
    btn.innerHTML = `<span style="font-size:16px;">🎉</span><span>全${totalMovies}本の送信完了！</span>`;
    chrome.storage.local.set({ batchInProgress: false });
    setTimeout(() => { isProcessing = false; renderButtons(); }, 6000);
  }

  function renderButtons() {
    const existing = document.getElementById("zen-downloader-tools-container");
    if (existing) existing.remove();

    const pageInfo = getPageInfo();
    if (!pageInfo) return;

    const container = document.createElement("div");
    container.id = "zen-downloader-tools-container";
    Object.assign(container.style, {
      position: "fixed", bottom: "24px", right: "24px", zIndex: "999999",
      display: "flex", flexDirection: "column", gap: "10px", alignItems: "flex-end"
    });

    if (pageInfo.type === "course") {
      const slidesBtn = document.createElement("button");
      slidesBtn.id = "zen-slides-only-btn";
      slidesBtn.innerHTML = `<span>🖼️</span><span>スライド画像だけ一括ダウンロード</span>`;
      styleButton(slidesBtn, "rgba(225, 29, 72, 0.92)", "#fecdd3", "rgba(244, 63, 94, 0.5)");
      slidesBtn.addEventListener("click", () => {
        if (isProcessing) return;
        isProcessing = true;
        runSlidesOnlyBatch(pageInfo.courseId, slidesBtn);
      });

      const bothBtn = document.createElement("button");
      bothBtn.id = "zen-both-btn";
      bothBtn.innerHTML = `<span>🔥</span><span>全15章（動画＋スライド）を一括ダウンロード</span>`;
      styleButton(bothBtn, "rgba(88, 28, 135, 0.92)", "#e9d5ff", "rgba(192, 132, 252, 0.5)");
      bothBtn.addEventListener("click", () => {
        if (isProcessing) return;
        isProcessing = true;
        runFullCourseBatch(pageInfo.courseId, bothBtn);
      });

      container.appendChild(slidesBtn);
      container.appendChild(bothBtn);
    } else {
      const chapterBtn = document.createElement("button");
      chapterBtn.id = "zen-chapter-btn";
      chapterBtn.innerHTML = `<span>📥</span><span>この章の動画を一括ダウンロード</span>`;
      styleButton(chapterBtn, "rgba(15, 23, 42, 0.92)", "#38bdf8", "rgba(56, 189, 248, 0.5)");
      chapterBtn.addEventListener("click", () => {
        if (isProcessing) return;
        isProcessing = true;
        runSingleChapterBatch(pageInfo.courseId, pageInfo.chapterId, chapterBtn);
      });

      container.appendChild(chapterBtn);
    }

    document.body.appendChild(container);
  }

  function styleButton(btn, bgColor, textColor, borderColor) {
    Object.assign(btn.style, {
      display: "flex", alignItems: "center", gap: "10px", padding: "12px 20px",
      backgroundColor: bgColor, color: textColor, border: `1px solid ${borderColor}`,
      borderRadius: "50px", boxShadow: "0 10px 25px -5px rgba(0,0,0,0.5)",
      backdropFilter: "blur(12px)", fontSize: "13px", fontWeight: "600",
      fontFamily: "Segoe UI, sans-serif", cursor: "pointer", transition: "all 0.3s cubic-bezier(0.4,0,0.2,1)"
    });
  }

  const observer = new MutationObserver(() => {
    if (!document.getElementById("zen-downloader-tools-container")) renderButtons();
  });
  if (document.body) {
    renderButtons();
    observer.observe(document.body, { childList: true, subtree: true });
  }
})();
