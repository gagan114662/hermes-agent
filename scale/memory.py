"""
Hermes BrainMemory — gbrain-style hybrid search memory layer

Architecture borrowed from GBrain (github.com/garrytan/gbrain):
  - compiled_truth: current best synthesis, rewritten every 5 facts
  - timeline: append-only evidence trail
  - Hybrid search: keyword (tsvector) + vector (pgvector) + RRF fusion

Graceful degradation: if pgvector extension is not installed (migration 005
not yet run), falls back to flat tenant_memory LIMIT 40 query and skips
upsert. Warning logged once on first call.
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger("hermes.memory")

_OPENAI_AVAILABLE = False
try:
    import openai as _openai
    _OPENAI_AVAILABLE = True
except ImportError:
    pass


class BrainMemory:
    """
    Hybrid-search memory layer for Hermes workers.

    Usage:
        brain = BrainMemory(db_pool=pool)
        results = await brain.search(tenant_id, "B2B SaaS leads logistics", limit=8)
        await brain.upsert(tenant_id, "lead_research/b2b_saas", "Found 3 new leads at ...", "memory")
    """

    def __init__(self, db_pool, openai_api_key: Optional[str] = None):
        self.db = db_pool
        self._api_key = openai_api_key or os.getenv("OPENAI_API_KEY", "")
        self._pgvector_ok: Optional[bool] = None   # None = untested yet
        self._warned = False

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def search(self, tenant_id, query: str, limit: int = 8) -> list:
        """
        Hybrid search: keyword + vector + RRF fusion.
        Falls back to flat tenant_memory query if pgvector not available.
        """
        if not await self._pgvector_available():
            return await self._flat_fallback(tenant_id, limit)

        try:
            keyword_rows = await self._keyword_search(tenant_id, query, k=20)
            vector_rows = await self._vector_search(tenant_id, query, k=20)
            merged = self._rrf_merge(keyword_rows, vector_rows, limit=limit)
            return merged
        except Exception as e:
            logger.warning("BrainMemory.search error, falling back: %s", e)
            return await self._flat_fallback(tenant_id, limit)

    async def upsert(self, tenant_id, slug: str, new_fact: str, page_type: str = "memory"):
        """
        Compiled truth + timeline pattern.
        Appends new_fact to timeline; rewrites compiled_truth every 5 facts.
        """
        if not await self._pgvector_available():
            return

        try:
            now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M")

            # 1. Fetch existing page
            existing = await self.db.fetchrow(
                "SELECT compiled_truth, timeline FROM brain_pages WHERE tenant_id=$1 AND slug=$2",
                tenant_id, slug,
            )

            old_timeline = existing["timeline"] if existing else ""
            old_truth = existing["compiled_truth"] if existing else ""

            # 2. Append to timeline
            new_entry = f"- {now_str}: {new_fact}"
            timeline = (old_timeline + "\n" + new_entry).strip() if old_timeline else new_entry

            # 3. Count entries to decide whether to resynthesize
            entry_count = timeline.count("\n- ") + 1
            if not existing or entry_count % 5 == 0:
                compiled_truth = await self._synthesize(slug, timeline, old_truth)
            else:
                compiled_truth = old_truth if old_truth else new_fact

            # 4. Re-embed
            embed_input = (compiled_truth or "") + " " + timeline[:500]
            embedding = await self.embed_text(embed_input)

            # 5. Upsert
            if embedding is not None:
                await self.db.execute(
                    """INSERT INTO brain_pages
                       (tenant_id, slug, page_type, compiled_truth, timeline, embedding, updated_at)
                       VALUES ($1, $2, $3, $4, $5, $6::vector, NOW())
                       ON CONFLICT (tenant_id, slug) DO UPDATE
                       SET compiled_truth = EXCLUDED.compiled_truth,
                           timeline       = EXCLUDED.timeline,
                           embedding      = EXCLUDED.embedding,
                           updated_at     = NOW()""",
                    tenant_id, slug, page_type, compiled_truth, timeline,
                    "[" + ",".join(str(x) for x in embedding) + "]",
                )
            else:
                await self.db.execute(
                    """INSERT INTO brain_pages
                       (tenant_id, slug, page_type, compiled_truth, timeline, updated_at)
                       VALUES ($1, $2, $3, $4, $5, NOW())
                       ON CONFLICT (tenant_id, slug) DO UPDATE
                       SET compiled_truth = EXCLUDED.compiled_truth,
                           timeline       = EXCLUDED.timeline,
                           updated_at     = NOW()""",
                    tenant_id, slug, page_type, compiled_truth, timeline,
                )

        except Exception as e:
            logger.warning("BrainMemory.upsert error [%s]: %s", slug, e)

    async def embed_text(self, text: str) -> Optional[list]:
        """
        Embed text via OpenAI text-embedding-3-small.
        Returns None if OPENAI_API_KEY not set or call fails.
        """
        if not self._api_key or not _OPENAI_AVAILABLE:
            return None
        try:
            client = _openai.AsyncOpenAI(api_key=self._api_key)
            resp = await client.embeddings.create(
                model="text-embedding-3-small",
                input=text[:8000],  # model limit
            )
            return resp.data[0].embedding
        except Exception as e:
            logger.debug("embed_text failed: %s", e)
            return None

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    async def _pgvector_available(self) -> bool:
        """Check once whether the brain_pages table exists."""
        if self._pgvector_ok is not None:
            return self._pgvector_ok
        try:
            await self.db.fetchval(
                "SELECT 1 FROM brain_pages LIMIT 1"
            )
            self._pgvector_ok = True
        except Exception:
            self._pgvector_ok = False
            if not self._warned:
                logger.warning(
                    "pgvector/brain_pages not available — using flat memory fallback. "
                    "Run migration 005 to enable hybrid search."
                )
                self._warned = True
        return self._pgvector_ok

    async def _keyword_search(self, tenant_id, query: str, k: int = 20) -> list:
        """Full-text keyword search via tsvector."""
        rows = await self.db.fetch(
            """SELECT slug, compiled_truth, timeline,
                      ts_rank(search_vector, plainto_tsquery('english', $2)) as score
               FROM brain_pages
               WHERE tenant_id = $1
                 AND search_vector @@ plainto_tsquery('english', $2)
               ORDER BY score DESC
               LIMIT $3""",
            tenant_id, query, k,
        )
        return [dict(r) for r in rows]

    async def _vector_search(self, tenant_id, query: str, k: int = 20) -> list:
        """Approximate nearest-neighbour search via pgvector cosine distance."""
        embedding = await self.embed_text(query)
        if embedding is None:
            return []
        vec_literal = "[" + ",".join(str(x) for x in embedding) + "]"
        rows = await self.db.fetch(
            """SELECT slug, compiled_truth, timeline,
                      1 - (embedding <=> $2::vector) as score
               FROM brain_pages
               WHERE tenant_id = $1 AND embedding IS NOT NULL
               ORDER BY score DESC
               LIMIT $3""",
            tenant_id, vec_literal, k,
        )
        return [dict(r) for r in rows]

    def _rrf_merge(self, keyword_rows: list, vector_rows: list, limit: int = 8) -> list:
        """
        Reciprocal Rank Fusion: score = Σ 1/(60 + rank) across result lists.
        Deduplicates by slug, returns top `limit` results.
        """
        rrf_scores: dict = {}
        seen: dict = {}   # slug -> row dict

        for rank, row in enumerate(keyword_rows):
            slug = row["slug"]
            rrf_scores[slug] = rrf_scores.get(slug, 0.0) + 1.0 / (60 + rank)
            seen.setdefault(slug, row)

        for rank, row in enumerate(vector_rows):
            slug = row["slug"]
            rrf_scores[slug] = rrf_scores.get(slug, 0.0) + 1.0 / (60 + rank)
            seen.setdefault(slug, row)

        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        return [seen[slug] for slug, _ in ranked[:limit]]

    async def _flat_fallback(self, tenant_id, limit: int) -> list:
        """
        Fallback to flat tenant_memory table when pgvector is unavailable.
        Returns rows shaped like brain_pages (slug, compiled_truth, timeline).
        """
        try:
            rows = await self.db.fetch(
                """SELECT memory_type, content FROM tenant_memory
                   WHERE tenant_id = $1
                   ORDER BY updated_at DESC
                   LIMIT $2""",
                tenant_id, limit * 5,   # fetch more since no relevance filter
            )
            return [
                {
                    "slug": r["memory_type"],
                    "compiled_truth": r["content"],
                    "timeline": None,
                }
                for r in rows[:limit]
            ]
        except Exception as e:
            logger.warning("Flat fallback failed: %s", e)
            return []

    async def _synthesize(self, slug: str, timeline: str, old_truth: str) -> str:
        """
        Rewrite compiled_truth by synthesizing all timeline entries.
        Uses a small OpenRouter LLM call. Falls back to last timeline entry if unavailable.
        """
        or_key = os.getenv("OPENROUTER_API_KEY", "")
        if not or_key:
            # No LLM available — use most recent timeline entries as truth
            lines = [l for l in timeline.splitlines() if l.strip().startswith("-")]
            return "\n".join(lines[-10:]) if lines else timeline[:800]

        try:
            import sys as _sys
            import os as _os
            _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), ".."))
            from run_agent import AIAgent

            synth_prompt = (
                f"You are synthesizing memory for an AI worker. "
                f"Topic: {slug}\n\n"
                f"Timeline of observations (most recent at bottom):\n{timeline[-2000:]}\n\n"
                f"Previous summary: {old_truth[:500] if old_truth else 'None'}\n\n"
                f"Write a concise, factual summary (max 200 words) of the current best understanding "
                f"about this topic. Include key facts, patterns, and what the worker should remember "
                f"about this area. No preamble — just the summary."
            )
            agent = AIAgent(
                model="google/gemini-2.5-flash-preview",
                api_key=or_key,
                base_url="https://openrouter.ai/api/v1",
                provider="openrouter",
                max_iterations=1,
                quiet_mode=True,
                skip_memory=True,
                skip_context_files=True,
                enabled_toolsets=[],
            )
            result = agent.run_conversation(user_message=synth_prompt)
            new_truth = result.get("final_response", "").strip()
            return new_truth if new_truth else timeline[:800]
        except Exception as e:
            logger.debug("_synthesize failed for %s: %s", slug, e)
            return old_truth or timeline[:800]
