"""Tahqeeq AI layer — Gemini 2.5 Flash with the Google Search grounding
tool. Same call pattern as the other gap builds (urllib, key read from
the environment AT CALL TIME only, never stored or logged).

The prompt forbids inventing facts and forbids the model from writing
its own [n] citation numbers: engine.annotate() inserts the numbers
from the grounding metadata instead, so a citation can only point at a
source the live search actually returned for that exact span.
"""
import json
import os
import urllib.error
import urllib.request

MODEL = "gemini-2.5-flash"
TIMEOUT = 120

LANG_NOTES = {
    "en": "Answer in English.",
    "roman": "Answer in Roman-Urdu (Urdu written in Latin letters).",
    "ur": "Answer in Urdu script.",
}


def _get_key():
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_APIkey")


def key_available() -> bool:
    return bool(_get_key())


def _call(payload):
    """One generateContent call. Returns (body, error)."""
    key = _get_key()
    if not key:
        return None, ("AI ke liye GEMINI_API_KEY set nahi hai. "
                      "Server par key set karein, phir dobara try karein.")
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{MODEL}:generateContent?key={key}")
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        return None, f"Gemini HTTP {e.code}: {e.read()[:200].decode(errors='replace')}"
    except Exception as e:
        return None, f"Gemini request failed: {type(e).__name__}: {e}"


def _parse_grounded(body):
    """Extract answer text + grounding metadata from a response."""
    try:
        cand = body["candidates"][0]
        parts = cand.get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError, TypeError):
        return "", [], [], []
    gm = cand.get("groundingMetadata", {}) or {}
    chunks = []
    for c in gm.get("groundingChunks", []) or []:
        web = c.get("web") or {}
        if web.get("uri"):
            chunks.append({"uri": web.get("uri"),
                           "title": web.get("title") or ""})
    supports = gm.get("groundingSupports", []) or []
    queries = gm.get("webSearchQueries", []) or []
    return text, chunks, supports, queries


def grounded_answer(question, language="en", max_tokens=2200):
    """Ask one question with live-search grounding.

    Returns {text, chunks, supports, queries, error}. chunks are the
    raw grounding chunks ({uri, title}); supports map answer spans to
    chunk indices. When the search returns nothing useful the model is
    told to say so instead of answering from memory.
    """
    lang_note = LANG_NOTES.get(language, LANG_NOTES["en"])
    prompt = (
        "Answer the question below using ONLY the information from the "
        "live web search results provided to you. " + lang_note +
        " Rules: (1) If the search results do not contain the answer, "
        "say plainly that you could not verify it — do not answer from "
        "memory and do not guess numbers, dates or names. (2) Keep the "
        "answer focused and concise: a short paragraph per point, no "
        "filler intro. (3) Do NOT write [1], [2] or any citation numbers "
        "in your answer — the app adds them from the search results. "
        "(4) For Pakistan-related questions, prefer Pakistani sources "
        "and give prices in PKR where relevant.\n\nQuestion: " + question)
    body, err = _call({
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.2,
                             "maxOutputTokens": max_tokens},
    })
    if err:
        return {"text": "", "chunks": [], "supports": [],
                "queries": [], "error": err}
    text, chunks, supports, queries = _parse_grounded(body)
    if not text:
        return {"text": "", "chunks": chunks, "supports": supports,
                "queries": queries,
                "error": "Gemini ne khaali jawaab diya — dobara try karein."}
    return {"text": text, "chunks": chunks, "supports": supports,
            "queries": queries, "error": None}


def sub_questions(question, language="en"):
    """Deep mode: 3 sub-questions covering different angles.

    Returns a list of 3 strings. Falls back to deterministic variants
    when the model reply is not parseable JSON.
    """
    lang_note = LANG_NOTES.get(language, LANG_NOTES["en"])
    prompt = (
        "Given the research question below, write exactly 3 different "
        "sub-questions that together cover it from different angles: "
        "(1) the latest facts or current status, (2) the key numbers, "
        "prices or statistics, (3) criticisms, risks or alternatives. "
        + lang_note +
        " Reply with ONLY a JSON array of 3 strings, no other text.\n\n"
        "Question: " + question)
    body, err = _call({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 600},
    })
    fallback = [question + " — latest facts and current status",
                question + " — key numbers, prices and statistics",
                question + " — criticisms, risks and alternatives"]
    if err or not body:
        return fallback
    try:
        text = body["candidates"][0]["content"]["parts"][0]["text"]
        start, end = text.index("["), text.rindex("]") + 1
        items = json.loads(text[start:end])
        items = [str(x).strip() for x in items if str(x).strip()]
        if len(items) >= 3:
            return items[:3]
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    return fallback
