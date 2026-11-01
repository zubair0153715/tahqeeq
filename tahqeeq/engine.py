"""Tahqeeq engine — deterministic citation handling for a research-answer
tool. Original clean-room code.

The AI (gemini.py) returns an answer plus the live-search grounding
metadata: which text spans the search tool supports, and which retrieved
chunks each span rests on. Everything in this module is pure arithmetic
on that metadata — no model judgement:

- annotate(): insert [n] markers at the end of each supported span, so a
  citation number can only appear if the search tool actually returned
  that source for that span. Overlapping spans are cited once.
- audit(): which numbers are cited, which are dangling (no such source),
  which retrieved sources were never cited, and what fraction of the
  answer the search tool actually supports.
- combine_sections(): deep mode stitches per-angle answers into one
  brief, remapping each angle's local citation numbers onto one global
  source list (deduplicated by URL).
- resolve_source(): follow a grounding redirect once (HEAD, no redirect
  following) to recover the real source URL for display.
- build_markdown(): export the answer + sources + audit as Markdown.
"""
import re
import urllib.error
import urllib.parse
import urllib.request

MAX_QUESTION = 2000
MIN_QUESTION = 3
MODES = ("quick", "deep")
LANGUAGES = ("en", "roman", "ur")
MAX_SOURCES = 12
RESOLVE_TIMEOUT = 8


def check_caps(question, mode, language):
    """Return an error string, or None when the request is acceptable."""
    if mode not in MODES:
        return "Mode quick ya deep hona chahiye."
    if language not in LANGUAGES:
        return "Language en, roman ya ur hona chahiye."
    q = (question or "").strip()
    if len(q) < MIN_QUESTION:
        return "Sawaal bohat chhota hai — kam az kam 3 characters likhein."
    if len(q) > MAX_QUESTION:
        return f"Sawaal {MAX_QUESTION} characters se zyada lamba hai."
    return None


def parse_citation_numbers(text):
    """All distinct integers inside [n] / [n, m] markers, sorted."""
    found = set()
    for group in re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", text or ""):
        for part in group.split(","):
            found.add(int(part.strip()))
    return sorted(found)


def _overlaps(a_start, a_end, intervals):
    for s, e in intervals:
        if a_start < e and s < a_end:
            return True
    return False


def annotate(text, supports):
    """Insert [n] markers after each search-supported span.

    supports: [{segment: {startIndex, endIndex}, groundingChunkIndices}]
    Chunk indices are 0-based here; markers are 1-based. Returns
    (annotated_text, cited_chunk_indices, covered_intervals).
    """
    text = text or ""
    used = []
    cited = set()
    # Largest end first so insertions never shift a smaller span's indices.
    ordered = sorted(
        supports or [],
        key=lambda s: s.get("segment", {}).get("endIndex", 0),
        reverse=True)
    for sup in ordered:
        seg = sup.get("segment", {})
        start = int(seg.get("startIndex", 0))
        end = int(seg.get("endIndex", 0))
        idxs = [int(i) for i in sup.get("groundingChunkIndices", [])]
        if not idxs or end <= start or start < 0 or end > len(text):
            continue
        if _overlaps(start, end, used):
            continue
        # Model already put a marker right here: do not double-cite.
        if "[" in text[max(0, end - 1):end + 6]:
            used.append((start, end))
            cited.update(idxs)
            continue
        marker = " [" + ", ".join(str(i + 1) for i in sorted(set(idxs))) + "]"
        text = text[:end] + marker + text[end:]
        used.append((start, end))
        cited.update(idxs)
    return text, sorted(cited), sorted(used)


def audit(text, supports, n_sources, annotated_text=None):
    """Deterministic citation check for one answer.

    coverage = % of answer characters inside a search-supported span
    (measured on the pre-annotation text, so inserted markers cannot
    shift the spans). cited numbers are read from annotated_text when
    given, else from text itself.
    dangling = cited numbers with no such source. uncited = retrieved
    sources the answer never cites.
    """
    text = text or ""
    cited = parse_citation_numbers(
        annotated_text if annotated_text is not None else text)
    dangling = [n for n in cited if n < 1 or n > n_sources]
    covered = 0
    merged = []
    for sup in supports or []:
        seg = sup.get("segment", {})
        s = max(0, int(seg.get("startIndex", 0)))
        e = min(len(text), int(seg.get("endIndex", 0)))
        if e > s:
            merged.append((s, e))
    merged.sort()
    cur_s = cur_e = None
    for s, e in merged:
        if cur_s is None:
            cur_s, cur_e = s, e
        elif s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            covered += cur_e - cur_s
            cur_s, cur_e = s, e
    if cur_s is not None:
        covered += cur_e - cur_s
    coverage = round(100 * covered / max(1, len(text))) if text else 0
    uncited = [i for i in range(1, n_sources + 1) if i not in cited]
    return {"cited": cited, "dangling": dangling, "uncited": uncited,
            "coverage": coverage, "n_sources": n_sources}


def _domain_of(url):
    try:
        return urllib.parse.urlparse(url).netloc or url
    except Exception:
        return url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def resolve_source(uri, title=""):
    """Resolve one grounding redirect to the real source URL.

    Follows a single Location header (HEAD, redirects refused by the
    handler). On any failure the redirect URI itself is kept — the link
    still works in a browser.
    """
    if not uri:
        return {"title": title or "", "url": "", "domain": ""}
    final = uri
    try:
        req = urllib.request.Request(uri, method="HEAD")
        opener = urllib.request.build_opener(_NoRedirect())
        with opener.open(req, timeout=RESOLVE_TIMEOUT):
            pass
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location") if e.headers else None
        if loc:
            final = loc
    except Exception:
        pass
    title = title or _domain_of(final)
    return {"title": title, "url": final, "domain": _domain_of(final)}


def dedupe_sources(sources):
    """Dedupe by normalized URL, keeping first-seen order."""
    seen = {}
    out = []
    for s in sources or []:
        key = (s.get("url") or "").strip().rstrip("/").lower()
        if not key or key in seen:
            continue
        seen[key] = True
        out.append(s)
    return out


def combine_sections(sections):
    """Stitch per-angle answers into one brief with global citations.

    Each section: {heading, text, supports, sources} where sources are
    resolved {title, url, domain} dicts and supports/chunk indices are
    local to the section. Returns {text, sources, supports, audit}.
    """
    global_sources = []
    url_to_global = {}

    def global_index(source):
        key = (source.get("url") or "").strip().rstrip("/").lower()
        if key in url_to_global:
            return url_to_global[key]
        idx = len(global_sources)
        global_sources.append(source)
        url_to_global[key] = idx
        return idx

    parts = []
    all_supports = []
    offset = 0
    for sec in sections:
        local_to_global = {}
        for li, src in enumerate(sec.get("sources") or []):
            local_to_global[li] = global_index(src)
        annotated, _, _ = annotate(sec.get("text") or "",
                                   sec.get("supports") or [])

        def _remap(m, _map=local_to_global):
            nums = [int(p.strip()) for p in m.group(1).split(",")]
            mapped = sorted({_map[n - 1] + 1 for n in nums
                             if 1 <= n <= len(_map)})
            return "[" + ", ".join(str(x) for x in mapped) + "]" if mapped else ""

        annotated = re.sub(r"\[(\d+(?:\s*,\s*\d+)*)\]", _remap, annotated)
        heading = "## " + (sec.get("heading") or "Answer") + "\n\n"
        parts.append(heading + annotated)
        body_start = offset + len(heading)
        for sup in sec.get("supports") or []:
            seg = sup.get("segment", {})
            s = int(seg.get("startIndex", 0))
            e = int(seg.get("endIndex", 0))
            idxs = [local_to_global[i] for i in
                    sup.get("groundingChunkIndices", [])
                    if i in local_to_global]
            if idxs and e > s:
                all_supports.append({
                    "segment": {"startIndex": body_start + s,
                                "endIndex": body_start + e},
                    "groundingChunkIndices": idxs})
        offset += len(heading) + len(annotated) + 2
    text = "\n\n".join(parts)
    return {"text": text, "sources": global_sources,
            "supports": all_supports,
            "audit": audit(text, all_supports, len(global_sources))}


def build_markdown(question, answer, sources, audit_info, mode, language):
    """Export an answer with its sources and citation check."""
    lang_name = {"en": "English", "roman": "Roman-Urdu",
                 "ur": "Urdu"}.get(language, "English")
    lines = [f"# Tahqeeq — {question.strip()}",
             "",
             f"_Mode: {mode} · Language: {lang_name}_",
             "",
             answer.strip(),
             "",
             "## Sources",
             ""]
    for i, s in enumerate(sources or [], 1):
        lines.append(f"{i}. [{s.get('title') or s.get('domain')}]({s.get('url')})")
    lines += ["",
              "## Citation check",
              f"- Sources retrieved: {audit_info.get('n_sources', 0)}",
              f"- Sources cited in the answer: {len(audit_info.get('cited', []))}",
              f"- Answer covered by retrieved sources: {audit_info.get('coverage', 0)}%",
              f"- Dangling citations: {audit_info.get('dangling') or 'none'}",
              f"- Retrieved but never cited: {audit_info.get('uncited') or 'none'}",
              "",
              "_Tahqeeq answers only from sources its live search returned. "
              "Re-check every number at the source before quoting it._"]
    return "\n".join(lines)
