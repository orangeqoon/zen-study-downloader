# -*- coding: utf-8 -*-
import os
os.environ["PYTHONUTF8"] = "1"
import sys
import io
import re
import json
import shutil
import subprocess
import threading
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Base directory determination (compatible with PyInstaller bundle)
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

PORT = 5000
CONFIG_PATH = os.path.join(APP_DIR, "zen_downloader_config.json")
COOKIES_PATH = os.path.join(APP_DIR, "cookies_nico.txt")

# Default downloads folder is in user's Downloads/ZEN_Study
USER_DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads", "ZEN_Study")
DEFAULT_DOWNLOADS_DIR = USER_DOWNLOADS

# Find yt-dlp binary
def get_ytdlp_path():
    local_ytdlp = os.path.join(APP_DIR, "yt-dlp.exe")
    if os.path.exists(local_ytdlp):
        return local_ytdlp
    system_ytdlp = shutil.which("yt-dlp")
    if system_ytdlp:
        return system_ytdlp
    return "yt-dlp"

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
        pass

def show_notification(title, message):
    try:
        safe_print(f"[Notification] {title}: {message}")
        if sys.platform == "win32":
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
            $notify.ShowBalloonTip(4000)
            Start-Sleep -Seconds 4
            $notify.Dispose()
            """
            subprocess.Popen(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_code],
                creationflags=subprocess.CREATE_NO_WINDOW
            )
    except Exception:
        pass

def download_images_list(images, target_dir):
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
        chapter_title = data.get("chapter_title", "")
        download_folder = data.get("download_folder") or cfg.get("download_folder") or DEFAULT_DOWNLOADS_DIR

        # Update config if changed
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
        os.makedirs(base_dir, exist_ok=True)

        if chapter_title:
            chapter_subfolder = clean_filename(chapter_title)
            target_chapter_dir = os.path.join(base_dir, chapter_subfolder)
        else:
            target_chapter_dir = base_dir

        os.makedirs(target_chapter_dir, exist_ok=True)

        # CASE 1: Slides only
        if req_type == "slides_only" or data.get("images"):
            images = data.get("images", [])
            slides_dir = os.path.join(target_chapter_dir, "slides")
            show_notification("ZEN Slide Downloader", f"{chapter_title} のスライド保存中 ({len(images)}枚)")
            count = download_images_list(images, slides_dir)
            show_notification("ZEN Slide Downloader", f"完了: {chapter_title} ({count}枚保存)")
            safe_print(f"Slides batch complete for '{chapter_title}': {count}/{len(images)} saved in {slides_dir}")
            return

        # CASE 2: Exercise Screenshots Batch
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

        # CASE 3: Video Download
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

        # Refresh cookies
        try:
            from extract_cookies import extract_cookies_to_file
            extract_cookies_to_file(COOKIES_PATH)
        except Exception:
            pass

        ytdlp_bin = get_ytdlp_path()

        if title and index is not None:
            output_template = os.path.join(target_chapter_dir, f"{index:02d}_{clean_filename(title)}.%(ext)s")
        elif title:
            output_template = os.path.join(target_chapter_dir, f"{clean_filename(title)}.%(ext)s")
        else:
            output_template = os.path.join(target_chapter_dir, "%(title)s.%(ext)s")

        show_notification("ZEN Downloader", f"{prefix}{display_name} [{quality}]")

        format_str = "best" if quality == "best" else f"best[height<={quality}]/best"
        cmd = [ytdlp_bin]
        if os.path.exists(COOKIES_PATH):
            cmd.extend(["--cookies", COOKIES_PATH])
        cmd.extend(["-f", format_str, "-o", output_template, video_url])

        safe_print(f"yt-dlp: {output_template}")

        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        result = subprocess.run(cmd, capture_output=True, creationflags=flags)

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
            self._json_response(200, {"status": "online", "version": "1.0.0"})
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
    safe_print(f"=================================================")
    safe_print(f" ZEN Study Downloader Server (v1.0.0)")
    safe_print(f" Port: {PORT}")
    safe_print(f" Save Directory: {DEFAULT_DOWNLOADS_DIR}")
    safe_print(f"=================================================")
    safe_print("Server is running. You can now use the Chrome extension.")
    safe_print("Press Ctrl+C to stop the server.")

    httpd = HTTPServer(('', PORT), DownloaderRequestHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        safe_print("\nServer stopped.")
        httpd.server_close()

if __name__ == "__main__":
    main()
