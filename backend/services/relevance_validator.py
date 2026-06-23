"""
relevance_validator.py — Production-Grade Query Understanding Pipeline.

Pipeline:
  1. Text Normalization  (word-numbers, spelling, punctuation)
  2. Intent Detection    (SHOW_DATA, AGGREGATION, VISUALIZATION, METADATA)
  3. Synonym Expansion   (rows/records/entries, highest/best/top, …)
  4. Fast pattern ALLOW  (dataset-analysis patterns after normalization)
  5. Fast pattern REJECT (clearly off-topic patterns)
  6. Hybrid scoring      (intent 40% + semantic 30% + schema 20% + entity 10%)
  7. LLM fallback        (only for uncertain zone 0.40–0.60)

Returns RelevanceResult(relevant, score, reason, suggestions).
Logs every decision to  backend/data/logs/query_engine.log
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

from groq import Groq

from backend.config.settings import GROQ_API_KEY, GROQ_MODEL, LOGS_DIR

# ── Logger ───────────────────────────────────────────────────────────────────
_rel_logger = logging.getLogger("query_engine")
if not _rel_logger.handlers:
    _rel_logger.setLevel(logging.INFO)
    _fh = logging.FileHandler(
        os.path.join(LOGS_DIR, "query_engine.log"), encoding="utf-8"
    )
    _fh.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s",
                          datefmt="%Y-%m-%d %H:%M:%S")
    )
    _rel_logger.addHandler(_fh)
    _rel_logger.propagate = False

# ── Thresholds ────────────────────────────────────────────────────────────────
_HARD_REJECT  = 0.20   # below → reject immediately
_LLM_LOW      = 0.40   # uncertain zone start
_LLM_HIGH     = 0.60   # uncertain zone end
_HARD_ACCEPT  = 0.60   # at or above → accept immediately

# ── Groq client ──────────────────────────────────────────────────────────────
_groq = Groq(api_key=GROQ_API_KEY)

# ── Step 1: Word-number normalization map ─────────────────────────────────────
_WORD_NUMBERS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20", "thirty": "30",
    "forty": "40", "fifty": "50", "hundred": "100", "thousand": "1000",
}

# ── Step 2: Intent categories ─────────────────────────────────────────────────
_INTENT_SHOW_DATA = {
    "show", "display", "give", "send", "list", "print", "fetch", "get",
    "view", "see", "present", "output", "return", "render",
    # common phrases after normalization
    "first", "last", "top", "bottom", "sample", "preview", "example",
    "rows", "row", "records", "record", "entries", "entry", "data",
    "observations", "observation", "instances", "instance",
}

_INTENT_AGGREGATION = {
    "average", "avg", "mean", "sum", "total", "count", "max", "min",
    "maximum", "minimum", "highest", "lowest", "best", "worst",
    "largest", "smallest", "most", "least", "top", "bottom",
    "median", "mode", "std", "variance", "range", "percentage", "percent",
    "proportion", "ratio", "rate", "growth", "trend",
}

_INTENT_VISUALIZATION = {
    "plot", "chart", "graph", "visualize", "visualise", "draw", "create",
    "bar", "pie", "line", "scatter", "column",
}

_INTENT_METADATA = {
    "schema", "columns", "column", "describe", "description", "fields",
    "field", "datatypes", "datatype", "metadata", "structure", "info",
}

# ── Step 3: Synonym engine ────────────────────────────────────────────────────
# Maps synonym → canonical form  (used during normalization)
_SYNONYMS: dict[str, str] = {
    # row synonyms
    "records": "rows", "record": "rows", "entries": "rows", "entry": "rows",
    "observations": "rows", "observation": "rows", "instances": "rows",
    "instance": "rows", "samples": "rows", "examples": "rows", "example": "rows",
    "items": "rows", "item": "rows", "lines": "rows", "line": "rows",
    # highest synonyms
    "best": "highest", "top": "highest", "maximum": "highest",
    "largest": "highest", "greatest": "highest", "most": "highest",
    "leading": "highest", "peak": "highest",
    # lowest synonyms
    "worst": "lowest", "bottom": "lowest", "minimum": "lowest",
    "smallest": "lowest", "least": "lowest", "fewest": "lowest",
    # average synonyms
    "mean": "average", "avg": "average",
    # count synonyms
    "how many": "count", "total": "count", "number of": "count",
    # show synonyms
    "display": "show", "give": "show", "send": "show", "fetch": "show",
    "get": "show", "view": "show", "list": "show", "print": "show",
    "provide": "show", "output": "show", "return": "show",
}


# ── Result type ──────────────────────────────────────────────────────────────
@dataclass
class RelevanceResult:
    relevant:    bool
    score:       float
    reason:      str
    intent:      str        = "unknown"
    suggestions: list[str] = field(default_factory=list)


# ── Stopwords (intentionally NOT including action words like show/give/display)
_STOPS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "on", "at", "by", "for", "with", "about",
    "from", "into", "through", "during", "before", "after", "above",
    "below", "between", "out", "off", "over", "under", "then", "once",
    "here", "there", "when", "where", "why", "how", "all", "both", "each",
    "more", "other", "such", "no", "nor", "not", "only", "same", "so",
    "than", "too", "very", "just", "me", "my", "myself", "we", "our",
    "you", "your", "he", "him", "his", "she", "her", "it", "its",
    "they", "them", "their", "what", "which", "who", "this", "that",
    "these", "those", "i", "and", "or", "but", "if", "as", "up", "any",
    "make", "go", "let", "please",
}

# ── Off-topic patterns (applied AFTER normalization & intent check) ───────────
_OFFTOPIC_PATTERNS = [
    r"\bjoke\b", r"\bfunny\b", r"\blaugh\b",
    r"\bweather\b", r"\bforecast\b",
    r"\bprime minister\b", r"\belection\b", r"\bpolitics\b",
    r"\bcricket score\b", r"\bipl\b",
    r"\brecipe\b", r"\bcooking\b",
    r"\bwrite (a |an )?(poem|story|essay|code|program|function)\b",
    r"\btranslate\b",
    r"\bstock price\b", r"\bcrypto\b", r"\bbitcoin\b",
    r"\bnews\b",
    r"\bmovie\b", r"\bfilm\b", r"\bsong\b", r"\bmusic\b",
    r"\bchatgpt\b", r"\bopenai\b",
    r"\bsolve (this )?(math|equation|problem)\b",
    r"\btell me a\b",
    r"\bwho is the\b",
    r"\bwhat is \w+coin\b",
]

# ── Dataset patterns (applied on NORMALIZED text — word-numbers already digits)
_DATASET_PATTERNS = [
    # show/display/give N rows — works after word-number normalization
    r"\b(show|display|give|send|fetch|get|list|print|view|see)\b",
    r"\b(top|bottom|first|last)\s*(\d+)?\b",
    r"\b(sample|preview|example|examples)\b",
    r"\b(count|sum|avg|average|mean|max|min|total|highest|lowest|best|worst)\b",
    r"\b(filter|where|group\s+by|order\s+by|sort|rank)\b",
    r"\b(distribution|trend|pattern|outlier|correlation|insight)\b",
    r"\b(missing|null|duplicate|unique|distinct|blank|empty)\b",
    r"\b(row|rows|record|records|entry|entries|column|columns|field|fields)\b",
    r"\b(dataset|table|data|database)\b",
    r"\b(compare|versus|vs\.?|between)\b",
    r"\b(visuali[sz]e|chart|graph|plot|scatter|bar|pie|column)\b",
    r"\b(percentage|percent|proportion|share|ratio)\b",
    r"\b(year|month|date|quarter|period)\b",
    r"\b\d+\s*(rows?|records?|entries|items?)\b",
]


# ── Step 1: Text Normalization ───────────────────────────────────────────────

def _normalize(text: str) -> str:
    """
    Normalize user input:
    - lowercase
    - replace word-numbers with digits
    - apply synonym expansion
    - strip extra punctuation/whitespace
    """
    t = text.lower().strip()
    # Remove punctuation except spaces and digits
    t = re.sub(r"[^\w\s]", " ", t)
    # Word-number substitution (whole words only)
    for word, digit in _WORD_NUMBERS.items():
        t = re.sub(rf"\b{word}\b", digit, t)
    # Synonym expansion (multi-word first, then single)
    for syn, canonical in sorted(_SYNONYMS.items(), key=lambda x: -len(x[0])):
        t = re.sub(rf"\b{re.escape(syn)}\b", canonical, t)
    # Collapse whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t


# ── Step 2: Intent Detection ──────────────────────────────────────────────────

def _detect_intent(normalized: str) -> str:
    """Return the dominant intent of a normalized query string."""
    tokens = set(normalized.split())
    scores = {
        "SHOW_DATA":      len(tokens & _INTENT_SHOW_DATA),
        "AGGREGATION":    len(tokens & _INTENT_AGGREGATION),
        "VISUALIZATION":  len(tokens & _INTENT_VISUALIZATION),
        "METADATA":       len(tokens & _INTENT_METADATA),
    }
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "UNKNOWN"


# ── Hybrid scoring helpers ────────────────────────────────────────────────────

def _intent_score(intent: str) -> float:
    """40% weight: any recognized dataset intent = 1.0, UNKNOWN = 0.0."""
    return 1.0 if intent != "UNKNOWN" else 0.0


def _entity_score(normalized: str, schema: str) -> float:
    """10% weight: fraction of query tokens that match schema column tokens."""
    col_tokens: set[str] = set()
    for line in schema.splitlines():
        m = re.match(r'\s*["\']?([A-Za-z_][A-Za-z0-9_ ]*)["\']?\s+\w', line)
        if m:
            for tok in re.findall(r"[a-z0-9]+", m.group(1).lower()):
                col_tokens.add(tok)
    if not col_tokens:
        return 0.0
    query_tokens = set(re.findall(r"[a-z0-9]+", normalized))
    overlap = query_tokens & col_tokens
    return min(1.0, len(overlap) / max(1, len(query_tokens)))


def _tokenise(text: str) -> dict[str, float]:
    """Lowercase, strip punctuation, remove stopwords → TF dict."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    tf: dict[str, float] = {}
    for w in words:
        if w not in _STOPS and len(w) > 1:
            tf[w] = tf.get(w, 0) + 1
    if tf:
        total = sum(tf.values())
        tf = {k: v / total for k, v in tf.items()}
    return tf


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine similarity between two TF dicts."""
    if not a or not b:
        return 0.0
    dot  = sum(a.get(k, 0) * v for k, v in b.items())
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _build_context_tokens(schema: str) -> dict[str, float]:
    """Build a TF vector from schema. Also inject universal data vocabulary."""
    col_names: list[str] = []
    for line in schema.splitlines():
        m = re.match(r'\s*["\']?([A-Za-z_][A-Za-z0-9_ ]*)["\']?\s+\w', line)
        if m:
            col_names.append(m.group(1).lower().replace("_", " ").replace("-", " "))

    # Universal dataset vocabulary always present in context
    universal = (
        "row rows record records data show display average count sum total "
        "highest lowest first last top bottom sample preview filter sort group "
        "visualize chart graph plot schema column field missing null duplicate"
    )
    boosted = " ".join(col_names * 5) + " " + schema + " " + universal
    return _tokenise(boosted)


def _generate_suggestions(schema: str, n: int = 5) -> list[str]:
    """
    Produce up to n example questions derived from the actual column names.
    Pattern: mix of aggregation, filter, top-N, comparison, visualisation.
    """
    col_names: list[str] = []
    for line in schema.splitlines():
        m = re.match(r'\s*["\']?([A-Za-z_][A-Za-z0-9_ ]*)["\']?\s+\w', line)
        if m:
            name = m.group(1)
            col_names.append(name)

    if not col_names:
        return [
            "Show top 10 rows",
            "Count total records",
            "Show missing values",
            "Describe the dataset schema",
            "Visualize the data",
        ]

    suggestions: list[str] = []
    numeric_hints = {"count", "sum", "total", "amount", "price", "sales",
                     "revenue", "qty", "quantity", "age", "score", "rate",
                     "value", "num", "number", "confirmed", "deaths",
                     "recovered", "cases", "population", "salary", "profit"}

    num_cols  = [c for c in col_names if any(h in c.lower() for h in numeric_hints)]
    cat_cols  = [c for c in col_names if c not in num_cols]
    date_cols = [c for c in col_names
                 if any(h in c.lower() for h in {"date", "time", "year", "month", "day"})]

    # Always safe suggestions
    suggestions.append(f"Show top 10 rows")
    suggestions.append(f"Count total records")

    if cat_cols and num_cols:
        suggestions.append(f"Which {cat_cols[0]} has the highest {num_cols[0]}?")
        suggestions.append(f"Compare {num_cols[0]} across {cat_cols[0]}")
    elif cat_cols:
        suggestions.append(f"Show all unique values in {cat_cols[0]}")
        suggestions.append(f"Count records by {cat_cols[0]}")
    elif num_cols:
        suggestions.append(f"Show average {num_cols[0]}")
        suggestions.append(f"Find rows with maximum {num_cols[0]}")

    if date_cols and num_cols:
        suggestions.append(f"Show {num_cols[0]} trend over {date_cols[0]}")
    elif num_cols:
        suggestions.append(f"Visualize {num_cols[0]} distribution")

    if len(col_names) >= 2:
        suggestions.append(f"Show missing values report")

    return suggestions[:n]


def _llm_check(question: str, schema: str) -> tuple[bool, str]:
    """
    Step 7: LLM fallback for uncertain zone (score 0.40–0.60).
    Asks Groq: can this be answered from the dataset?
    Falls back to True on any exception — never block valid queries.
    """
    prompt = (
        "You are a dataset relevance classifier for a production analytics platform.\n\n"
        "DATASET SCHEMA:\n"
        f"{schema}\n\n"
        "USER QUESTION:\n"
        f"{question}\n\n"
        "Determine if this question can be answered using the uploaded dataset.\n\n"
        "Mark as RELEVANT if:\n"
        "- Question asks to show, display, fetch, list rows or records (even without column names)\n"
        "- Question asks for statistics, counts, averages, top/bottom N records\n"
        "- Question references columns, trends, filters, aggregations, or visualizations\n"
        "- Question is a conversational follow-up (show more, next, filter that, etc.)\n\n"
        "Mark as IRRELEVANT only if:\n"
        "- Completely unrelated to data (jokes, weather, sports, coding, news, etc.)\n\n"
        "Return ONLY valid JSON: {\"relevant\": true, \"reason\": \"one sentence\"}"
    )
    try:
        resp = _groq.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": "You are a relevance classifier. Return only JSON."},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            max_tokens=80,
        )
        obj = json.loads(resp.choices[0].message.content.strip())
        return bool(obj.get("relevant", True)), str(obj.get("reason", ""))
    except Exception as exc:
        _rel_logger.warning("LLM check failed (%s) — defaulting relevant=True", exc)
        return True, "LLM unavailable — allowed by default"


# ── Public API ────────────────────────────────────────────────────────────────

class RelevanceValidator:
    """
    Production-grade query understanding pipeline.

    Steps: Normalize → Intent → Pattern ALLOW → Pattern REJECT
           → Hybrid Score → LLM fallback (uncertain zone only)
    """

    def validate(self, question: str, schema: str,
                 conversation_history: list | None = None) -> RelevanceResult:
        t0 = time.monotonic()
        original = question.strip()

        # ── Step 1: Normalize ────────────────────────────────────────────────
        normalized = _normalize(original)

        # ── Step 2: Intent Detection ─────────────────────────────────────────
        intent = _detect_intent(normalized)

        # ── Step 3: Conversational follow-up — always allow ──────────────────
        follow_ups = {
            "yes", "ok", "okay", "sure", "next", "more", "show more",
            "continue", "go on", "and", "also", "what about", "explain",
            "show next", "next 10", "next page",
        }
        if normalized in follow_ups or len(normalized.split()) <= 2 and intent != "UNKNOWN":
            elapsed = (time.monotonic() - t0) * 1000
            _rel_logger.info(
                "ALLOW | follow-up | intent=%s | %.1fms | original=%r | normalized=%r",
                intent, elapsed, original[:120], normalized[:120],
            )
            return RelevanceResult(relevant=True, score=1.0, intent=intent,
                                   reason="Conversational follow-up.")

        # ── Step 4: Intent-based fast ALLOW (SHOW_DATA always relevant) ──────
        if intent == "SHOW_DATA":
            elapsed = (time.monotonic() - t0) * 1000
            _rel_logger.info(
                "ALLOW | intent=SHOW_DATA | %.1fms | original=%r | normalized=%r",
                elapsed, original[:120], normalized[:120],
            )
            return RelevanceResult(relevant=True, score=1.0, intent=intent,
                                   reason="Dataset display / retrieval intent detected.")

        # ── Step 5: Dataset pattern fast ALLOW (on normalized text) ──────────
        for pat in _DATASET_PATTERNS:
            if re.search(pat, normalized):
                elapsed = (time.monotonic() - t0) * 1000
                _rel_logger.info(
                    "ALLOW | pattern | intent=%s | %.1fms | original=%r | normalized=%r",
                    intent, elapsed, original[:120], normalized[:120],
                )
                return RelevanceResult(relevant=True, score=1.0, intent=intent,
                                       reason="Matches dataset analysis pattern.")

        # ── Step 6: Off-topic pattern fast REJECT ────────────────────────────
        # Only reject if intent is UNKNOWN (no dataset intent detected)
        if intent == "UNKNOWN":
            for pat in _OFFTOPIC_PATTERNS:
                if re.search(pat, normalized):
                    sugg = _generate_suggestions(schema)
                    elapsed = (time.monotonic() - t0) * 1000
                    _rel_logger.info(
                        "REJECT | off-topic pattern | %.1fms | original=%r | normalized=%r",
                        elapsed, original[:120], normalized[:120],
                    )
                    return RelevanceResult(
                        relevant=False, score=0.0, intent=intent,
                        reason="This question is not related to the uploaded dataset.",
                        suggestions=sugg,
                    )

        # ── Step 7: Hybrid Scoring ────────────────────────────────────────────
        # intent_score (40%) + semantic_score (30%) + schema_match (20%) + entity (10%)
        i_score = _intent_score(intent)                           # 0.0 or 1.0
        ctx_tokens = _build_context_tokens(schema)
        q_tokens   = _tokenise(normalized)
        sem_score  = _cosine(q_tokens, ctx_tokens)                # 0.0–1.0
        e_score    = _entity_score(normalized, schema)            # 0.0–1.0
        # schema_match: does query overlap with schema text at all?
        schema_tokens = _tokenise(schema)
        s_score    = min(1.0, _cosine(q_tokens, schema_tokens) * 3)  # boosted

        hybrid = (0.40 * i_score) + (0.30 * sem_score) + (0.20 * s_score) + (0.10 * e_score)

        elapsed = (time.monotonic() - t0) * 1000
        _rel_logger.info(
            "SCORE | intent=%s(%.2f) sem=%.3f schema=%.3f entity=%.3f hybrid=%.3f "
            "| %.1fms | original=%r | normalized=%r",
            intent, i_score, sem_score, s_score, e_score, hybrid,
            elapsed, original[:120], normalized[:120],
        )

        # Hard accept
        if hybrid >= _HARD_ACCEPT:
            return RelevanceResult(relevant=True, score=hybrid, intent=intent,
                                   reason="High relevance score.")

        # Hard reject
        if hybrid < _HARD_REJECT:
            sugg = _generate_suggestions(schema)
            return RelevanceResult(
                relevant=False, score=hybrid, intent=intent,
                reason="This question is not related to the uploaded dataset.",
                suggestions=sugg,
            )

        # ── Step 8: LLM fallback (uncertain zone 0.20–0.60) ──────────────────
        relevant, reason = _llm_check(original, schema)
        elapsed = (time.monotonic() - t0) * 1000
        _rel_logger.info(
            "%s | llm | hybrid=%.3f | %.1fms | %s | original=%r",
            "ALLOW" if relevant else "REJECT",
            hybrid, elapsed, reason, original[:120],
        )

        if relevant:
            return RelevanceResult(relevant=True, score=hybrid, intent=intent,
                                   reason=reason)

        sugg = _generate_suggestions(schema)
        return RelevanceResult(
            relevant=False, score=hybrid, intent=intent,
            reason="This question is not related to the uploaded dataset.",
            suggestions=sugg,
        )
