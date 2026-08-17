#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eMaktab Quiz Generator
Reads lesson bodies from the HTML, sends them to Gemini, gets 3-5 quiz
questions per lesson, and injects them into LESSON_QUIZZES in the file.

Usage:
  python3 generate_quizzes.py

Config below — set HTML_FILE and GEMINI_KEY.
"""

import os, re, time, json, sys, html as html_lib
import concurrent.futures

try:
    import requests
except ImportError:
    print("Run: pip install requests")
    sys.exit(1)

# ── CONFIG ────────────────────────────────────────────────────────────────────
GEMINI_KEY   = os.environ.get('GEMINI_KEY', 'YOUR_GEMINI_API_KEY_HERE')
HTML_FILE    = '../public/eMaktab_lms_v2.html'
BATCH_SIZE   = 1       # sequential — avoids 429
DELAY        = 8.0     # seconds between requests (~7 RPM, safely under free-tier 15 RPM)
SKIP_EXISTING = True   # skip lessons that already have >= 3 questions
QUESTIONS_PER_LESSON = 4   # 3–5
MODEL = 'gemini-2.5-flash-lite'
# ─────────────────────────────────────────────────────────────────────────────

GEMINI_URL = f'https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GEMINI_KEY}'
GEMINI_HEADERS = {'Content-Type': 'application/json'}

TAG_RE = re.compile(r'<[^>]+>')

def strip_html(text):
    return TAG_RE.sub(' ', html_lib.unescape(text)).strip()

def call_gemini(prompt, retries=7):
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": 2048,
            "temperature": 0.7,
            "responseMimeType": "application/json"
        }
    }
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.post(GEMINI_URL, json=body, headers=GEMINI_HEADERS, timeout=60)
            if r.status_code == 429:
                # Respect Retry-After if the server sends it; otherwise exponential back-off
                # starting at 60 s so the per-minute quota window has time to reset.
                retry_after = int(r.headers.get('Retry-After', 0))
                wait = max(retry_after, 60 * (attempt + 1))   # 60, 120, 180 …
                wait = min(wait, 360)                          # cap at 6 minutes
                last_err = f"HTTP 429"
                print(f"    ⏳ Rate limited, waiting {wait}s (attempt {attempt+1}/{retries})…")
                time.sleep(wait)
                continue
            if r.status_code == 503:
                wait = 20 * (attempt + 1)
                last_err = f"HTTP 503"
                time.sleep(wait)
                continue
            if not r.ok:
                raise Exception(f"HTTP {r.status_code}: {r.text[:200]}")
            data = r.json()
            return data['candidates'][0]['content']['parts'][0]['text']
        except requests.exceptions.Timeout:
            last_err = "Timeout"
            if attempt < retries - 1:
                time.sleep(15 * (attempt + 1))
                continue
            raise
    raise Exception(f"Failed after {retries} retries: {last_err}")

def build_quiz_prompt(lesson_name, subject, grade, lesson_text):
    n = QUESTIONS_PER_LESSON
    clean = lesson_text[:1500]  # keep prompt short
    return (
        f"Ин матни дарси мактабиро бихон ва {n} савол тести 4-вариантӣ бисоз.\n"
        f"Фан: {subject}, Синф: {grade}, Мавзӯъ: {lesson_name}\n"
        f"Шартҳо:\n"
        f"- Ҳар савол аз матни дарс бошад, на умумӣ\n"
        f"- 4 вариант, 1 ҷавоби дуруст\n"
        f"- Забон: тоҷикӣ\n"
        f"- Ҷавоб дар формати JSON:\n"
        f'[{{"q":"савол","opts":["а","б","в","г"],"ans":0}},...]\n'
        f"- ans = индекси ҷавоби дуруст (0,1,2 ё 3)\n"
        f"- Танҳо JSON, ҳеҷ чизи дигар\n\n"
        f"Матни дарс:\n{clean}"
    )

def parse_questions(raw):
    """Parse Gemini JSON response into list of {q, opts, ans} dicts."""
    raw = raw.strip()
    # Strip markdown fences if present
    raw = re.sub(r'^```(?:json)?\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    questions = json.loads(raw)
    out = []
    for item in questions:
        if not isinstance(item, dict):
            continue
        q = str(item.get('q', '')).strip()
        opts = item.get('opts', [])
        ans = int(item.get('ans', 0))
        if q and len(opts) == 4 and 0 <= ans <= 3:
            out.append({'q': q, 'opts': [str(o) for o in opts], 'ans': ans})
    return out

def format_quiz_js(lesson_id, questions):
    """Format a quiz entry as JS to inject into LESSON_QUIZZES."""
    lines = [f"'{lesson_id}': ["]
    for q in questions:
        opts_str = ','.join(f"'{o.replace(chr(39), chr(96))}'" for o in q['opts'])
        q_str = q['q'].replace("'", "`")
        lines.append(f"  {{q:'{q_str}', opts:[{opts_str}], ans:{q['ans']}}},")
    lines.append("],")
    return '\n'.join(lines)

# ── EXTRACT LESSONS ───────────────────────────────────────────────────────────

def extract_lessons(html_bytes):
    """Return list of {id, name, subject, grade, body_text, has_body}."""
    lessons = []
    curriculum_start = html_bytes.find(b'const CURRICULUM')
    curriculum_end   = html_bytes.find(b'async function loadCurriculum', curriculum_start)

    for course_m in re.finditer(
        rb"\{id:'([^']+)',grade:(\d+),subject:'([^']+)',name:'([^']+)'",
        html_bytes[curriculum_start:curriculum_end]
    ):
        grade   = int(course_m.group(2))
        subject = course_m.group(4).decode('utf-8', 'replace')
        pos     = course_m.start() + curriculum_start
        next_c  = html_bytes.find(b"\n{id:'", pos + 1)
        if next_c == -1: next_c = curriculum_end
        region  = html_bytes[pos:next_c]

        for tok in re.finditer(rb"\{id:'([^']+l\d+)',name:'([^']+)',body:`", region):
            lid   = tok.group(1).decode()
            lname = tok.group(2).decode('utf-8', 'replace')
            abs_pos  = pos + tok.end()
            body_end = html_bytes.find(b'`}', abs_pos)
            if body_end == -1: continue
            body = html_bytes[abs_pos:body_end].decode('utf-8', 'replace')
            lessons.append({
                'id': lid, 'name': lname,
                'subject': subject, 'grade': grade,
                'body_text': strip_html(body),
                'has_body': len(body) >= 400,
            })
    return lessons

def extract_existing_quiz_ids(html_bytes):
    """Return set of lesson IDs that already have >= 3 questions in LESSON_QUIZZES."""
    block_start = html_bytes.find(b'Object.assign(LESSON_QUIZZES,')
    block_end   = html_bytes.find(b'\n});', block_start)
    if block_start == -1 or block_end == -1:
        return set()
    block = html_bytes[block_start:block_end].decode('utf-8', 'replace')

    existing = set()
    for m in re.finditer(r"'([a-z0-9_]+)':\s*\[", block):
        lid = m.group(1)
        # Count how many {q: entries follow before the next ],
        section_start = m.end()
        section_end   = block.find('],', section_start)
        if section_end == -1: continue
        count = block[section_start:section_end].count('{q:')
        if count >= 3:
            existing.add(lid)
    return existing

def inject_quizzes(html_bytes, new_quizzes):
    """Append new quiz entries into the Object.assign(LESSON_QUIZZES, { ... }); block."""
    marker = b'Object.assign(LESSON_QUIZZES,'
    block_start = html_bytes.find(marker)
    block_end   = html_bytes.find(b'\n});', block_start)
    if block_start == -1 or block_end == -1:
        print("❌ Could not find LESSON_QUIZZES block in HTML!")
        return html_bytes

    insert_text = '\n\n// ═══ GENERATED QUIZZES ═══\n'
    for lid, questions in new_quizzes.items():
        insert_text += format_quiz_js(lid, questions) + '\n\n'

    insertion = insert_text.encode('utf-8')
    return html_bytes[:block_end] + insertion + html_bytes[block_end:]

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print(f"📖 Reading {HTML_FILE}...")
    with open(HTML_FILE, 'rb') as f:
        html = f.read()

    lessons = extract_lessons(html)
    print(f"✅ Found {len(lessons)} lessons")

    existing_ids = extract_existing_quiz_ids(html)
    print(f"⚡ {len(existing_ids)} lessons already have quizzes")

    if SKIP_EXISTING:
        to_gen = [l for l in lessons if l['id'] not in existing_ids and l['has_body']]
    else:
        to_gen = [l for l in lessons if l['has_body']]

    print(f"🎯 Will generate quizzes for {len(to_gen)} lessons\n")

    if not to_gen:
        print("✅ All lessons already have quizzes!")
        return

    to_gen.sort(key=lambda x: x['grade'])

    done, errors = 0, 0
    new_quizzes = {}
    start_time = time.time()

    def generate_one(lesson):
        prompt = build_quiz_prompt(
            lesson['name'], lesson['subject'],
            lesson['grade'], lesson['body_text']
        )
        try:
            raw = call_gemini(prompt)
            questions = parse_questions(raw)
            if len(questions) < 2:
                return lesson['id'], None, f"Only {len(questions)} valid questions"
            return lesson['id'], questions, None
        except Exception as e:
            return lesson['id'], None, str(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
        futures = {executor.submit(generate_one, l): l for l in to_gen}
        for future in concurrent.futures.as_completed(futures):
            lesson = futures[future]
            lid, questions, err = future.result()

            if err:
                errors += 1
                print(f"  ❌ {lid}: {err[:70]}")
            else:
                new_quizzes[lid] = questions
                done += 1
                elapsed = time.time() - start_time
                rate = done / elapsed if elapsed > 0 else 0
                remaining = len(to_gen) - done - errors
                eta = int(remaining / rate / 60) if rate > 0 else '?'
                print(f"  ✅ [{done}/{len(to_gen)}] {lid}: {lesson['name'][:40]} ({len(questions)}q) ETA:{eta}m")

            # Checkpoint every 200 lessons
            if done % 200 == 0 and done > 0:
                print(f"\n💾 Checkpoint: injecting {len(new_quizzes)} quizzes...")
                html = inject_quizzes(html, new_quizzes)
                new_quizzes = {}
                backup = HTML_FILE.replace('.html', f'_quiz_checkpoint_{done}.html')
                with open(backup, 'wb') as f:
                    f.write(html)
                with open(HTML_FILE, 'wb') as f:
                    f.write(html)
                print(f"   Saved checkpoint: {backup}\n")
                # Re-extract existing IDs so we don't double-inject
                existing_ids = extract_existing_quiz_ids(html)

            time.sleep(DELAY / BATCH_SIZE)

    if new_quizzes:
        print(f"\n💾 Saving final result ({len(new_quizzes)} quizzes)...")
        html = inject_quizzes(html, new_quizzes)
        with open(HTML_FILE, 'wb') as f:
            f.write(html)

    total = int(time.time() - start_time)
    print(f"\n🎉 Done! Quizzes generated: {done}, Errors: {errors}, Time: {total//60}m {total%60}s")

if __name__ == '__main__':
    main()
