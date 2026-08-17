# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary users are students in Tajikistan, grades 1–11, plus their parents. Many are outside Dushanbe, in villages/regions with inconsistent internet and no access to private tutors or paid supplementary materials. Secondary audience: people the founder pitches to (partners, press, potential funders) who land on the same marketing page.

## Product Purpose

еМактаб (eMaktab) is a free online school platform covering the official Tajikistan national curriculum, grades 1–11: thousands of lessons across dozens of subjects, quizzes, exams, an AI tutor that answers in Tajik, and a peer-mentor booking system connecting students with top-performing older students for free 1:1 help via Zoom/Telegram. Success = a student anywhere in the country, regardless of family income or location, can get the same quality of instruction and homework help as a student in Dushanbe with private tutors.

## Positioning

Free, Tajik-language-first, built entirely by one young Tajik developer/student (not an institution, not a foreign NGO). The AI tutor answering in Tajik and the peer-mentor network are the two things a generic "online school" competitor doesn't have — most alternatives are Russian/English-only or paid.

## Operating Context

Students access via phone browser primarily (not desktop-first). Real backend: Firebase (Auth + Firestore) for accounts/progress, a Cloud Function proxying Gemini for the AI tutor, EmailJS + a Zoom Server-to-Server OAuth Cloud Function for mentor session booking, real curriculum data (curriculum-data.js). This site is the marketing/landing page (`public/index.html`) that funnels into the logged-in app at `public/eMaktab_lms_v2.html`.

## Capabilities and Constraints

- 100% free, no payment, no ads — this is a binding brand commitment, not just current pricing.
- Bilingual TJ/EN toggle already implemented and must be preserved (Tajik is the primary/default language, not a translation afterthought).
- Real stats to use, not invented: 3,574 lessons, 79 subjects, grades 1–11. Per-stage/per-subject breakdowns should be computed from real data (already implemented via a `GRADES` object in-page) rather than fabricated numbers — this was an explicit prior correction, do not regress it.
- The AI "solver" demo on the page must call the real Cloud Function endpoint (`https://geminiproxy-rcwua2htiq-uc.a.run.app`), not a canned/stub answer.
- No founder/About section on the landing page — was explicitly removed at the site owner's request; do not reinstate it.
- No emoji as UI icons — replaced with line-icon SVGs sitewide per explicit prior direction; keep that standard.
- Static HTML/CSS/vanilla JS, deployed via Firebase Hosting (`firebase deploy --only hosting`) — no build step, no bundler, no npm frontend framework. Do not introduce React/Next/a bundler for this file.

## Brand Commitments

- Name/wordmark: "еМактаб" (Cyrillic), "eMaktab" in Latin/English contexts.
- Logo: a vector emblem (graduation cap + globe + laurel wreath) — real asset at `/logo-mark.png` (+ `/logo-mark-192.png`, `/favicon-32.png`, `/favicon.svg`). This replaced an earlier low-res placeholder; do not regress to raster crops or emoji-as-logo.
- Founder: Bahrom Ashurov (Ashurov Bahrom / Ашуров Баҳром), building this largely solo. Credit appears in structured data and footer, not as an on-page About section.
- Prior explicit aesthetic feedback: the owner rejected a "classical serif, gold/navy, university-prospectus" direction as looking old-fashioned, and rejected a follow-up pass for still "looking like AI did it" (too-symmetric grids, centered-everything, templated section rhythm). Most recent accepted direction was a dark zinc/near-black base with one vibrant indigo/cyan accent and Manrope/Inter typography — colors were approved, structure was not. This round should treat structure/composition as the primary problem to solve, not palette.

## Evidence on Hand

- Live site: https://emaktab.tj
- Real curriculum data lives in `public/curriculum-data.js` (large file) and a `GRADES` object already used in the page's own JS for real per-grade subject lists.
- No customer testimonials, press logos, or case studies exist — do not fabricate any.

## Product Principles

1. Free and accessible beats polished-but-paywalled — never let a design implicitly suggest tiers, premium, or payment.
2. Tajik-first, not Tajik-as-an-afterthought — typography, layout, and copy must work natively in Cyrillic, not just Latin.
3. Real numbers only — no invented stats, testimonials, or company logos.
4. Built by one person, for a whole country — the story is real but is not the hero of this specific surface (About section stays off-page).
5. This page's job is Persuade (a visitor decides to sign up or explore further) — optimize for that, not for looking like a generic SaaS template.

## Accessibility & Inclusion

No formal standard specified. Given the real-world audience (variable device quality, inconsistent connections, phone-first), keep contrast high, avoid motion that blocks content, and don't rely on hover-only interactions for anything essential.
