#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eMaktab Lesson Generator
Generates full lesson content using Gemini API and injects into HTML file.

Usage:
  python3 generate_lessons.py

Requirements:
  pip install requests

Config:
  Set your Gemini API key below, or pass as env variable GEMINI_KEY
"""

import os, re, time, random, json, sys

try:
    import requests
except ImportError:
    print("Run: pip install requests")
    sys.exit(1)

# ── CONFIG ────────────────────────────────────────────────────────────────────
GEMINI_KEY = os.environ.get('GEMINI_KEY', 'YOUR_GEMINI_API_KEY_HERE')
HTML_FILE  = '../public/eMaktab_lms_v2.html'  # path to your HTML file
BATCH_SIZE = 5     # parallel requests (keep at 5 to avoid rate limits)
DELAY      = 0.3   # seconds between batches
SKIP_EXISTING = True  # skip lessons that already have 600+ char bodies
MODEL = 'gemini-2.5-flash-lite'
# ─────────────────────────────────────────────────────────────────────────────

GEMINI_URL = f'https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GEMINI_KEY}'

def word_target(grade):
    if grade <= 4:  return 250
    if grade <= 8:  return 300
    return 350

def template_id(lesson_id):
    """Pick one of 5 templates pseudo-randomly but consistently per lesson"""
    return (hash(lesson_id) % 5) + 1

def build_prompt(name, group, subject, grade, tmpl):
    words = word_target(grade)
    
    base = (
        f"Барои платформаи таълимии еМактаб (Тоҷикистон) дарс тайёр кун.\n"
        f"Фан: {subject}\nСинф: {grade}\nМавзӯъ: {group}\nДарс: {name}\n"
        f"Тақрибан {words} калима. Забон: тоҷикӣ. Танҳо HTML тегҳо, markdown не.\n\n"
    )

    structures = {
        1: (  # Classic
            "Сохтор:\n"
            f"<h2>{name}</h2>\n"
            "<p>Муаррифӣ: ин дарс чист ва чаро муҳим аст (2 ҷумла)</p>\n"
            "<div class='formula-box'>Қоида ё мафҳуми асосӣ</div>\n"
            "<h3>Шарҳи муфассал</h3>\n"
            "<p>Шарҳи мукаммал бо мисолҳо</p>\n"
            "<div class='example-box'><div class='ex-label'>Мисол</div><p>Мисоли воқеӣ аз ҳаёти тоҷик</p></div>\n"
            "<div class='example-box'><div class='ex-label'>Машқ</div><p>3 савол бо ҷавоб</p></div>\n"
            "<div class='tip-box'>Нуктаи ёдовар</div>"
        ),
        2: (  # Step by step
            "Сохтор (қадам ба қадам):\n"
            f"<h2>{name}</h2>\n"
            "<div class='formula-box'>Ҳадафи дарс</div>\n"
            "<h3>Қадами 1</h3><p>...</p>\n"
            "<h3>Қадами 2</h3><p>...</p>\n"
            "<h3>Қадами 3</h3><p>...</p>\n"
            "<div class='example-box'><div class='ex-label'>Мисол</div><p>Намунаи ҳаллшуда</p></div>\n"
            "<div class='example-box'><div class='ex-label'>Машқ</div><p>Акнун худат кӯш</p></div>\n"
            "<div class='tip-box'>Хатоҳои маъмул</div>"
        ),
        3: (  # Life & Science
            "Сохтор (аз ҳаёт ба илм):\n"
            f"<h2>{name}</h2>\n"
            "<p>Ҳикояи кӯтоҳ аз ҳаёти тоҷик ки ба мавзӯъ алоқа дорад</p>\n"
            "<div class='formula-box'>Таърифи расмӣ</div>\n"
            "<p>Шарҳи мафҳум тавассути ҳикоя</p>\n"
            "<div class='example-box'><div class='ex-label'>Мисол</div><p>Пеш ва баъд аз донистан</p></div>\n"
            "<div class='example-box'><div class='ex-label'>Машқ</div><p>Саволҳо</p></div>\n"
            "<div class='tip-box'>Хулоса</div>"
        ),
        4: (  # Dialogue
            "Сохтор (муколама):\n"
            f"<h2>{name}</h2>\n"
            "<p><strong>Омӯзгор:</strong> ... <strong>Донишҷӯ:</strong> ... (2-3 муколама)</p>\n"
            "<div class='formula-box'>Мафҳуми асосӣ</div>\n"
            "<p>Шарҳи муфассал</p>\n"
            "<div class='example-box'><div class='ex-label'>Мисол</div><p>Масъалаи ҳаллшуда</p></div>\n"
            "<div class='example-box'><div class='ex-label'>Машқ</div><p>Барои донишҷӯ</p></div>\n"
            "<div class='tip-box'>Нуктаи муҳим</div>"
        ),
        5: (  # Mind map
            "Сохтор (3 зербахш):\n"
            f"<h2>{name}</h2>\n"
            "<div class='formula-box'>Мафҳуми марказӣ</div>\n"
            "<h3>Бахши 1</h3><p>...</p>\n"
            "<h3>Бахши 2</h3><p>...</p>\n"
            "<h3>Бахши 3</h3><p>...</p>\n"
            "<div class='example-box'><div class='ex-label'>Мисол</div><p>Ҳамаи 3 бахшро мепайвандад</p></div>\n"
            "<div class='example-box'><div class='ex-label'>Машқ</div><p>Саволҳо</p></div>\n"
            "<div class='tip-box'>Хулосаи кӯтоҳ</div>"
        ),
    }
    
    return base + structures[tmpl]

def call_gemini(prompt):
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 1400, "temperature": 0.8}
    }
    r = requests.post(GEMINI_URL, json=body, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data['candidates'][0]['content']['parts'][0]['text']

def extract_lessons(html_bytes):
    """Extract all lessons with byte positions for body replacement"""
    lessons = []
    curriculum_start = html_bytes.find(b'const CURRICULUM')
    curriculum_end = html_bytes.find(b'async function loadCurriculum', curriculum_start)
    
    for course_m in re.finditer(
        b"\\{id:'([^']+)',grade:(\\d+),subject:'([^']+)',name:'([^']+)'",
        html_bytes[curriculum_start:curriculum_end]
    ):
        grade = int(course_m.group(2))
        subject = course_m.group(4).decode('utf-8', 'replace')
        pos = course_m.start() + curriculum_start
        next_course = html_bytes.find(b"\n{id:'", pos + 1)
        if next_course == -1: next_course = curriculum_end
        region = html_bytes[pos:next_course]
        
        current_group = 'Мавзӯъ'
        for tok in re.finditer(b"group:'([^']+)'|\\{id:'([^']+l\\d+)',name:'([^']+)',body:`", region):
            if tok.group(1):
                current_group = tok.group(1).decode('utf-8', 'replace')
            elif tok.group(2):
                lid = tok.group(2).decode()
                lname = tok.group(3).decode('utf-8', 'replace')
                abs_pos = pos + tok.end()
                body_end = html_bytes.find(b'`}', abs_pos)
                if body_end == -1: continue
                body = html_bytes[abs_pos:body_end]
                lessons.append({
                    'id': lid, 'name': lname,
                    'group': current_group, 'subject': subject, 'grade': grade,
                    'body_start': abs_pos, 'body_end': body_end,
                    'body_len': len(body)
                })
    return lessons

def main():
    if GEMINI_KEY == 'YOUR_GEMINI_API_KEY_HERE':
        print("❌ Set your GEMINI_KEY in the script or via environment variable!")
        print("   export GEMINI_KEY='your-key-here'")
        sys.exit(1)

    print(f"📖 Reading {HTML_FILE}...")
    with open(HTML_FILE, 'rb') as f:
        html = f.read()

    lessons = extract_lessons(html)
    print(f"✅ Found {len(lessons)} total lessons")

    if SKIP_EXISTING:
        to_gen = [l for l in lessons if l['body_len'] < 600]
        print(f"⚡ Skipping {len(lessons) - len(to_gen)} already full lessons")
        print(f"🎯 Will generate {len(to_gen)} lessons")
    else:
        to_gen = lessons
        print(f"🎯 Will regenerate ALL {len(to_gen)} lessons")

    if not to_gen:
        print("✅ All lessons already have content!")
        return

    # Sort by grade so we process smallest first
    to_gen.sort(key=lambda x: x['grade'])

    done = 0
    errors = 0
    replacements = {}  # id -> new_body_bytes
    start_time = time.time()

    print(f"\n🚀 Starting generation ({BATCH_SIZE} parallel)...\n")

    import concurrent.futures

    def generate_one(lesson):
        tmpl = template_id(lesson['id'])
        prompt = build_prompt(
            lesson['name'], lesson['group'],
            lesson['subject'], lesson['grade'], tmpl
        )
        try:
            body = call_gemini(prompt)
            # Clean up: remove markdown code fences if any
            body = re.sub(r'^```html?\n?', '', body.strip())
            body = re.sub(r'\n?```$', '', body.strip())
            return lesson['id'], body, None
        except Exception as e:
            return lesson['id'], None, str(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
        futures = {executor.submit(generate_one, l): l for l in to_gen}
        
        for future in concurrent.futures.as_completed(futures):
            lesson = futures[future]
            lid, body, err = future.result()
            
            if err:
                errors += 1
                print(f"  ❌ {lid}: {err[:60]}")
            elif body and len(body) > 200:
                replacements[lid] = body.encode('utf-8')
                done += 1
                elapsed = time.time() - start_time
                rate = done / elapsed if elapsed > 0 else 0
                remaining = len(to_gen) - done - errors
                eta = int(remaining / rate / 60) if rate > 0 else '?'
                print(f"  ✅ [{done}/{len(to_gen)}] {lid}: {lesson['name'][:40]} (tmpl {template_id(lid)}) ETA:{eta}m")
            else:
                errors += 1
                print(f"  ⚠️  {lid}: empty response")
            
            # Save checkpoint every 100 lessons
            if done % 100 == 0 and done > 0:
                print(f"\n💾 Checkpoint: saving {done} lessons...\n")
                html = apply_replacements(html, lessons, replacements)
                replacements = {}
                backup = HTML_FILE.replace('.html', f'_checkpoint_{done}.html')
                with open(backup, 'wb') as f:
                    f.write(html)
                with open(HTML_FILE, 'wb') as f:
                    f.write(html)
                # Re-extract lessons for correct byte positions
                lessons = extract_lessons(html)
                to_gen_ids = {l['id'] for l in to_gen}
                # We already saved done ones, reload their positions
            
            time.sleep(DELAY / BATCH_SIZE)

    # Final save
    print(f"\n💾 Saving final result...")
    html = apply_replacements(html, lessons, replacements)
    with open(HTML_FILE, 'wb') as f:
        f.write(html)

    total_time = int(time.time() - start_time)
    print(f"\n🎉 Done! Generated: {done}, Errors: {errors}, Time: {total_time//60}m {total_time%60}s")

def apply_replacements(html, lessons, replacements):
    """Apply all replacements at once, working backwards to preserve positions"""
    if not replacements:
        return html
    
    # Sort by body_start descending to replace from end to start
    to_replace = [(l['body_start'], l['body_end'], replacements[l['id']])
                  for l in lessons if l['id'] in replacements]
    to_replace.sort(key=lambda x: x[0], reverse=True)
    
    for body_start, body_end, new_body in to_replace:
        html = html[:body_start] + new_body + html[body_end:]
    
    return html

if __name__ == '__main__':
    main()
