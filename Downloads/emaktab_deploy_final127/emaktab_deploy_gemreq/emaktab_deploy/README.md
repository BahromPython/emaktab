# еМактаб (eMaktab)

Free online school platform for Tajikistan, grades 1–11.

**Live site:** [emaktab.tj](https://emaktab.tj)

еМактаб covers the official Tajikistan national curriculum — 3,574 lessons across 79 subjects — with quizzes, exams, an AI tutor that answers in Tajik, and a peer-mentor booking system connecting students with top-performing older students for free 1:1 help over Zoom/Telegram.

100% free. No payment, no ads.

## Structure

```
public/                    Everything Firebase Hosting actually serves
  index.html                Landing/marketing page
  eMaktab_lms_v2.html        The logged-in learning platform (dashboard, courses,
                              AI tutor, mentor booking, profile, admin)
  curriculum-data.js        Full curriculum content (grades 1–11)
  mentors.html               Standalone mentor-booking entry point
  mentor-portal.html         Private portal for mentors to manage their own profile
  terms.html, support.html   Static pages
  manifest.json, sw.js       PWA manifest + service worker

functions/                 Firebase Cloud Functions
  index.js                  Gemini AI proxy (keeps the API key server-side) +
                              Zoom Server-to-Server OAuth meeting creation

scripts/                   One-off content-generation scripts (Gemini-assisted)
  generate_lessons.py        Generate lesson content into eMaktab_lms_v2.html
  generate_quizzes.py        Generate per-lesson quiz questions
  generate_exams.py          Generate per-course final exams

PRODUCT.md                 Durable product context (audience, purpose, brand commitments)
firebase.json               Hosting + Functions config
```

## Stack

Static HTML/CSS/vanilla JS — no build step, no bundler, no frontend framework. Deployed via Firebase Hosting. Backend is Firebase (Auth + Firestore) plus two Cloud Functions (Gemini AI proxy, Zoom meeting creation).

## Deploying

```bash
firebase deploy --only hosting      # site
firebase deploy --only functions    # Cloud Functions
```

Requires being logged into the Firebase account that owns the `donish-79396` project (`firebase login:use <account>`).

## Content generation scripts

The scripts in `scripts/` call the Gemini API to fill in lesson/quiz/exam content directly inside `public/eMaktab_lms_v2.html`. Run them from the `scripts/` directory; each writes periodic checkpoint copies of the HTML file (gitignored) so a long run can resume after an interruption. Set `GEMINI_KEY` as an environment variable before running — never commit an API key.

## License

All rights reserved. This is a proprietary platform built and maintained by [Bahrom Ashurov](https://instagram.com/_.bahrrrom._).
