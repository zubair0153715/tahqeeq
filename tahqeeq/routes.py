"""Tahqeeq routes — free research-answer engine (Perplexity gap build).

Original clean-room build. Not affiliated with Perplexity. Stateless:
nothing is stored server-side; answers exist only in the request/
response and in the user's own browser (localStorage history). No
account, no card, no subscription, no usage meter.

Quick mode: one grounded answer. Deep mode: 3 sub-questions, one
grounded answer each, stitched into a brief with global citations.
Every citation number is inserted by engine.annotate() from the live
search grounding metadata — a number can only point at a source the
search actually returned for that span.
"""
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, JSONResponse

from . import engine, gemini
from .pages import TAHQEEQ_HTML

router = APIRouter(prefix="/tahqeeq")

HEADINGS = ["Latest facts & status",
            "Key numbers & statistics",
            "Criticisms, risks & alternatives"]


def _resolve(chunks):
    """Resolve grounding chunks to real source URLs, in parallel."""
    chunks = (chunks or [])[:engine.MAX_SOURCES]
    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(
            lambda c: engine.resolve_source(c.get("uri", ""),
                                            c.get("title", "")),
            chunks))


def _quick(question, language):
    res = gemini.grounded_answer(question, language)
    if res["error"]:
        return None, res["error"]
    sources = _resolve(res["chunks"])
    text, _, _ = engine.annotate(res["text"], res["supports"])
    audit = engine.audit(res["text"], res["supports"], len(sources),
                         annotated_text=text)
    warning = None
    if not sources:
        warning = ("Live search se koi source nahi mila — yeh jawaab "
                   "verify nahi hua. Sawaal badal kar dobara try karein.")
    return {"answer": text, "sources": sources, "audit": audit,
            "queries": res["queries"], "warning": warning}, None


def _deep(question, language):
    subs = gemini.sub_questions(question, language)
    sections = []
    queries = []
    for i, sub in enumerate(subs):
        res = gemini.grounded_answer(sub, language, max_tokens=1800)
        if res["error"]:
            return None, res["error"]
        queries += res["queries"]
        sections.append({
            "heading": HEADINGS[i] if i < len(HEADINGS) else f"Angle {i + 1}",
            "text": res["text"],
            "supports": res["supports"],
            "sources": _resolve(res["chunks"]),
        })
    combined = engine.combine_sections(sections)
    return {"answer": combined["text"], "sources": combined["sources"],
            "audit": combined["audit"], "queries": queries,
            "warning": None}, None


@router.get("", response_class=HTMLResponse)
def index():
    return TAHQEEQ_HTML


@router.get("/api/ai-status")
def ai_status():
    return {"ai_available": gemini.key_available()}


@router.post("/api/ask")
async def ask(question: str = Form(""), mode: str = Form("quick"),
              language: str = Form("en")):
    err = engine.check_caps(question, mode, language)
    if err:
        return JSONResponse({"ok": False, "error": err}, status_code=400)
    if not gemini.key_available():
        return JSONResponse(
            {"ok": False,
             "error": "AI ke liye GEMINI_API_KEY set nahi hai — server "
                      "par key set karein, phir dobara try karein."},
            status_code=400)
    if mode == "deep":
        data, err = _deep(question, language)
    else:
        data, err = _quick(question, language)
    if err:
        return JSONResponse({"ok": False, "error": err}, status_code=400)
    data["ok"] = True
    data["mode"] = mode
    data["language"] = language
    data["question"] = question.strip()
    return data
