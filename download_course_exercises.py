# -*- coding: utf-8 -*-
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
import html
import requests
import rookiepy
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

COURSE_ID = "449211952"
BASE_DIR = r"D:\ZEN大学関係\大学動画\民俗学"

def clean_filename(text):
    if not text:
        return ""
    return re.sub(r'[\\/*?:"<>|]', '_', text).strip()

def format_chapter_title(raw_title, fallback_index=1):
    if not raw_title:
        raw_title = ""
    clean = re.sub(r'^(?:第?\s*\d+\s*[章回\.\:\-]?\s*)+', '', raw_title).strip()
    if not clean:
        clean = raw_title.strip() or f"第{fallback_index}章"
    m = re.search(r'\d+', raw_title)
    chap_num = int(m.group(0)) if m else fallback_index
    return f"{chap_num:02d}. {clean}"

def get_firefox_cookies():
    raw_cookies = rookiepy.firefox()
    jar = {}
    for c in raw_cookies:
        name = c.get("name")
        domain = c.get("domain", "")
        if not name or not domain:
            continue
        if any(k in domain for k in ['nico', 'dwango', 'nnn', 'ed.nico']):
            jar[name] = c.get("value")
    return jar

def build_exercise_html(statement_html, questions_data):
    html_out = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap');
  
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Noto Sans JP', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background-color: #ffffff;
    color: #333333;
    padding: 30px 40px;
    display: inline-block;
    min-width: 900px;
    max-width: 1050px;
  }
  .card-container {
    background: #ffffff;
    border-radius: 12px;
    padding: 26px 28px;
    border: 1px solid #e2e8f0;
    box-shadow: 0 4px 20px rgba(0,0,0,0.06);
  }
  .statement {
    font-size: 16px;
    font-weight: 500;
    line-height: 1.8;
    margin-bottom: 24px;
    color: #1e293b;
    word-break: break-word;
  }
  .statement p {
    margin-bottom: 8px;
  }
  .statement img {
    max-width: 100%;
    height: auto;
    border-radius: 6px;
    margin: 10px 0;
  }
  .question-block {
    margin-bottom: 20px;
  }
  .question-label {
    font-size: 14px;
    font-weight: 700;
    color: #64748b;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .choices-list {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-bottom: 20px;
  }
  .choice-item {
    display: flex;
    align-items: center;
    padding: 12px 18px;
    border-radius: 8px;
    font-size: 15px;
    font-weight: 500;
    border: 1.5px solid #e2e8f0;
    background-color: #f8fafc;
    color: #334155;
  }
  .choice-item.correct {
    background-color: #00ba66;
    border-color: #00ba66;
    color: #ffffff;
    font-weight: 700;
    box-shadow: 0 4px 12px rgba(0, 186, 102, 0.22);
  }
  .choice-icon {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    margin-right: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
    font-weight: 700;
    flex-shrink: 0;
  }
  .choice-item:not(.correct) .choice-icon {
    border: 2px solid #cbd5e1;
    color: #64748b;
    background: #ffffff;
  }
  .choice-item.correct .choice-icon {
    background: #ffffff;
    color: #00ba66;
  }
  .explanation-box {
    background-color: #fef9c3;
    border: 1.5px solid #fde047;
    border-radius: 8px;
    padding: 18px 22px;
    margin-top: 16px;
    color: #713f12;
    font-size: 14.5px;
    line-height: 1.7;
  }
  .explanation-title {
    font-weight: 700;
    margin-bottom: 8px;
    color: #854d0e;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .explanation-content {
    color: #451a03;
  }
  .explanation-content p {
    margin-bottom: 6px;
  }
</style>
</head>
<body>
  <div class="card-container">
    <div class="statement">""" + statement_html + """</div>
"""
    for q in questions_data:
        html_out += f"""
    <div class="question-block">
      <div class="question-label">{html.escape(q['question_title'])}</div>
      <ul class="choices-list">
"""
        for val, c_text, is_corr in q['choices']:
            corr_cls = "correct" if is_corr else ""
            icon_content = "✓" if is_corr else str(val)
            html_out += f"""        <li class="choice-item {corr_cls}">
          <span class="choice-icon">{icon_content}</span>
          <span class="choice-text">{html.escape(c_text)}</span>
        </li>
"""
        html_out += """      </ul>
"""
        if q.get('explanation_html'):
            html_out += f"""      <div class="explanation-box">
        <div class="explanation-title">💡 解答・解説</div>
        <div class="explanation-content">{q['explanation_html']}</div>
      </div>
"""
        html_out += """    </div>
"""
    html_out += """  </div>
</body>
</html>"""
    return html_out

def run(course_id=COURSE_ID, output_base=BASE_DIR):
    print(f"=== Starting All-Choices Exercise Scraper for Course {course_id} ===")
    os.makedirs(output_base, exist_ok=True)

    cookie_jar = get_firefox_cookies()
    print(f"Loaded session cookies from Firefox.")

    # 1. APIから全チャプター一覧を取得
    api_url = f"https://api.nnn.ed.nico/v2/material/courses/{course_id}?revision=1"
    res = requests.get(api_url, cookies=cookie_jar, timeout=20)
    if not res.ok:
        print(f"Failed to fetch course: {res.status_code}")
        return

    data = res.json()
    chapters = data.get("course", {}).get("chapters", [])
    print(f"Found {len(chapters)} chapters in course.")

    # 2. 各チャプター内の確認テスト (exercise) を収集
    tasks = []
    for idx, chap in enumerate(chapters, 1):
        chap_id = chap.get("id")
        raw_title = chap.get("title", "")
        chap_folder_name = format_chapter_title(raw_title, idx)
        
        chap_api = f"https://api.nnn.ed.nico/v2/material/courses/{course_id}/chapters/{chap_id}?revision=1"
        try:
            r_c = requests.get(chap_api, cookies=cookie_jar, timeout=20)
            if r_c.ok:
                c_data = r_c.json()
                sections = c_data.get("chapter", {}).get("sections", [])
                exercises = [s for s in sections if s.get("resource_type") in ("exercise", "eval_test", "test")]
                tasks.append({
                    "chap_id": chap_id,
                    "folder_name": chap_folder_name,
                    "exercises": exercises
                })
                print(f"  [{idx:02d}/{len(chapters):02d}] {chap_folder_name}: {len(exercises)} tests found")
        except Exception as e:
            print(f"  Error fetching chapter {chap_id}: {e}")

    # 3. Playwrightインスタンスを起動して各問題のHTMLを完全レンダリングして保存
    total_saved = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1050, 'height': 800}, device_scale_factor=2)

        for t in tasks:
            chap_folder = t["folder_name"]
            exercises = t["exercises"]
            if not exercises:
                continue

            exercises_dir = os.path.join(output_base, chap_folder, "exercises")
            os.makedirs(exercises_dir, exist_ok=True)
            print(f"\n>>> Processing {chap_folder} ({len(exercises)} tests)...")

            for ex_idx, ex in enumerate(exercises, 1):
                ex_id = ex.get("id")
                ex_title = clean_filename(ex.get("title") or "確認テスト")
                
                # Fetch result page HTML directly
                ex_url = f"https://www.nnn.ed.nico/contents/courses/{course_id}/chapters/{t['chap_id']}/exercises/{ex_id}/result?content_type=zen_univ"

                try:
                    r_ex = requests.get(ex_url, cookies=cookie_jar, timeout=20)
                    r_ex.encoding = 'utf-8'
                    
                    soup = BeautifulSoup(r_ex.text, 'html.parser')
                    section = soup.find('section', class_='exercise')
                    if not section:
                        print(f"  Warning: No exercise section found in {ex_id}")
                        continue

                    statement_div = section.find('div', class_='statement')
                    statement_html = "".join(str(c) for c in statement_div.contents).strip() if statement_div else ""

                    questions = []
                    q_elements = section.find_all('li', attrs={'data-type': 'normal'})
                    if not q_elements:
                        # Fallback for alternative structures
                        q_elements = [section]

                    for q_li in q_elements:
                        q_title = q_li.find('div', class_='question')
                        q_title_txt = q_title.get_text(strip=True) if q_title else '【選択肢】'
                        
                        answers_ul = q_li.find('ul', class_='answers')
                        choices = []
                        if answers_ul:
                            for idx_c, a_li in enumerate(answers_ul.find_all('li'), 1):
                                val = a_li.get('data-input-value') or str(idx_c)
                                is_corr = a_li.get('data-correct') == 'true'
                                a_txt = a_li.get_text(strip=True)
                                choices.append((val, a_txt, is_corr))
                                
                        exp_div = q_li.find('div', class_='explanation')
                        exp_html = ""
                        if exp_div:
                            exp_html = "".join(str(c) for c in exp_div.contents).strip()
                            
                        questions.append({
                            'question_title': q_title_txt,
                            'choices': choices,
                            'explanation_html': exp_html
                        })

                    # Render to full card HTML
                    rendered_html = build_exercise_html(statement_html, questions)
                    page.set_content(rendered_html)
                    page.wait_for_timeout(200)

                    card = page.query_selector('.card-container')
                    q_filename = f"{ex_idx:02d}_{ex_title}.png"
                    save_path = os.path.join(exercises_dir, q_filename)

                    if card:
                        card.screenshot(path=save_path)
                    else:
                        page.screenshot(path=save_path, full_page=True)

                    total_saved += 1
                    print(f"  [SAVED] {q_filename} ({os.path.getsize(save_path)/1024:.1f} KB)")

                except Exception as e:
                    print(f"  Error capturing {ex_url}: {e}")

        browser.close()

    print(f"\n==========================================")
    print(f" COMPLETED! Total {total_saved} exercise screenshots saved with all choices.")
    print(f" Target Folder: {output_base}")
    print(f"==========================================")

if __name__ == "__main__":
    course = sys.argv[1] if len(sys.argv) > 1 else COURSE_ID
    run(course)
