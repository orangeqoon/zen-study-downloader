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
import shutil
import glob
import requests
import rookiepy
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

DEFAULT_COURSE_ID = "302927622"
DEFAULT_BASE_DIR = r"D:\ZEN大学関係\大学動画\地域アントレプレナーシップ"

def clean_filename(text):
    if not text:
        return ""
    return re.sub(r'[\\/*?:"<>|]', '_', text).strip()

def format_chapter_title(raw_title, fallback_index=1):
    if not raw_title:
        raw_title = ""
    clean = re.sub(r'^(?:第?\s*\d+\s*[章回\.\:\-]?\s*)+', '', raw_title).strip()
    clean = clean_filename(clean)
    if not clean:
        clean = clean_filename(raw_title).strip() or f"第{fallback_index}章"
    m = re.search(r'\d+', raw_title)
    chap_num = int(m.group(0)) if m else fallback_index
    return f"{chap_num:02d}. {clean}"

def get_firefox_cookies():
    domains = ['ed.nico', 'nicovideo.jp', 'dwango.jp', 'nnn.ed.nico']
    cookies_list = rookiepy.firefox(domains)
    jar = {}
    for c in cookies_list:
        jar[c['name']] = c['value']
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
  .word-answer-box {
    display: flex;
    align-items: center;
    padding: 14px 20px;
    border-radius: 8px;
    background-color: #00ba66;
    border: 1.5px solid #00ba66;
    color: #ffffff;
    font-size: 16px;
    font-weight: 700;
    box-shadow: 0 4px 12px rgba(0, 186, 102, 0.22);
    gap: 12px;
    margin-bottom: 20px;
  }
  .word-icon {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: #ffffff;
    color: #00ba66;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
    font-weight: 700;
    flex-shrink: 0;
  }
  .word-text {
    font-size: 16px;
    letter-spacing: 0.5px;
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
"""
        if q.get('type') == 'word':
            html_out += f"""
      <div class="word-answer-box">
        <span class="word-icon">✓</span>
        <span class="word-text">{html.escape(q.get('correct_word', ''))}</span>
      </div>
"""
        elif q.get('choices'):
            html_out += """      <ul class="choices-list">
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
        if q.get('explanation_html') and q.get('explanation_html').strip():
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

def run(course_id=DEFAULT_COURSE_ID, output_base=None):
    print(f"=== Starting All-Choices Exercise Scraper for Course {course_id} ===")

    cookie_jar = get_firefox_cookies()
    print(f"Loaded session cookies from Firefox.")

    # 1. APIから全チャプター一覧を取得
    api_url = f"https://api.nnn.ed.nico/v2/material/courses/{course_id}?revision=1"
    res = requests.get(api_url, cookies=cookie_jar, timeout=20)
    if not res.ok:
        print(f"Failed to fetch course: {res.status_code}")
        return

    data = res.json()
    c_info = data.get("course", {})
    sub_title = c_info.get("subject_category", {}).get("title")
    main_title = c_info.get("title", "")
    course_name = sub_title if sub_title else (main_title if main_title not in ["オンデマンド", "ライブ"] else f"Course_{course_id}")
    course_name = clean_filename(course_name)

    if not output_base or output_base == DEFAULT_BASE_DIR:
        output_base = os.path.join(r"D:\ZEN大学関係\大学動画", course_name)

    os.makedirs(output_base, exist_ok=True)
    print(f"Target Output Directory: {output_base}")

    chapters = c_info.get("chapters", [])
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
                exercises = [s for s in sections if s.get("resource_type") in ("exercise", "eval_test", "test", "report")]
                tasks.append({
                    "chap_id": chap_id,
                    "folder_name": chap_folder_name,
                    "exercises": exercises
                })
                print(f"  [{idx:02d}/{len(chapters):02d}] {chap_folder_name}: {len(exercises)} tests found")
        except Exception as e:
            print(f"  Error fetching chapter {chap_id}: {e}")

    # 3. Playwrightで各問題のHTMLを完全レンダリングして保存
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
                ex_url = ex.get("content_url") or f"https://www.nnn.ed.nico/contents/courses/{course_id}/chapters/{t['chap_id']}/exercises/{ex_id}/result?content_type=zen_univ"

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
                    q_elements = section.find_all('li', attrs={'data-type': True})
                    if not q_elements:
                        q_elements = [section]

                    for q_li in q_elements:
                        q_type = q_li.get('data-type', 'normal')
                        q_title = q_li.find('div', class_='question')
                        
                        exp_div = q_li.find('div', class_='explanation')
                        if not exp_div or not exp_div.get_text(strip=True):
                            exp_div = section.find('div', class_='explanation')
                        
                        exp_html = ""
                        if exp_div:
                            exp_html = "".join(str(c) for c in exp_div.contents).strip()

                        if q_type == 'word' or q_li.find('input', class_='answers'):
                            input_el = q_li.find('input', class_='answers') or q_li.find('input')
                            correct_word = ""
                            if input_el:
                                correct_word = input_el.get('data-correct-answers') or input_el.get('value') or ""
                            
                            q_title_txt = q_title.get_text(strip=True) if (q_title and q_title.get_text(strip=True)) else '【正解入力】'
                            questions.append({
                                'type': 'word',
                                'question_title': q_title_txt,
                                'correct_word': correct_word,
                                'explanation_html': exp_html
                            })
                        elif q_type == 'essay' or q_li.find('textarea'):
                            questions.append({
                                'type': 'essay',
                                'question_title': '【レポート記述課題】',
                                'explanation_html': exp_html
                            })
                        else:
                            q_title_txt = q_title.get_text(strip=True) if (q_title and q_title.get_text(strip=True)) else '【選択肢】'
                            answers_ul = q_li.find('ul', class_='answers')
                            choices = []
                            if answers_ul:
                                for idx_c, a_li in enumerate(answers_ul.find_all('li'), 1):
                                    val = a_li.get('data-input-value') or str(idx_c)
                                    is_corr = a_li.get('data-correct') == 'true'
                                    a_txt = a_li.get_text(strip=True)
                                    choices.append((val, a_txt, is_corr))
                                    
                            questions.append({
                                'type': 'normal',
                                'question_title': q_title_txt,
                                'choices': choices,
                                'explanation_html': exp_html
                            })

                    rendered_html = build_exercise_html(statement_html, questions)
                    page.set_content(rendered_html)
                    page.wait_for_timeout(150)

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

    # 4. 全問統合フォルダへの自動一括集約コピー
    consolidated_dir = os.path.join(output_base, "【確認テスト・演習まとめ】")
    os.makedirs(consolidated_dir, exist_ok=True)
    chapter_dirs = sorted([d for d in os.listdir(output_base) if os.path.isdir(os.path.join(output_base, d)) and re.match(r'^\d+', d)])
    consolidated_count = 0

    for chap in chapter_dirs:
        m = re.match(r'^(\d+)', chap)
        chap_num = int(m.group(1)) if m else 0
        chap_ex_dir = os.path.join(output_base, chap, "exercises")
        if os.path.exists(chap_ex_dir):
            for p in sorted(glob.glob(os.path.join(chap_ex_dir, "*.png"))):
                fname = os.path.basename(p)
                new_fname = f"第{chap_num:02d}章_{fname}"
                target_path = os.path.join(consolidated_dir, new_fname)
                shutil.copy2(p, target_path)
                consolidated_count += 1

    print(f"\n==========================================")
    print(f" COMPLETED! Total {total_saved} exercise screenshots saved.")
    print(f" Consolidated {consolidated_count} images into: {consolidated_dir}")
    print(f"==========================================")

if __name__ == "__main__":
    course = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_COURSE_ID
    output = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_BASE_DIR
    run(course, output)
