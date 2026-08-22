import os
import re
import sys
import time
import requests
import rookiepy
import tempfile
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

def get_firefox_cookies():
    domains = ['ed.nico', 'nicovideo.jp', 'dwango.jp', 'nnn.ed.nico']
    cookies_list = rookiepy.firefox(domains)
    jar = {}
    for c in cookies_list:
        jar[c['name']] = c['value']
    return jar

def clean_filename(s):
    if not s:
        return "untitled"
    s = s.replace('/', '_').replace('\\', '_').replace(':', '：')
    s = s.replace('*', '＊').replace('?', '？').replace('"', '”')
    s = s.replace('<', '＜').replace('>', '＞').replace('|', '｜')
    return s.strip()

def format_chapter_title(raw_title, index):
    cleaned = clean_filename(raw_title)
    if re.match(r'^\d+\.', cleaned):
        return cleaned
    return f"{index:02d}. {cleaned}"

def download_ts_segment(url, index, temp_dir, session, retries=3):
    dest = os.path.join(temp_dir, f"seg_{index:06d}.ts")
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=15)
            if r.ok and len(r.content) > 0:
                with open(dest, 'wb') as f:
                    f.write(r.content)
                return index, True
        except Exception:
            time.sleep(1)
    return index, False

def download_hls_fast(master_m3u8_url, output_path, max_workers=24):
    print(f"  [FAST-HLS] Resolving stream for {os.path.basename(output_path)}...")
    t0 = time.time()
    
    # 1. Resolve child m3u8 (highest bandwidth)
    session = requests.Session()
    r = session.get(master_m3u8_url, timeout=15)
    if not r.ok:
        print(f"  Failed master playlist: {r.status_code}")
        return False
        
    base_dir = master_m3u8_url.rsplit('/', 1)[0]
    lines = [l.strip() for l in r.text.splitlines() if l.strip()]
    
    streams = []
    for i, l in enumerate(lines):
        if l.startswith('#EXT-X-STREAM-INF'):
            bw = int(re.search(r'BANDWIDTH=(\d+)', l).group(1)) if re.search(r'BANDWIDTH=(\d+)', l) else 0
            if i + 1 < len(lines):
                uri = lines[i+1]
                streams.append((bw, uri if uri.startswith('http') else f"{base_dir}/{uri}"))
                
    if streams:
        streams.sort(key=lambda x: x[0], reverse=True)
        child_m3u8_url = streams[0][1]
    else:
        child_m3u8_url = master_m3u8_url
        
    # 2. Fetch child playlist and extract all TS segment URLs
    r_child = session.get(child_m3u8_url, timeout=15)
    if not r_child.ok:
        print(f"  Failed child playlist: {r_child.status_code}")
        return False
        
    child_base = child_m3u8_url.rsplit('/', 1)[0]
    segment_lines = [l.strip() for l in r_child.text.splitlines() if l.strip() and not l.startswith('#')]
    ts_urls = [s if s.startswith('http') else f"{child_base}/{s}" for s in segment_lines]
    
    total_segs = len(ts_urls)
    print(f"  [FAST-HLS] Found {total_segs} segments (~{total_segs*3/60:.1f} mins). Starting parallel download ({max_workers} threads)...")
    
    # 3. Download segments in parallel to temp directory
    with tempfile.TemporaryDirectory(dir=r"C:\scripts") as temp_dir:
        done_count = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(download_ts_segment, url, idx, temp_dir, session) for idx, url in enumerate(ts_urls)]
            for future in as_completed(futures):
                idx, ok = future.result()
                if not ok:
                    print(f"  [WARN] Failed to download segment {idx}")
                done_count += 1
                if done_count % 300 == 0 or done_count == total_segs:
                    print(f"    Progress: {done_count}/{total_segs} ({done_count/total_segs*100:.1f}%)")
                    
        # 4. Merge TS segments with ffmpeg into mp4
        print(f"  [FAST-HLS] Merging {total_segs} segments into MP4...")
        concat_list_path = os.path.join(temp_dir, "concat.txt")
        with open(concat_list_path, 'w', encoding='utf-8') as f:
            for idx in range(total_segs):
                f.write(f"file 'seg_{idx:06d}.ts'\n")
                
        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_list_path,
            '-c', 'copy',
            '-bsf:a', 'aac_adtstoasc',
            output_path
        ]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        if p.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 100000:
            t1 = time.time()
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"  [SUCCESS] {os.path.basename(output_path)} ({size_mb:.1f} MB) in {t1-t0:.1f}s!\n")
            return True
        else:
            print(f"  [ERROR] Concat failed with code {p.returncode}: {p.stderr[-500:]}\n")
            return False

def run(course_id="88092284", output_base=r"D:\ZEN大学関係\大学動画\クリエイティブの現場から"):
    print(f"=== Starting Fast Live Video Downloader for Course {course_id} ===")
    os.makedirs(output_base, exist_ok=True)
    
    cookie_jar = get_firefox_cookies()
    print("Loaded session cookies from Firefox.")
    
    api_url = f"https://api.nnn.ed.nico/v2/material/courses/{course_id}?revision=1"
    res = requests.get(api_url, cookies=cookie_jar, timeout=20)
    if not res.ok:
        print(f"Failed to fetch course: {res.status_code}")
        return
        
    chapters = res.json().get("course", {}).get("chapters", [])
    print(f"Found {len(chapters)} chapters in course.\n")
    
    for idx, chap in enumerate(chapters, 1):
        chap_id = str(chap.get("id"))
        raw_title = chap.get("title", "")
        chap_folder_name = format_chapter_title(raw_title, idx)
        chap_dir = os.path.join(output_base, chap_folder_name, "movies")
        os.makedirs(chap_dir, exist_ok=True)
        
        print(f">>> Chapter [{idx:02d}/{len(chapters):02d}] {chap_folder_name}")
        
        chap_api = f"https://api.nnn.ed.nico/v2/material/courses/{course_id}/chapters/{chap_id}?revision=1"
        try:
            r_c = requests.get(chap_api, cookies=cookie_jar, timeout=20)
            if not r_c.ok:
                print(f"  Failed chapter API: {r_c.status_code}")
                continue
                
            sections = r_c.json().get("chapter", {}).get("sections", [])
            lesson_sections = [s for s in sections if s.get("resource_type") == "lesson"]
            movie_sections = [s for s in sections if s.get("resource_type") == "movie"]
            
            for l_idx, s in enumerate(lesson_sections, 1):
                lesson_id = str(s.get("id"))
                l_title = clean_filename(s.get("title") or f"第{idx:02d}回講義")
                out_filename = f"{l_idx:02d}_{l_title}.mp4"
                out_path = os.path.join(chap_dir, out_filename)
                
                if os.path.exists(out_path) and os.path.getsize(out_path) > 50000000:
                    print(f"  [SKIP] Already exists ({os.path.getsize(out_path)/(1024*1024):.1f} MB): {out_filename}\n")
                    continue
                    
                lesson_api = f"https://api.nnn.ed.nico/v1/n_school/courses/{course_id}/chapters/{chap_id}/lessons/{lesson_id}?revision=1"
                r_l = requests.get(lesson_api, cookies=cookie_jar, timeout=20)
                if not r_l.ok:
                    print(f"  Failed lesson details API {lesson_id}: {r_l.status_code}")
                    continue
                    
                l_data = r_l.json().get("lesson", {})
                hls_url = l_data.get("archive", {}).get("url", {}).get("hls")
                if not hls_url:
                    print(f"  No HLS archive URL found for lesson {lesson_id}")
                    continue
                    
                download_hls_fast(hls_url, out_path, max_workers=24)
                
        except Exception as e:
            print(f"  Error processing chapter {chap_id}: {e}")

    print("\n==========================================")
    print(" ALL LIVE LESSON VIDEOS DOWNLOADED SUCCESSFULLY!")
    print(f" Saved to: {output_base}")
    print("==========================================")

if __name__ == "__main__":
    cid = sys.argv[1] if len(sys.argv) > 1 else "88092284"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else r"D:\ZEN大学関係\大学動画\クリエイティブの現場から"
    run(cid, out_dir)
