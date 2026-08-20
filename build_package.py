# -*- coding: utf-8 -*-
import os
import shutil
import subprocess
import zipfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.join(BASE_DIR, "server")
EXTENSION_DIR = os.path.join(BASE_DIR, "chrome_extension")
WORK_DIR = os.path.join(BASE_DIR, "build_temp")
DIST_TEMP = os.path.join(BASE_DIR, "dist_temp")
DIST_DIR = os.path.join(BASE_DIR, "dist")
PACKAGE_DIR = os.path.join(BASE_DIR, "ZEN_Study_Downloader_v1.0")

def build():
    print("=== Building ZEN Study Downloader Package ===")

    # Clean old build
    for p in [PACKAGE_DIR, WORK_DIR, DIST_TEMP]:
        if os.path.exists(p):
            shutil.rmtree(p)
    os.makedirs(PACKAGE_DIR, exist_ok=True)
    os.makedirs(DIST_DIR, exist_ok=True)

    # 1. Build ZEN_Downloader.exe with PyInstaller
    server_script = os.path.join(SERVER_DIR, "zen_server.py")
    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--onefile",
        "--name=ZEN_Downloader",
        f"--workpath={WORK_DIR}",
        f"--distpath={DIST_TEMP}",
        "--clean",
        server_script
    ]
    print("Running PyInstaller...")
    res = subprocess.run(cmd, cwd=BASE_DIR)
    if res.returncode != 0:
        print("PyInstaller build failed!")
        return False

    # 2. Copy the standalone ZEN_Downloader.exe
    built_exe = os.path.join(DIST_TEMP, "ZEN_Downloader.exe")
    if not os.path.exists(built_exe):
        print(f"Error: {built_exe} not found!")
        return False
    shutil.copy2(built_exe, os.path.join(PACKAGE_DIR, "ZEN_Downloader.exe"))
    print("Copied ZEN_Downloader.exe")

    # 3. Copy yt-dlp.exe
    src_ytdlp = r"C:\scripts\.venv\Scripts\yt-dlp.exe"
    if os.path.exists(src_ytdlp):
        shutil.copy2(src_ytdlp, os.path.join(PACKAGE_DIR, "yt-dlp.exe"))
        print("Copied yt-dlp.exe")

    # 4. Copy chrome_extension
    dst_ext = os.path.join(PACKAGE_DIR, "chrome_extension")
    shutil.copytree(EXTENSION_DIR, dst_ext)
    print("Copied chrome_extension")

    # 5. Create Easy Quickstart HTML Guide
    guide_html = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>ZEN Study Downloader かんたん導入ガイド</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 700px; margin: 40px auto; padding: 20px; line-height: 1.6; background: #0f172a; color: #f8fafc; }
  h1 { color: #38bdf8; border-bottom: 2px solid #334155; padding-bottom: 10px; }
  h2 { color: #34d399; margin-top: 30px; }
  .step { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 16px 20px; margin-bottom: 16px; }
  .step-num { display: inline-block; background: #0284c7; color: white; border-radius: 50%; width: 24px; height: 24px; text-align: center; font-weight: bold; line-height: 24px; margin-right: 8px; }
  code { background: #334155; padding: 2px 6px; border-radius: 4px; color: #f43f5e; font-family: Consolas, monospace; }
  .btn-sample { display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: bold; }
  .btn-both { background: #581c87; color: #e9d5ff; }
  .btn-slides { background: #e11d48; color: #fecdd3; }
</style>
</head>
<body>
  <h1>ZEN Study Downloader かんたん導入ガイド</h1>
  <p>わずか2ステップでZEN大学の講義動画とスライド画像を1クリック保存できるようになります！</p>

  <div class="step">
    <h2><span class="step-num">1</span> アプリ（サーバー）の起動</h2>
    <p>このフォルダ内にある <code>ZEN_Downloader.exe</code> をダブルクリックして起動します。<br>
    黒い画面に <code>Server is running.</code> と表示されれば準備完了です！（起動中は画面を閉じないでください）</p>
  </div>

  <div class="step">
    <h2><span class="step-num">2</span> Chrome拡張機能の読み込み</h2>
    <ol>
      <li>Google Chrome を開き、URLバーに <code>chrome://extensions</code> と入力して開きます。</li>
      <li>画面右上の <strong>「デベロッパー モード」</strong> をONにします。</li>
      <li>左上の <strong>「パッケージ化されていない拡張機能を読み込む」</strong> を押し、このフォルダ内の <code>chrome_extension</code> フォルダを選択します。</li>
    </ol>
  </div>

  <div class="step">
    <h2><span class="step-num">3</span> 使い方</h2>
    <p>ZEN Studyで講義ページ（コース一覧）を開くと、画面右下に専用ボタンが出現します！</p>
    <ul>
      <li><span class="btn-sample btn-both">🔥 全15章（動画＋スライド）を一括ダウンロード</span>：全動画と全スライドを一度に保存</li>
      <li><span class="btn-sample btn-slides">🖼️ スライド画像だけ一括ダウンロード</span>：スライド画像のみを高速保存</li>
    </ul>
    <p>保存先は標準で <code>ダウンロード/ZEN_Study/</code> フォルダ内に章ごとに自動整理されます。</p>
  </div>
</body>
</html>
"""
    with open(os.path.join(PACKAGE_DIR, "かんたん導入ガイド.html"), "w", encoding="utf-8") as f:
        f.write(guide_html)

    # 6. Compress into ZIP
    zip_path = os.path.join(DIST_DIR, "ZEN_Study_Downloader_v1.0.zip")
    print(f"Compressing into {zip_path}...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(PACKAGE_DIR):
            for file in files:
                abs_f = os.path.join(root, file)
                rel_f = os.path.relpath(abs_f, os.path.dirname(PACKAGE_DIR))
                zf.write(abs_f, rel_f)

    # Clean temporary directories
    for p in [WORK_DIR, DIST_TEMP]:
        if os.path.exists(p):
            shutil.rmtree(p)
    spec_file = os.path.join(BASE_DIR, "ZEN_Downloader.spec")
    if os.path.exists(spec_file):
        os.remove(spec_file)

    print(f"\n==========================================")
    print(f" BUILD SUCCESSFUL!")
    print(f" Portable ZIP created at: {zip_path}")
    print(f" Size: {os.path.getsize(zip_path) / (1024*1024):.2f} MB")
    print(f"==========================================")
    return True

if __name__ == "__main__":
    build()
