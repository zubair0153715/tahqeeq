# Tahqeeq — تحقیق

**Free research answers with verified citations. No account, no card, no usage meter.**

Ask any question and get a sourced answer — in English, Roman-Urdu or
Urdu script. Every citation number is inserted by the app from the
live search grounding metadata, so a number can only point at a source
the search actually returned for that exact sentence. A citation check
on every answer shows how much of it the retrieved sources really
support, which numbers are dangling, and which retrieved sources were
never cited.

## Why it exists

Premium answer engines charge $20–200/month (Perplexity Pro $20/mo,
Max $200/mo) and still fail the thing they sell: a third-party audit
(Haus Research, Sep 2026) found **34.7% of checked numeric citations
failed**, Trustpilot sits at **1.4/5 (825 reviews, 83% one-star)** on
opaque credit limits that bite mid-task, and the free tier is ~3–5 Pro
searches a day. Tahqeeq is the free, open, original alternative — built
clean-room from public pricing pages and review complaints only. See
the full gap analysis in the operator's workspace
(`market-gaps/daily/2026-11-01-tahqeeq.md`).

## What it does

- **Quick mode** — one grounded answer with live-search citations.
- **Deep mode** — 3 sub-questions (latest facts, key numbers,
  criticisms/alternatives), one grounded answer each, stitched into a
  structured brief with one global, deduplicated source list.
- **Verified citations** — numbers come from Gemini's Google Search
  grounding metadata (`groundingSupports`), never from the model's own
  say-so. The audit reports coverage %, dangling citations and
  uncited sources on every answer.
- **Real source URLs** — grounding redirects are resolved to the actual
  page (e.g. `en.wikipedia.org/wiki/Larkana`) before display.
- **Urdu + Roman-Urdu + English** answers, with PK-aware prompting
  (Pakistani sources preferred, prices in PKR).
- **Export** — copy any answer as Markdown with sources + audit.
- **History** — your recent questions live in your own browser
  (localStorage); nothing is stored on the server.

## Honest limits

- Answers are only as good as the retrieved pages; numbers must be
  re-checked at the source before quoting.
- Search grounding needs `GEMINI_API_KEY` on the server; when the key
  is missing or the search returns nothing, the page says so instead
  of silently answering from memory.
- No file upload in v1; no audio.

## Run it

Live: `https://clinic-demo.fastapicloud.dev/tahqeeq`

Local (from the `clinic-demo` repo, which mounts this package):

```bash
GEMINI_API_KEY=your-key uvicorn app.main:app --port 8000
# open http://localhost:8000/tahqeeq
```

## Verify

```bash
python3 tests/verify.py   # 44 hand-computed checks, no AI needed
```

## Stack

Python + FastAPI (server) · Gemini 2.5 Flash with the Google Search
grounding tool (answers) · plain HTML/CSS/JS (page, no build step).
