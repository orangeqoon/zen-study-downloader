# -*- coding: utf-8 -*-
# Force Python UTF-8 mode on Windows to prevent cp932 encoding crashes
import os
os.environ["PYTHONUTF8"] = "1"
import sys
import io
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import re
import json
import time
import subprocess
import threading
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 5000
SCRIPTS_DIR = r"C:\scripts"
CONFIG_PATH = os.path.join(SCRIPTS_DIR, "zen_downloader_config.json")
YTDLP_PATH = os.path.join(SCRIPTS_DIR, ".venv", "Scripts", "yt-dlp.exe")
COOKIES_PATH = os.path.join(SCRIPTS_DIR, "cookies_nico.txt")
LIVE_COOKIES_JSON = os.path.join(SCRIPTS_DIR, "live_session_cookies.json")
DEFAULT_DOWNLOADS_DIR = os.path.join(SCRIPTS_DIR, "youtube_downloads")

def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"quality": "best", "download_folder": DEFAULT_DOWNLOADS_DIR}

def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def clean_filename(text):
    if not text:
        return ""
    text = re.sub(r'[\\/*?:"<>|]', '_', text).strip()
    return text

def safe_print(msg):
    try:
        print(msg, flush=True)
    except Exception:
        try:
            print(msg.encode("utf-8", errors="replace").decode("ascii", errors="replace"), flush=True)
        except Exception:
            pass

def show_notification(title, message):
    try:
        safe_print(f"[Notification] {title}: {message}")
        safe_title = title.replace("'", "''").replace('"', '""')
        safe_message = message.replace("'", "''").replace('"', '""')
        ps_code = f"""
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        [void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms')
        $notify = New-Object System.Windows.Forms.NotifyIcon
        $notify.Icon = [System.Drawing.SystemIcons]::Information
        $notify.BalloonTipTitle = '{safe_title}'
        $notify.BalloonTipText = '{safe_message}'
        $notify.Visible = $true
        $notify.ShowBalloonTip(5000)
        Start-Sleep -Seconds 5
        $notify.Dispose()
        """
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_code],
            creationflags=subprocess.CREATE_NO_WINDOW
        )
    except Exception:
        pass

def download_images_list(images, target_dir, chapter_prefix=""):
    """Download a list of slide images into the chapter's slides directory"""
    if not images:
        return 0
    os.makedirs(target_dir, exist_ok=True)
    downloaded = 0
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.nnn.ed.nico/"
    }

    for idx, item in enumerate(images, 1):
        try:
            img_url = ""
            ext = ".png"
            filename = f"{idx:03d}_slide.png"

            if isinstance(item, str):
                img_url = item
                if ".jpg" in img_url or ".jpeg" in img_url:
                    ext = ".jpg"
                filename = f"{idx:03d}_slide{ext}"
            elif isinstance(item, dict):
                img_url = item.get("url", "")
                if ".jpg" in img_url or ".jpeg" in img_url:
                    ext = ".jpg"

                movie_idx = item.get("movie_index")
                movie_title = clean_filename(item.get("movie_title", ""))
                slide_idx = item.get("slide_index", idx)

                if movie_idx is not None and movie_title:
                    filename = f"{movie_idx:02d}_{movie_title}_slide_{slide_idx:02d}{ext}"
                elif movie_idx is not None:
                    filename = f"{movie_idx:02d}_slide_{slide_idx:02d}{ext}"
                elif item.get("filename"):
                    filename = item.get("filename")
                else:
                    filename = f"{idx:03d}_slide{ext}"

            if not img_url:
                continue

            save_path = os.path.join(target_dir, filename)
            if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
                downloaded += 1
                continue

            res = requests.get(img_url, headers=headers, timeout=20)
            if res.ok and len(res.content) > 0:
                with open(save_path, "wb") as f:
                    f.write(res.content)
                downloaded += 1
                safe_print(f"Downloaded slide: {save_path} ({len(res.content) / 1024:.1f} KB)")
        except Exception as e:
            safe_print(f"Error downloading slide image {idx}: {e}")

    return downloaded

def run_download(data):
    try:
        cfg = load_config()

        req_type = data.get("type", "video")
        course_title = data.get("course_title", "")
        chapter_title = data.get("chapter_title", "")
        download_folder = data.get("download_folder") or cfg.get("download_folder") or DEFAULT_DOWNLOADS_DIR

        # Update persistent settings
        updated = False
        if data.get("quality") and data.get("quality") != cfg.get("quality"):
            cfg["quality"] = data.get("quality")
            updated = True
        if data.get("download_folder") and data.get("download_folder") != cfg.get("download_folder"):
            cfg["download_folder"] = data.get("download_folder")
            updated = True
        if updated:
            save_config(cfg)

        base_dir = download_folder
        if course_title:
            clean_cname = clean_filename(course_title)
            # If download_folder already ends with course name, don't duplicate
            if os.path.basename(os.path.normpath(base_dir)).lower() != clean_cname.lower():
                base_dir = os.path.join(base_dir, clean_cname)

        os.makedirs(base_dir, exist_ok=True)

        if chapter_title:
            chapter_subfolder = clean_filename(chapter_title)
            target_chapter_dir = os.path.join(base_dir, chapter_subfolder)
        else:
            target_chapter_dir = base_dir

        os.makedirs(target_chapter_dir, exist_ok=True)

        # ----------------------------------------------------
        # CASE 1: Slides-only Batch Download
        # ----------------------------------------------------
        if req_type == "slides_only" or data.get("images"):
            images = data.get("images", [])
            slides_dir = os.path.join(target_chapter_dir, "slides")
            show_notification("ZEN Slide Downloader", f"{chapter_title} のスライド保存中 ({len(images)}枚)")
            count = download_images_list(images, slides_dir)
            show_notification("ZEN Slide Downloader", f"完了: {chapter_title} ({count}枚保存)")
            safe_print(f"Slides batch complete for '{chapter_title}': {count}/{len(images)} saved in {slides_dir}")
            return

        # ----------------------------------------------------
        # CASE 2: Exercise Screenshots Batch Download
        # ----------------------------------------------------
        if req_type == "exercises_batch" or data.get("exercise_images"):
            exercises_dir = os.path.join(target_chapter_dir, "exercises")
            os.makedirs(exercises_dir, exist_ok=True)
            exercise_images = data.get("exercise_images", [])
            saved_count = 0
            import base64
            for item in exercise_images:
                try:
                    filename = clean_filename(item.get("filename", "exercise.png"))
                    if not filename.endswith(".png") and not filename.endswith(".jpg"):
                        filename += ".png"
                    save_path = os.path.join(exercises_dir, filename)
                    b64_data = item.get("image_base64", "")
                    if "," in b64_data:
                        b64_data = b64_data.split(",", 1)[1]
                    img_bytes = base64.b64decode(b64_data)
                    with open(save_path, "wb") as f:
                        f.write(img_bytes)
                    saved_count += 1
                    safe_print(f"Saved exercise screenshot: {save_path} ({len(img_bytes)/1024:.1f} KB)")
                except Exception as e:
                    safe_print(f"Error saving exercise image: {e}")

            show_notification("ZEN Exercise Downloader", f"完了: {chapter_title} (確認テスト {saved_count}枚保存)")
            safe_print(f"Exercises batch complete for '{chapter_title}': {saved_count}/{len(exercise_images)} saved in {exercises_dir}")
            return

        # ----------------------------------------------------
        # CASE 3: Video Download
        # ----------------------------------------------------
        video_url = data.get("url")
        if not video_url:
            return

        title = data.get("title", "")
        index = data.get("index")
        total = data.get("total")
        quality = data.get("quality") or cfg.get("quality") or "best"

        prefix = ""
        if index is not None and total is not None:
            prefix = f"[{index}/{total}] "
        display_name = title if title else "動画"

        # Refresh cookies for yt-dlp
        cookie_script = os.path.join(SCRIPTS_DIR, "extract_nico_cookies.py")
        try:
            subprocess.run(["python", cookie_script], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception:
            pass

        if not os.path.exists(COOKIES_PATH):
            show_notification("ZEN Downloader", "エラー: クッキーファイルなし")
            return

        if title and index is not None:
            output_template = os.path.join(target_chapter_dir, f"{index:02d}_{clean_filename(title)}.%(ext)s")
        elif title:
            output_template = os.path.join(target_chapter_dir, f"{clean_filename(title)}.%(ext)s")
        else:
            output_template = os.path.join(target_chapter_dir, "%(title)s.%(ext)s")

        show_notification("ZEN Downloader", f"{prefix}{display_name} [{quality}]")

        format_str = "best" if quality == "best" else f"best[height<={quality}]/best"
        cmd = [YTDLP_PATH, "--cookies", COOKIES_PATH, "-f", format_str, "-o", output_template, video_url]
        safe_print(f"yt-dlp: {output_template}")

        result = subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

        if result.returncode == 0:
            show_notification("ZEN Downloader", f"{prefix}完了: {display_name}")
            safe_print(f"OK: {display_name}")
        else:
            stderr_text = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
            show_notification("ZEN Downloader", f"{prefix}エラー: {display_name}")
            safe_print(f"FAIL: {display_name}\n{stderr_text}")

        # If slide images were also attached
        slide_images = data.get("slide_images", [])
        if slide_images:
            slides_dir = os.path.join(target_chapter_dir, "slides")
            download_images_list(slide_images, slides_dir)

    except Exception as e:
        try:
            show_notification("ZEN Downloader", f"エラー: {str(e)[:50]}")
            safe_print(f"Error in downloader thread: {e}")
        except Exception:
            pass

def run_playwright_batch_scraper(course_id, download_folder=None):
    """Playwrightを使って全章の確認テストを自動巡回＆高画質スクショ保存"""
    from playwright.sync_api import sync_playwright

    cfg = load_config()
    target_base = download_folder or cfg.get("download_folder") or DEFAULT_DOWNLOADS_DIR

    # Load session cookies
    cookies_for_pw = []
    if os.path.exists(LIVE_COOKIES_JSON):
        try:
            with open(LIVE_COOKIES_JSON, "r", encoding="utf-8") as f:
                cdata = json.load(f)
                cookie_str = cdata.get("cookie_header", "")
                # Parse key=value; pairs
                for part in cookie_str.split(";"):
                    part = part.strip()
                    if "=" in part:
                        k, v = part.split("=", 1)
                        cookies_for_pw.append({
                            "name": k.strip(),
                            "value": v.strip(),
                            "domain": "www.nnn.ed.nico",
                            "path": "/"
                        })
        except Exception as e:
            safe_print(f"Error reading live cookies: {e}")

    safe_print(f"Starting Playwright Batch Scraper for Course {course_id}...")
    show_notification("ZEN Scraper", f"コース {course_id} の確認テスト自動収集を開始します")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            device_scale_factor=2
        )
        if cookies_for_pw:
            context.add_cookies(cookies_for_pw)

        page = context.new_page()

        # 1. Fetch course details to get all chapters
        course_url = f"https://www.nnn.ed.nico/courses/{course_id}"
        page.goto(course_url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        # Get chapters from page
        links = page.eval_on_selector_all('a[href*="/chapters/"]', 'els => els.map(e => ({ href: e.href, text: e.innerText.trim() }))')
        chapter_dict = {}
        for l in links:
            m = re.search(r'/courses/(\d+)/chapters/(\d+)', l['href'])
            if m:
                chap_id = m.group(2)
                if chap_id not in chapter_dict:
                    chapter_dict[chap_id] = l['text'] or f"第{len(chapter_dict)+1}章"

        safe_print(f"Found {len(chapter_dict)} chapters.")

        for idx, (chap_id, chap_title) in enumerate(chapter_dict.items(), 1):
            clean_chap = re.sub(r'^(?:第?\s*\d+\s*[章回\.\:\-]?\s*)+', '', chap_title).strip()
            chap_folder_name = f"{idx:02d}. {clean_chap}"
            chap_dir = os.path.join(target_base, chap_folder_name, "exercises")
            os.makedirs(chap_dir, exist_ok=True)

            chap_url = f"https://www.nnn.ed.nico/courses/{course_id}/chapters/{chap_id}"
            page.goto(chap_url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1500)

            # Find all exercise links in this chapter
            ex_links = page.eval_on_selector_all('a[href*="/exercise/"]', 'els => els.map(e => ({ href: e.href, text: e.innerText.trim() }))')
            safe_print(f"[{idx}/{len(chapter_dict)}] Chapter '{chap_folder_name}': {len(ex_links)} exercises found.")

            for ex_idx, ex in enumerate(ex_links, 1):
                try:
                    page.goto(ex['href'], wait_until="networkidle", timeout=30000)
                    page.wait_for_timeout(2500)

                    # Look for question blocks
                    # Evaluate script to find question cards and take screenshots
                    cards = page.query_selector_all('section, article, div')
                    # Filter elements containing choices and explanation
                    target_cards = []
                    for card in cards:
                        try:
                            txt = card.inner_text()
                            if ("【選択肢】" in txt or "選択肢" in txt) and ("解答：" in txt or "解答" in txt or "解説" in txt):
                                bbox = card.bounding_box()
                                if bbox and bbox['height'] > 120 and bbox['width'] > 350:
                                    target_cards.append(card)
                        except Exception:
                            pass

                    # Filter out parents
                    leaf_cards = []
                    for c in target_cards:
                        # If c contains another card, skip
                        is_parent = False
                        for other in target_cards:
                            if other != c:
                                try:
                                    if c.evaluate('(parent, child) => parent.contains(child)', other):
                                        is_parent = True
                                        break
                                except Exception:
                                    pass
                        if not is_parent:
                            leaf_cards.append(c)

                    if leaf_cards:
                        for q_i, card in enumerate(leaf_cards, 1):
                            q_filename = f"{ex_idx:02d}_{clean_filename(ex['text'])}_問{q_i:02d}.png"
                            save_path = os.path.join(chap_dir, q_filename)
                            card.screenshot(path=save_path)
                            safe_print(f"  Saved question screenshot: {save_path}")
                    else:
                        # Fallback full page
                        q_filename = f"{ex_idx:02d}_{clean_filename(ex['text'])}_全問.png"
                        save_path = os.path.join(chap_dir, q_filename)
                        page.screenshot(path=save_path, full_page=True)
                        safe_print(f"  Saved fallback screenshot: {save_path}")

                except Exception as e:
                    safe_print(f"Error capturing exercise {ex['href']}: {e}")

        browser.close()
        show_notification("ZEN Scraper", f"全{len(chapter_dict)}章の確認テスト画像保存が完了しました！")
        safe_print("Playwright batch scraper complete!")

class DownloaderRequestHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        if self.path == "/status":
            self._json_response(200, {"status": "online"})
        elif self.path == "/settings":
            self._json_response(200, load_config())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/settings":
            try:
                data = self._read_json()
                cfg = load_config()
                if data.get("quality"):
                    cfg["quality"] = data["quality"]
                if data.get("download_folder"):
                    cfg["download_folder"] = data["download_folder"]
                save_config(cfg)
                self._json_response(200, {"status": "saved", "config": cfg})
            except Exception as e:
                self._json_response(500, {"error": str(e)})

        elif self.path == "/sync_cookies":
            try:
                data = self._read_json()
                with open(LIVE_COOKIES_JSON, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                safe_print(f"Synchronized live cookies from browser ({len(data.get('cookie_header', ''))} bytes)")
                self._json_response(200, {"status": "synced"})
            except Exception as e:
                self._json_response(500, {"error": str(e)})

        elif self.path == "/run_exercises_scraper":
            try:
                data = self._read_json()
                course_id = data.get("course_id")
                course_title = data.get("course_title", "")
                cfg = load_config()
                download_folder = cfg.get("download_folder") or DEFAULT_DOWNLOADS_DIR
                if course_title and os.path.basename(os.path.normpath(download_folder)).lower() != clean_filename(course_title).lower():
                    target_output = os.path.join(download_folder, clean_filename(course_title))
                else:
                    target_output = download_folder

                def _run_bg():
                    try:
                        import download_course_exercises
                        download_course_exercises.run(course_id, target_output)
                    except Exception as e:
                        safe_print(f"Scraper error: {e}")

                threading.Thread(target=_run_bg, daemon=True).start()
                self._json_response(200, {"status": "scraper_started"})
            except Exception as e:
                self._json_response(500, {"error": str(e)})

        elif self.path == "/download":
            try:
                data = self._read_json()
                threading.Thread(target=run_download, args=(data,), daemon=True).start()
                self._json_response(200, {"status": "started"})
            except Exception as e:
                self._json_response(500, {"error": str(e)})
        else:
            self.send_response(404)
            self.end_headers()

    def _read_json(self):
        length = int(self.headers['Content-Length'])
        return json.loads(self.rfile.read(length).decode('utf-8'))

    def _json_response(self, code, obj):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode('utf-8'))

    def log_message(self, format, *args):
        safe_print(f"[Server] {args[0]} {args[1]} {args[2]}" if len(args) >= 3 else f"[Server] {format % args}")

def main():
    safe_print(f"ZEN Study Downloader Server starting on port {PORT}...")
    httpd = HTTPServer(('', PORT), DownloaderRequestHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        safe_print("Server stopped.")
        httpd.server_close()

if __name__ == "__main__":
    main()
