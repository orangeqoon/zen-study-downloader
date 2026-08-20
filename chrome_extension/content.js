// ZEN Study Downloader + Slide Images & Exercises Content Script v7.5
// 動画・スライド・確認テスト（解答解説付き）の完全全自動保存
(function () {
  'use strict';
  console.log("[ZEN Downloader + Images & Exercises v7.5] Content script initialized.");

  const LOCAL_SERVER = "http://localhost:5000";
  let isProcessing = false;
  let myTabId = -1;

  function clean_filename(text) {
    if (!text) return "";
    return text.replace(/[\\/*?:"<>|]/g, '_').trim();
  }

  // 章タイトルの整形
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

  // サーバーへCookieとセッションを同期
  async function syncSessionToLocalServer() {
    try {
      const csrf = await getCsrfToken();
      await fetch(`${LOCAL_SERVER}/sync_cookies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: location.href,
          cookie_header: document.cookie,
          csrf_token: csrf
        })
      });
    } catch (e) {}
  }
  syncSessionToLocalServer();

  function getPageInfo() {
    const pathname = location.pathname;
    const exerciseMatch = pathname.match(/\/courses\/(\d+)\/chapters\/(\d+)\/exercise\/(\d+)/);
    if (exerciseMatch) return { type: "exercise", courseId: exerciseMatch[1], chapterId: exerciseMatch[2], exerciseId: exerciseMatch[3] };

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

    const movies = sections.filter((s) => s.resource_type === "movie").map((s, idx) => ({
      index: idx + 1,
      title: s.title,
      contentUrl: s.content_url,
      movieId: s.id
    }));

    const exercises = sections.filter((s) => s.resource_type === "exercise" || s.resource_type === "eval_test" || s.resource_type === "test").map((s, idx) => ({
      index: idx + 1,
      title: s.title || "確認テスト",
      contentUrl: s.content_url,
      exerciseId: s.id
    }));

    return { chapterTitle, movies, exercises };
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

  // 動画リソースとスライド画像の同期抽出
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

        if (captured.m3u8 && ((slideCount > 0 && stableDuration >= 1200) || elapsed >= 4500)) {
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

  // [問題文 + 選択肢 + 解答解説] をすべて含む完全な問題カード要素を探索
  function findQuestionCards(doc) {
    const allElements = Array.from(doc.querySelectorAll('section, article, div, li'));

    // 1. 「選択肢」と「解答」の双方を内包しているコンテナ
    const candidates = allElements.filter((el) => {
      const text = el.innerText || "";
      return (text.includes("【選択肢】") || text.includes("選択肢")) && (text.includes("解答：") || text.includes("解答") || text.includes("解説"));
    });

    if (candidates.length > 0) {
      const leafCards = candidates.filter((card) => {
        return !candidates.some((other) => other !== card && card.contains(other));
      });
      if (leafCards.length > 0) return leafCards;
    }

    // 2. ラジオボタン等と解答解説を含むブロック
    const radioCandidates = allElements.filter((el) => {
      const text = el.innerText || "";
      const hasRadio = el.querySelector('input[type="radio"], input[type="checkbox"], svg');
      return hasRadio && (text.includes("解答：") || text.includes("解答") || text.includes("解説"));
    });

    if (radioCandidates.length > 0) {
      const leafRadio = radioCandidates.filter((card) => {
        return !radioCandidates.some((other) => other !== card && card.contains(other));
      });
      if (leafRadio.length > 0) return leafRadio;
    }

    // 3. フォールバック
    const mainEl = doc.querySelector('main') || doc.querySelector('article') || doc.querySelector('#root') || doc.body;
    return [mainEl];
  }

  // Chromeネイティブ画面キャプチャによる切り抜き
  async function captureElementViaNativeScreenshot(element) {
    if (!element) return null;

    element.scrollIntoView({ behavior: "instant", block: "center" });
    await new Promise((r) => setTimeout(r, 450));

    const rect = element.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;

    const res = await new Promise((resolve) => {
      chrome.runtime.sendMessage({ action: "CAPTURE_TAB_SCREENSHOT" }, resolve);
    });

    if (!res || !res.dataUrl) {
      console.error("[ZEN Downloader] Failed to capture tab screenshot.");
      return null;
    }

    const img = new Image();
    await new Promise((resolve, reject) => {
      img.onload = resolve;
      img.onerror = reject;
      img.src = res.dataUrl;
    });

    const pad = 12 * dpr;
    const cropX = Math.max(0, Math.round(rect.left * dpr - pad));
    const cropY = Math.max(0, Math.round(rect.top * dpr - pad));
    const cropW = Math.min(img.width - cropX, Math.round(rect.width * dpr + pad * 2));
    const cropH = Math.min(img.height - cropY, Math.round(rect.height * dpr + pad * 2));

    const canvas = document.createElement("canvas");
    canvas.width = cropW;
    canvas.height = cropH;
    const ctx = canvas.getContext("2d");

    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, cropW, cropH);
    ctx.drawImage(img, cropX, cropY, cropW, cropH, 0, 0, cropW, cropH);

    return canvas.toDataURL("image/png");
  }

  // 単一の確認テストページで即座に保存
  async function runSingleExerciseSave(btn) {
    btn.innerHTML = `<span>⏳</span><span>スクショ撮影中...</span>`;
    await syncSessionToLocalServer();
    const questionCards = findQuestionCards(document);

    if (questionCards.length > 0) {
      try {
        const pageInfo = getPageInfo();
        const capturedList = [];

        for (let qIdx = 0; qIdx < questionCards.length; qIdx++) {
          const card = questionCards[qIdx];
          const dataUrl = await captureElementViaNativeScreenshot(card);
          if (dataUrl) {
            const qNum = String(qIdx + 1).padStart(2, '0');
            capturedList.push({
              filename: `確認テスト_${pageInfo.exerciseId}_問${qNum}.png`,
              image_base64: dataUrl
            });
          }
        }

        if (capturedList.length === 0) {
          alert("スクショの取得に失敗しました。ZEN_Downloader.exe が起動しているかご確認ください。");
          renderButtons();
          return;
        }

        const csrfToken = await getCsrfToken();
        let chapterTitle = "確認テスト";
        try {
          const data = await fetchChapterDetails(pageInfo.courseId, pageInfo.chapterId, csrfToken);
          chapterTitle = formatChapterTitle(data.chapterTitle, 1);
        } catch (e) {}

        const payload = {
          type: "exercises_batch",
          chapter_title: chapterTitle,
          exercise_images: capturedList,
          download_folder: ""
        };
        await fetch(`${LOCAL_SERVER}/download`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        btn.innerHTML = `<span>🎉</span><span>確認テスト（全${capturedList.length}問）を画像保存しました！</span>`;
        setTimeout(() => { renderButtons(); }, 4000);
      } catch (e) {
        console.error("Single exercise save error:", e);
        alert("キャプチャに失敗しました。");
        renderButtons();
      }
    }
  }

  // -----------------------------------------------------------
  // モード1: 確認テストだけを一括画像保存（全15章 自動ブラウザ操作）
  // -----------------------------------------------------------
  async function runExercisesOnlyBatch(courseId, btn) {
    await syncSessionToLocalServer();
    btn.innerHTML = `<span>🚀</span><span>全自動ブラウザ操作中...</span>`;
    try {
      const res = await fetch(`${LOCAL_SERVER}/run_exercises_scraper`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ course_id: courseId })
      });
      if (res.ok) {
        btn.innerHTML = `<span>🎉</span><span>確認テストの自動収集を開始しました！（画面通知が出ます）</span>`;
        setTimeout(() => { renderButtons(); }, 5000);
      } else {
        alert("サーバーエラーが発生しました。");
        renderButtons();
      }
    } catch (e) {
      alert("ZEN Downloader サーバーが起動していません。ZEN_Downloader.exe を起動してください。");
      renderButtons();
    }
  }

  // -----------------------------------------------------------
  // モード2: スライド画像だけを一括ダウンロード（全15章）
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
              await fetch(`${LOCAL_SERVER}/download`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
            } catch (e) {}
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
  // モード3: 全コース（動画 ＋ スライド）を完全一括保存
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
          btn.innerHTML = `<span>⏳</span><span>[章 ${chapNum}/${totalChapters}] [動画 ${item.index}/${totalMovies}] 処理中...</span>`;

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
                  await fetch(`${LOCAL_SERVER}/download`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
                } catch (e) {}
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

  function renderButtons() {
    const existing = document.getElementById("zen-image-tools-container");
    if (existing) existing.remove();

    const pageInfo = getPageInfo();
    if (!pageInfo) return;

    const container = document.createElement("div");
    container.id = "zen-image-tools-container";
    Object.assign(container.style, {
      position: "fixed", bottom: "24px", right: "24px", zIndex: "999999",
      display: "flex", flexDirection: "column", gap: "10px", alignItems: "flex-end"
    });

    if (pageInfo.type === "course") {
      // 1. 全15章（動画＋スライド）を一括保存
      const allInOneBtn = document.createElement("button");
      allInOneBtn.id = "zen-all-in-one-btn";
      allInOneBtn.innerHTML = `<span>⚡</span><span>全15章（動画＋スライド）を一括保存</span>`;
      styleButton(allInOneBtn, "rgba(88, 28, 135, 0.95)", "#e9d5ff", "rgba(192, 132, 252, 0.6)");
      allInOneBtn.addEventListener("click", () => {
        if (isProcessing) return;
        isProcessing = true;
        runFullCourseBatch(pageInfo.courseId, allInOneBtn);
      });

      // 2. 確認テストだけ一括画像保存（Playwright全自動ブラウザ操作）
      const testsBtn = document.createElement("button");
      testsBtn.id = "zen-tests-only-btn";
      testsBtn.innerHTML = `<span>📝</span><span>全15章の確認テストを一括画像保存（全自動）</span>`;
      styleButton(testsBtn, "rgba(13, 148, 136, 0.95)", "#ccfbf1", "rgba(45, 212, 191, 0.6)");
      testsBtn.addEventListener("click", () => {
        runExercisesOnlyBatch(pageInfo.courseId, testsBtn);
      });

      // 3. スライド画像だけ一括ダウンロード
      const slidesBtn = document.createElement("button");
      slidesBtn.id = "zen-slides-only-btn";
      slidesBtn.innerHTML = `<span>🖼️</span><span>スライド画像だけ一括ダウンロード</span>`;
      styleButton(slidesBtn, "rgba(225, 29, 72, 0.92)", "#fecdd3", "rgba(244, 63, 94, 0.5)");
      slidesBtn.addEventListener("click", () => {
        if (isProcessing) return;
        isProcessing = true;
        runSlidesOnlyBatch(pageInfo.courseId, slidesBtn);
      });

      container.appendChild(allInOneBtn);
      container.appendChild(testsBtn);
      container.appendChild(slidesBtn);
    } else if (pageInfo.type === "exercise") {
      const singleExBtn = document.createElement("button");
      singleExBtn.id = "zen-single-ex-btn";
      singleExBtn.innerHTML = `<span>📝</span><span>この確認テストを画像保存（解説付き）</span>`;
      styleButton(singleExBtn, "rgba(13, 148, 136, 0.95)", "#ccfbf1", "rgba(45, 212, 191, 0.6)");
      singleExBtn.addEventListener("click", () => {
        runSingleExerciseSave(singleExBtn);
      });
      container.appendChild(singleExBtn);
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
    if (!document.getElementById("zen-image-tools-container")) renderButtons();
  });
  if (document.body) {
    renderButtons();
    observer.observe(document.body, { childList: true, subtree: true });
  }
})();
