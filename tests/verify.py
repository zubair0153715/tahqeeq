"""Tahqeeq verification — hand-computed fixtures, no AI needed.

Fixture sentence (hand-counted):
  "Larkana has 551716 people. It is in Sindh."
  - "Larkana has 551716 people." = 26 chars -> span (0, 26)
  - " " = 1 char (index 26)
  - "It is in Sindh." = 15 chars -> span (27, 42)
  Total length 42. Covered by both spans: 26 + 15 = 41 chars.
  Coverage on the original text: 41/42 = 97.6% -> 98.

Combine fixture:
  Sec A text "Alpha is one. Beta is two." (26 chars)
    "Alpha is one." = 13 chars -> (0, 13); "Beta is two." -> (14, 26)
  Sec B text "Gamma is three." (15 chars) -> (0, 15)
  Sources: A=[a.example/1, b.example/2], B=[a.example/1 (same URL), c.example/3]
  Global sources after dedupe: 3 (a, b, c). B's local [1] remaps to
  global [1] (a.example is global index 0). Covered chars: 13+12+15=40.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "clinic-demo"))

from app.tahqeeq import engine
from app.tahqeeq.pages import TAHQEEQ_HTML
from app.tahqeeq.routes import ask as route_ask

TEXT = "Larkana has 551716 people. It is in Sindh."
SUPPORTS = [
    {"segment": {"startIndex": 0, "endIndex": 26}, "groundingChunkIndices": [0]},
    {"segment": {"startIndex": 27, "endIndex": 42}, "groundingChunkIndices": [1]},
]

passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS {name}")
    else:
        failed += 1
        print(f"FAIL {name} {extra}")


# --- fixture sanity (hand counts must match Python) ---
check("fixture length 42", len(TEXT) == 42, f"got {len(TEXT)}")
check("span 1 text", TEXT[0:26] == "Larkana has 551716 people.")
check("span 2 text", TEXT[27:42] == "It is in Sindh.")

# --- caps ---
check("caps empty", engine.check_caps("", "quick", "en") is not None)
check("caps too short", engine.check_caps("ab", "quick", "en") is not None)
check("caps too long", engine.check_caps("x" * 2001, "quick", "en") is not None)
check("caps bad mode", engine.check_caps("hello world", "turbo", "en") is not None)
check("caps bad lang", engine.check_caps("hello world", "quick", "fr") is not None)
check("caps ok", engine.check_caps("hello world", "deep", "ur") is None)

# --- citation parsing ---
check("parse [1] [2, 3] [1]",
      engine.parse_citation_numbers("[1] a [2, 3] b [1]") == [1, 2, 3])
check("parse none", engine.parse_citation_numbers("no markers") == [])

# --- annotate ---
annotated, cited, _ = engine.annotate(TEXT, SUPPORTS)
check("annotate text",
      annotated == "Larkana has 551716 people. [1] It is in Sindh. [2]",
      f"got {annotated!r}")
check("annotate cited", cited == [0, 1], f"got {cited}")

# overlapping supports cite once
overlap = [
    {"segment": {"startIndex": 0, "endIndex": 26}, "groundingChunkIndices": [0]},
    {"segment": {"startIndex": 10, "endIndex": 26}, "groundingChunkIndices": [1]},
]
ann2, cited2, _ = engine.annotate(TEXT, overlap)
check("overlap cited once", ann2.count("[") == 1 and cited2 == [0],
      f"got {ann2!r} {cited2}")

# model already wrote a marker: no double insert
pre = "Larkana has 551716 people. [1] It is in Sindh."
ann3, _, _ = engine.annotate(pre, SUPPORTS)
check("no double marker", ann3.count("[1]") == 1, f"got {ann3!r}")

# --- audit ---
a = engine.audit(TEXT, SUPPORTS, 2, annotated_text=annotated)
check("audit coverage 98", a["coverage"] == 98, f"got {a['coverage']}")
check("audit cited", a["cited"] == [1, 2])
check("audit dangling none", a["dangling"] == [])
check("audit uncited none", a["uncited"] == [])
a3 = engine.audit(TEXT, SUPPORTS, 3, annotated_text=annotated)
check("audit uncited [3]", a3["uncited"] == [3], f"got {a3['uncited']}")
a_bad = engine.audit("claim [9] here", [], 2)
check("audit dangling [9]", a_bad["dangling"] == [9], f"got {a_bad['dangling']}")
check("audit empty coverage 0",
      engine.audit("", [], 0)["coverage"] == 0)

# --- combine_sections ---
sec_a = {"heading": "Latest facts & status",
         "text": "Alpha is one. Beta is two.",
         "supports": [
             {"segment": {"startIndex": 0, "endIndex": 13},
              "groundingChunkIndices": [0]},
             {"segment": {"startIndex": 14, "endIndex": 26},
              "groundingChunkIndices": [1]}],
         "sources": [{"title": "A", "url": "https://a.example/1",
                      "domain": "a.example"},
                     {"title": "B", "url": "https://b.example/2",
                      "domain": "b.example"}]}
sec_b = {"heading": "Key numbers & statistics",
         "text": "Gamma is three.",
         "supports": [{"segment": {"startIndex": 0, "endIndex": 15},
                       "groundingChunkIndices": [0]}],
         "sources": [{"title": "A2", "url": "https://a.example/1",
                      "domain": "a.example"},
                     {"title": "C", "url": "https://c.example/3",
                      "domain": "c.example"}]}
combo = engine.combine_sections([sec_a, sec_b])
check("combine sources deduped to 3",
      len(combo["sources"]) == 3, f"got {len(combo['sources'])}")
check("combine source order",
      [s["url"] for s in combo["sources"]] ==
      ["https://a.example/1", "https://b.example/2", "https://c.example/3"])
check("combine A citations",
      "Alpha is one. [1] Beta is two. [2]" in combo["text"],
      f"got {combo['text']!r}")
check("combine B remapped to global [1]",
      "Gamma is three. [1]" in combo["text"], f"got {combo['text']!r}")
check("combine audit cited", combo["audit"]["cited"] == [1, 2])
check("combine audit uncited", combo["audit"]["uncited"] == [3])
check("combine audit coverage",
      combo["audit"]["coverage"] == round(100 * 40 / len(combo["text"])),
      f"got {combo['audit']['coverage']} len {len(combo['text'])}")

# --- dedupe / markdown ---
check("dedupe keeps first",
      len(engine.dedupe_sources(
          [{"url": "https://x.example/"}, {"url": "https://x.example"},
           {"url": "https://y.example"}])) == 2)
md = engine.build_markdown("Q?", combo["text"], combo["sources"],
                           combo["audit"], "deep", "en")
check("markdown has question", "Q?" in md)
check("markdown has sources", "## Sources" in md and "a.example" in md)
check("markdown has audit",
      "Citation check" in md and "Sources retrieved: 3" in md)

# --- resolve_source (live: known redirect from the grounding test) ---
r = engine.resolve_source(
    "https://vertexaisearch.cloud.google.com/grounding-api-redirect/"
    "AUZIYQEyT-UUYH1p8F-L22qUt87oyDGZMWO8zupuYP8TQIWhluZp-0PXAIkJ5tLsDscS0HBCrVkCdtAXXLm04YZv4jcYwTXMImcSMgOTttyM3_-QAeP13axSJxB0qadEuIoRLyE=",
    "wikipedia.org")
check("resolve redirect to wikipedia",
      r["url"] == "https://en.wikipedia.org/wiki/Larkana",
      f"got {r['url']!r}")
check("resolve domain", r["domain"] == "en.wikipedia.org")
r2 = engine.resolve_source("https://example.com", "")
check("resolve plain url kept", r2["url"] == "https://example.com")
check("resolve bad url kept",
      engine.resolve_source("https://nonexistent.invalid/",
                            "t")["url"] == "https://nonexistent.invalid/")

# --- page ---
check("page has title", "Tahqeeq" in TAHQEEQ_HTML)
check("page honest limits", "Honest limits" in TAHQEEQ_HTML)
check("page deep mode", 'value="deep"' in TAHQEEQ_HTML)
check("page urdu option", 'value="ur"' in TAHQEEQ_HTML)

# --- routes (no GEMINI_API_KEY in this shell: key gate must 400) ---
resp = asyncio.run(route_ask(question="", mode="quick", language="en"))
check("route empty question 400", resp.status_code == 400)
resp = asyncio.run(route_ask(question="What is Larkana?",
                             mode="quick", language="en"))
body = json.loads(resp.body.decode())
check("route no-key 400", resp.status_code == 400,
      f"got {resp.status_code} {body}")
check("route no-key message mentions key",
      "GEMINI_API_KEY" in body.get("error", ""))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
