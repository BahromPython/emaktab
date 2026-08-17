#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eMaktab Exam Generator
Reads courses from the HTML, generates 20-50 exam questions per course using
Gemini, and injects them into EXAM_QUESTIONS in the file.

Exams are per-COURSE (not per-lesson). A course is the top-level unit
(e.g. "Алгебра, синфи 9").

Usage:
  python3 generate_exams.py

Config below.
"""

import os, re, time, json, sys, html as html_lib
import concurrent.futures

try:
    import requests
except ImportError:
    print("Run: pip install requests")
    sys.exit(1)

# ── CONFIG ────────────────────────────────────────────────────────────────────
GEMINI_KEY    = os.environ.get('GEMINI_KEY', 'YOUR_GEMINI_API_KEY_HERE')
HTML_FILE     = '../public/eMaktab_lms_v2.html'
BATCH_SIZE    = 4      # parallel (lower than quiz — larger prompts)
DELAY         = 0.3
MIN_QUESTIONS = 20     # minimum per exam
MAX_QUESTIONS = 25     # maximum per exam
MIN_EXISTING  = 15     # skip course if it already has this many questions
MODEL = 'gemini-2.5-flash'
# ─────────────────────────────────────────────────────────────────────────────

GEMINI_URL = f'https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GEMINI_KEY}'
GEMINI_HEADERS = {'Content-Type': 'application/json'}

TAG_RE = re.compile(r'<[^>]+>')

def strip_html(text):
    return TAG_RE.sub(' ', html_lib.unescape(text)).strip()

def call_gemini(prompt, retries=4):
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": 8192,
            "temperature": 0.75,
            "responseMimeType": "application/json"
        }
    }
    for attempt in range(retries):
        try:
            r = requests.post(GEMINI_URL, json=body, headers=GEMINI_HEADERS, timeout=60)
            if r.status_code in (503, 429):
                wait = 5 * (2 ** attempt)
                time.sleep(wait)
                continue
            r.raise_for_status()
            data = r.json()
            return data['candidates'][0]['content']['parts'][0]['text']
        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                time.sleep(5)
                continue
            raise
    raise Exception(f"Failed after {retries} retries")

def build_exam_prompt(course_id, course_name, subject, grade, topics, n_questions):
    topics_str = ', '.join(topics[:30]) if topics else 'курс умумӣ'
    return (
        f"Барои фани «{subject}», синфи {grade} ({course_name}) "
        f"дақиқан {n_questions} савол тести 4-вариантӣ тайёр кун.\n"
        f"Мавзӯъҳо ки бояд дар имтиҳон бошанд:\n{topics_str}\n\n"
        f"Шартҳо:\n"
        f"- Саволҳо мушкилии гуногун дошта бошанд (осон, миёна, мушкил)\n"
        f"- Ҳар савол 4 вариант дорад, 1 ҷавоби дуруст\n"
        f"- Саволҳо мушаххас ва аз барномаи синфи {grade} бошанд\n"
        f"- Забон: тоҷикӣ\n"
        f"- Ҷавоб ТАНҲО дар формати JSON:\n"
        f'[{{"q":"савол","opts":["а","б","в","г"],"ans":0}},...]\n'
        f"- ans = индекси ҷавоби дуруст (0,1,2 ё 3)\n"
        f"- Дақиқан {n_questions} савол, на камтар, на зиёдтар\n"
        f"- Танҳо JSON массив, ҳеҷ чизи дигар\n"
    )

def parse_questions(raw):
    raw = raw.strip()
    raw = re.sub(r'^```(?:json)?\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    questions = json.loads(raw)
    out = []
    for item in questions:
        if not isinstance(item, dict):
            continue
        q    = str(item.get('q', '')).strip()
        opts = item.get('opts', [])
        ans  = int(item.get('ans', 0))
        if q and len(opts) == 4 and 0 <= ans <= 3:
            out.append({'q': q, 'opts': [str(o) for o in opts], 'ans': ans})
    return out

def format_exam_js(course_id, questions):
    lines = [f"  '{course_id}': ["]
    for q in questions:
        opts_str = ','.join(f"'{o.replace(chr(39), chr(96))}'" for o in q['opts'])
        q_str    = q['q'].replace("'", "`")
        lines.append(f"    {{q:'{q_str}', opts:[{opts_str}], ans:{q['ans']}}},")
    lines.append("  ],")
    return '\n'.join(lines)

# ── EXTRACT COURSES ───────────────────────────────────────────────────────────

def extract_courses(html_bytes):
    """Return list of {id, name, subject, grade, topics, lesson_count}."""
    courses = []
    curriculum_start = html_bytes.find(b'const CURRICULUM')
    curriculum_end   = html_bytes.find(b'async function loadCurriculum', curriculum_start)

    for course_m in re.finditer(
        rb"\{id:'([^']+)',grade:(\d+),subject:'([^']+)',name:'([^']+)'",
        html_bytes[curriculum_start:curriculum_end]
    ):
        cid     = course_m.group(1).decode()
        grade   = int(course_m.group(2))
        subject = course_m.group(4).decode('utf-8', 'replace')
        pos     = course_m.start() + curriculum_start
        next_c  = html_bytes.find(b"\n{id:'", pos + 1)
        if next_c == -1: next_c = curriculum_end
        region  = html_bytes[pos:next_c]

        # Extract lesson names as topics
        topics = []
        for tok in re.finditer(rb"\{id:'([^']+l\d+)',name:'([^']+)',body:`", region):
            lname = tok.group(2).decode('utf-8', 'replace')
            topics.append(lname)

        # Extract group names too
        groups = []
        for tok in re.finditer(rb"group:'([^']+)'", region):
            g = tok.group(1).decode('utf-8', 'replace')
            if g not in groups:
                groups.append(g)

        courses.append({
            'id': cid, 'subject': subject, 'grade': grade,
            'name': subject,
            'topics': groups + topics,
            'lesson_count': len(topics),
        })
    return courses

def extract_existing_exam_ids(html_bytes):
    """Return dict of {course_id: question_count} for EXAM_QUESTIONS entries."""
    block_start = html_bytes.find(b'const EXAM_QUESTIONS = {')
    block_end   = html_bytes.find(b'\n};', block_start)
    if block_start == -1 or block_end == -1:
        return {}
    block = html_bytes[block_start:block_end].decode('utf-8', 'replace')

    result = {}
    for m in re.finditer(r"'([a-z0-9_]+)':\s*\[", block):
        cid = m.group(1)
        section_start = m.end()
        # Find end of this array
        depth = 1
        i = section_start
        while i < len(block) and depth > 0:
            if block[i] == '[': depth += 1
            elif block[i] == ']': depth -= 1
            i += 1
        section = block[section_start:i]
        count = section.count('{q:')
        result[cid] = count
    return result

def replace_exam_entry(html_bytes, course_id, new_questions):
    """Replace an existing EXAM_QUESTIONS entry with new content."""
    pattern = (f"'{course_id}':").encode()
    pos = html_bytes.find(pattern)
    if pos == -1:
        return html_bytes, False

    # Find the opening [ of the array
    arr_start = html_bytes.find(b'[', pos)
    if arr_start == -1:
        return html_bytes, False

    # Find matching ]
    depth = 1
    i = arr_start + 1
    while i < len(html_bytes) and depth > 0:
        if html_bytes[i:i+1] == b'[': depth += 1
        elif html_bytes[i:i+1] == b']': depth -= 1
        i += 1
    arr_end = i  # after the closing ]

    new_arr = '[\n'
    for q in new_questions:
        opts_str = ','.join(f"'{o.replace(chr(39), chr(96))}'" for o in q['opts'])
        q_str    = q['q'].replace("'", "`")
        new_arr += f"    {{q:'{q_str}', opts:[{opts_str}], ans:{q['ans']}}},\n"
    new_arr += '  ]'

    return (html_bytes[:arr_start] + new_arr.encode('utf-8') + html_bytes[arr_end:]), True

def insert_new_exam_entry(html_bytes, course_id, questions):
    """Insert a brand-new entry into EXAM_QUESTIONS before the closing };"""
    marker = b'const EXAM_QUESTIONS = {'
    block_start = html_bytes.find(marker)
    block_end   = html_bytes.find(b'\n};', block_start)
    if block_start == -1 or block_end == -1:
        return html_bytes

    entry = '\n' + format_exam_js(course_id, questions) + '\n'
    return html_bytes[:block_end] + entry.encode('utf-8') + html_bytes[block_end:]

def inject_exam(html_bytes, course_id, questions):
    """Replace existing entry or insert new one."""
    html_bytes, replaced = replace_exam_entry(html_bytes, course_id, questions)
    if not replaced:
        html_bytes = insert_new_exam_entry(html_bytes, course_id, questions)
    return html_bytes

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print(f"📖 Reading {HTML_FILE}...")
    with open(HTML_FILE, 'rb') as f:
        html = f.read()

    courses = extract_courses(html)
    print(f"✅ Found {len(courses)} courses")

    existing = extract_existing_exam_ids(html)
    print(f"⚡ {len(existing)} courses already have exam questions")

    to_gen = []
    for c in courses:
        if c['lesson_count'] == 0:
            continue  # no lessons in this course
        current_count = existing.get(c['id'], 0)
        if current_count >= MIN_EXISTING:
            continue  # already enough questions
        to_gen.append(c)

    print(f"🎯 Will generate exams for {len(to_gen)} courses\n")

    if not to_gen:
        print("✅ All courses already have sufficient exam questions!")
        return

    to_gen.sort(key=lambda x: x['grade'])

    done, errors = 0, 0
    new_exams = {}  # course_id -> questions
    start_time = time.time()

    def generate_one(course):
        # Scale question count to course size
        n = min(MAX_QUESTIONS, max(MIN_QUESTIONS, course['lesson_count'] * 2))
        prompt = build_exam_prompt(
            course['id'], course['name'],
            course['subject'], course['grade'],
            course['topics'], n
        )
        try:
            raw = call_gemini(prompt)
            questions = parse_questions(raw)
            if len(questions) < 10:
                return course['id'], None, f"Only {len(questions)} valid questions parsed"
            return course['id'], questions, None
        except Exception as e:
            return course['id'], None, str(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
        futures = {executor.submit(generate_one, c): c for c in to_gen}
        for future in concurrent.futures.as_completed(futures):
            course = futures[future]
            cid, questions, err = future.result()

            if err:
                errors += 1
                print(f"  ❌ {cid}: {err[:70]}")
            else:
                new_exams[cid] = questions
                done += 1
                elapsed = time.time() - start_time
                rate = done / elapsed if elapsed > 0 else 0
                remaining = len(to_gen) - done - errors
                eta = int(remaining / rate / 60) if rate > 0 else '?'
                print(f"  ✅ [{done}/{len(to_gen)}] {cid}: {course['subject']} gr{course['grade']} ({len(questions)}q) ETA:{eta}m")

            # Checkpoint every 50 courses
            if done % 50 == 0 and done > 0:
                print(f"\n💾 Checkpoint: saving {len(new_exams)} exams...")
                for cid2, qs in new_exams.items():
                    html = inject_exam(html, cid2, qs)
                new_exams = {}
                backup = HTML_FILE.replace('.html', f'_exam_checkpoint_{done}.html')
                with open(backup, 'wb') as f:
                    f.write(html)
                with open(HTML_FILE, 'wb') as f:
                    f.write(html)
                existing = extract_existing_exam_ids(html)
                print(f"   Saved: {backup}\n")

            time.sleep(DELAY / BATCH_SIZE)

    if new_exams:
        print(f"\n💾 Saving final result ({len(new_exams)} exams)...")
        for cid, qs in new_exams.items():
            html = inject_exam(html, cid, qs)
        with open(HTML_FILE, 'wb') as f:
            f.write(html)

    total = int(time.time() - start_time)
    print(f"\n🎉 Done! Exams generated: {done}, Errors: {errors}, Time: {total//60}m {total%60}s")

if __name__ == '__main__':
    main()
