"""Event category and place classification: native mapping -> Claude Haiku (cached) -> keywords."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from .config import Config
from .model import Event
from .normalize import norm

log = logging.getLogger(__name__)

ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL") or "claude-haiku-4-5"
OPENAI_MODEL = os.environ.get("OPENAI_MODEL") or "gpt-6-luna"   # empty env (CI vars) = default
BATCH = 25


def provider() -> str | None:
    """LLM provider: LLM_PROVIDER env (openai|anthropic) or auto-detect from available keys."""
    forced = os.environ.get("LLM_PROVIDER")
    if forced in ("openai", "anthropic"):
        return forced
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return None


class Classification(BaseModel):
    id: str
    category: str
    place: str | None
    confidence: float


class ClassifyBatch(BaseModel):
    results: list[Classification]


def load_cache(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def map_native(native: str | None, cmap: dict[str, str]) -> str | None:
    if not native:
        return None
    keys = sorted(cmap, key=len, reverse=True)
    for part in norm(native).split(","):
        part = part.strip()
        for k in keys:
            if k in part:
                return cmap[k]
    return None


def keyword_category(cfg: Config, *texts: str | None) -> str | None:
    blob = " ".join(norm(t) for t in texts if t)
    for c in cfg.categories:
        for kw in c.keywords:
            if re.search(r"(?<![a-z0-9])" + re.escape(norm(kw)), blob):
                return c.slug
    return None


def _system_prompt(cfg: Config) -> str:
    cats = "\n".join(f"- {c.slug}: {c.label}" for c in cfg.categories)
    places = "\n".join(f"- {p.name}" + (f" (také: {', '.join(p.aliases)})" if p.aliases else "")
                       for p in cfg.places)
    return (
        "Jsi klasifikátor kulturních a společenských akcí v Podkrkonoší (okolí obce Mostek, okres Trutnov).\n"
        "Pro každou položku vrať `category` přesně z tohoto seznamu slugů:\n"
        f"{cats}\n\n"
        "A `place` = název obce přesně ze seznamu níže, kde se akce koná (podle místa, venue, názvu nebo popisu). "
        "Pokud se akce nekoná v žádné z těchto obcí nebo to nelze určit, vrať null.\n"
        f"{places}\n\n"
        "`confidence` je 0–1. Vrať pouze strukturovaný výstup."
    )


def _call_anthropic(cfg: Config, items: list[dict]) -> list[Classification]:
    import anthropic

    client = anthropic.Anthropic()
    resp = client.messages.parse(
        model=ANTHROPIC_MODEL,
        max_tokens=4096,
        system=[{"type": "text", "text": _system_prompt(cfg), "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": json.dumps(items, ensure_ascii=False)}],
        output_format=ClassifyBatch,
    )
    return resp.parsed_output.results if resp.parsed_output else []


def _call_openai(cfg: Config, items: list[dict]) -> list[Classification]:
    from openai import OpenAI

    client = OpenAI()
    resp = client.chat.completions.parse(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": _system_prompt(cfg)},
            {"role": "user", "content": json.dumps(items, ensure_ascii=False)},
        ],
        response_format=ClassifyBatch,
    )
    parsed = resp.choices[0].message.parsed
    return parsed.results if parsed else []


def _call_llm(cfg: Config, items: list[dict]) -> list[Classification]:
    prov = provider()
    if prov == "openai":
        return _call_openai(cfg, items)
    if prov == "anthropic":
        return _call_anthropic(cfg, items)
    raise RuntimeError("no LLM provider configured (set OPENAI_API_KEY or ANTHROPIC_API_KEY)")


def model_name() -> str:
    return {"openai": OPENAI_MODEL, "anthropic": ANTHROPIC_MODEL}.get(provider() or "", "none")


def classify(events: list[Event], cfg: Config, cache: dict, use_llm: bool = True) -> dict:
    """Fill `category` (and `place` where missing) on events in place. Returns updated cache."""
    slugs = set(cfg.category_slugs)
    place_names = {p.name for p in cfg.places}

    for e in events:
        if not e.category:
            e.category = map_native(e.native_category, cfg.category_map)

    pending = [e for e in events if (e.category in (None, "jine") or e.place is None)
               and e.source_id not in cache]
    llm_ok = use_llm and provider() is not None
    if pending and not llm_ok:
        log.info("LLM classification skipped (%d pending, use_llm=%s, provider=%s)",
                 len(pending), use_llm, provider())
    if pending and llm_ok:
        by_id = {e.source_id: e for e in pending}
        ids = list(by_id)
        for i in range(0, len(ids), BATCH):
            chunk = [by_id[x] for x in ids[i:i + BATCH]]
            items = [{
                "id": e.source_id, "title": e.title, "venue": e.venue, "place_raw": e.place_raw,
                "native_category": e.native_category, "description": (e.description or "")[:300],
            } for e in chunk]
            try:
                results = _call_llm(cfg, items)
            except Exception as ex:  # noqa: BLE001
                log.warning("LLM classification failed: %s", ex)
                break
            now = datetime.now(UTC).isoformat(timespec="seconds")
            for r in results:
                if r.id not in by_id:
                    continue
                cache[r.id] = {
                    "category": r.category if r.category in slugs else None,
                    "place": r.place if r.place in place_names else None,
                    "confidence": round(float(r.confidence), 2),
                    "needs_review": float(r.confidence) < 0.5,
                    "model": model_name(), "ts": now,
                }
            log.info("LLM (%s) classified %d/%d events", model_name(), len(results), len(chunk))

    for e in events:
        c = cache.get(e.source_id)
        if c:
            if e.category in (None, "jine") and c.get("category") and not c.get("needs_review"):
                e.category = c["category"]
            if e.place is None and c.get("place"):
                e.place = c["place"]
            e.needs_review = bool(c.get("needs_review"))
        if e.category in (None, "jine"):
            e.category = (keyword_category(cfg, e.title, e.native_category)
                          or keyword_category(cfg, e.venue) or e.category or "jine")
    return cache
