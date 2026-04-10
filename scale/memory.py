"""
Hermes BrainMemory — gbrain-style hybrid search memory layer

Architecture borrowed from GBrain (github.com/garrytan/gbrain):
  - compiled_truth: current best synthesis, rewritten every 5 facts
  - timeline: append-only evidence trail
  - Hybrid search: keyword (tsvector) + vector (pgvector) + RRF fusion

Intelligence additions (feature/brain-intelligence):
  - Multi-query expansion: expand query into 3 phrasings before searching
  - Entity detection: detect and ingest entities from any text
  - 60s query expansion cache to avoid redundant LLM calls

Graceful degradation: if pgvector extension is not installed (migration 005
not yet run), falls back to flat tenant_memory LIMIT 40 query and skips
upsert. Warning logged once on first call.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger("hermes.memory")

# Local embedding model — no API key, no cost, runs on CPU
# Loaded once and cached at module level so workers share the instance
_EMBED_MODEL = None
_EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"  # 384-dim, ~90MB
_EMBED_DIM = 384

def _get_embed_model():
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
            _EMBED_MODEL = SentenceTransformer(_EMBED_MODEL_NAME)
            logger.info("Loaded local embedding model: %s", _EMBED_MODEL_NAME)
        except ImportError:
            logger.warning(
                "sentence-transformers not installed — vector search disabled. "
                "Run: pip install sentence-transformers"
            )
    return _EMBED_MODEL


def _make_llm_agent():
    """Return an AIAgent configured for fast single-turn calls, or None if no key."""
    or_key = os.getenv("OPENROUTER_API_KEY", "")
    if not or_key:
        return None, None
    try:
        import sys as _sys, os as _os
        _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), ".."))
        from run_agent import AIAgent
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
        return agent, or_key
    except Exception:
        return None, None


class BrainMemory:
    """
    Hybrid-search memory layer for Hermes workers.

    Usage:
        brain = BrainMemory(db_pool=pool)
        results = await brain.search(tenant_id, "B2B SaaS leads logistics", limit=8)
        await brain.upsert(tenant_id, "lead_research/b2b_saas", "Found 3 new leads at ...", "memory")
        count = await brain.detect_and_ingest(tenant_id, text, "task summary")
    """

    def __init__(self, db_pool):
        self.db = db_pool
        self._pgvector_ok: Optional[bool] = None   # None = untested yet
        self._warned = False
        # Query expansion cache: query_str -> (timestamp, [expansions])
        self._expansion_cache: dict = {}
        self._expansion_ttl = 60  # seconds

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def search(self, tenant_id, query: str, limit: int = 8) -> list:
        """
        Multi-query hybrid search: expands query into 4 phrasings, runs keyword
        + vector search for each in parallel, fuses via RRF across all result sets.
        Falls back to flat tenant_memory query if pgvector not available.
        """
        if not await self._pgvector_available():
            return await self._flat_fallback(tenant_id, limit)

        try:
            queries = await self._expand_query(query)  # [original] + up to 3 expansions

            # Run all (keyword + vector) searches in parallel across all queries
            search_tasks = [
                self._search_one_query(tenant_id, q, k=20) for q in queries
            ]
            result_sets = await asyncio.gather(*search_tasks, return_exceptions=True)

            # Filter out exceptions, keep successful result sets
            valid_sets = [r for r in result_sets if isinstance(r, list)]
            if not valid_sets:
                return await self._flat_fallback(tenant_id, limit)

            merged = self._rrf_merge_multi(valid_sets, limit=limit)
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
            embedding = self.embed_text(embed_input)

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

    async def detect_and_ingest(self, tenant_id, text: str, source_summary: str) -> int:
        """
        Detect entities in text and upsert a brain page for each.
        Returns count of entities ingested. Never raises — all exceptions return 0.
        """
        try:
            agent, _ = _make_llm_agent()
            if agent is None:
                return 0

            prompt = (
                "Extract entities from this text. Return JSON only, no explanation:\n"
                '{"entities": [\n'
                '  {"slug": "companies/acme-corp", "type": "company", "name": "Acme Corp",\n'
                '   "fact": "one sentence about what was learned"}\n'
                "]}\n"
                "Only include entities where something concrete was learned. "
                "Max 5 entities. Types: company, person, market, product, other.\n\n"
                f"Text: {text[:1500]}"
            )

            raw = agent.run_conversation(user_message=prompt).get("final_response", "").strip()

            # Strip markdown fences
            if raw.startswith("```"):
                import re as _re
                raw = _re.sub(r"^```[a-z]*\n?", "", raw)
                raw = _re.sub(r"\n?```$", "", raw.rstrip())

            parsed = json.loads(raw)
            entities = parsed.get("entities", [])[:5]

            ingested = 0
            for ent in entities:
                slug = ent.get("slug", "").strip()
                fact = ent.get("fact", "").strip()
                etype = ent.get("type", "other")
                if slug and fact:
                    await self.upsert(tenant_id, slug, fact, page_type=etype)
                    ingested += 1

            if ingested:
                logger.info(
                    "Entity detection: ingested %d entities from '%s'",
                    ingested, source_summary[:60],
                )
            return ingested

        except Exception as e:
            logger.debug("detect_and_ingest failed: %s", e)
            return 0

    def embed_text(self, text: str) -> Optional[list]:
        """
        Embed text using local sentence-transformers model (no API key needed).
        Returns None if sentence-transformers is not installed.
        """
        model = _get_embed_model()
        if model is None:
            return None
        try:
            vec = model.encode(text[:2048], normalize_embeddings=True)
            return vec.tolist()
        except Exception as e:
            logger.debug("embed_text failed: %s", e)
            return None

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    async def _expand_query(self, query: str) -> list:
        """
        Expand query into [original] + up to 3 alternative phrasings via LLM.
        Results cached for 60s by query string.
        Falls back to [query] only if LLM unavailable or call fails.
        """
        # Check cache
        now = time.monotonic()
        cached = self._expansion_cache.get(query)
        if cached and (now - cached[0]) < self._expansion_ttl:
            return cached[1]

        queries = [query]  # always include original

        agent, _ = _make_llm_agent()
        if agent is None:
            return queries

        try:
            prompt = (
                f"Given this search query: '{query}'\n"
                "Return 3 alternative phrasings that would find related information.\n"
                "Return as JSON array of strings. Be concise.\n"
                'Example: ["phrasing 1", "phrasing 2", "phrasing 3"]'
            )
            raw = agent.run_conversation(user_message=prompt).get("final_response", "").strip()

            if raw.startswith("```"):
                import re as _re
                raw = _re.sub(r"^```[a-z]*\n?", "", raw)
                raw = _re.sub(r"\n?```$", "", raw.rstrip())

            expansions = json.loads(raw)
            if isinstance(expansions, list):
                queries = [query] + [str(e) for e in expansions[:3] if e]

        except Exception as e:
            logger.debug("Query expansion failed, using original: %s", e)

        # Cache result
        self._expansion_cache[query] = (now, queries)
        # Evict stale entries to prevent unbounded growth
        if len(self._expansion_cache) > 200:
            cutoff = now - self._expansion_ttl
            self._expansion_cache = {
                k: v for k, v in self._expansion_cache.items() if v[0] > cutoff
            }

        return queries

    async def _search_one_query(self, tenant_id, query: str, k: int = 20) -> list:
        """Run keyword + vector search for a single query, return RRF-merged list."""
        keyword_rows, vector_rows = await asyncio.gather(
            self._keyword_search(tenant_id, query, k=k),
            self._vector_search(tenant_id, query, k=k),
        )
        return self._rrf_merge_multi([keyword_rows, vector_rows], limit=k)

    async def _pgvector_available(self) -> bool:
        """Check once whether the brain_pages table exists."""
        if self._pgvector_ok is not None:
            return self._pgvector_ok
        try:
            await self.db.fetchval("SELECT 1 FROM brain_pages LIMIT 1")
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
        embedding = self.embed_text(query)
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

    def _rrf_merge_multi(self, result_sets: list, limit: int = 8) -> list:
        """
        Reciprocal Rank Fusion across N result sets.
        score = Σ 1/(60 + rank) for each appearance across all sets.
        Deduplicates by slug, returns top `limit` results.
        """
        rrf_scores: dict = {}
        seen: dict = {}  # slug -> row dict (first occurrence wins)

        for result_set in result_sets:
            for rank, row in enumerate(result_set):
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
                tenant_id, limit * 5,
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
        Rewrite compiled_truth by synthesizing all timeline entries via LLM.
        Falls back to recent timeline entries if no LLM available.
        """
        agent, _ = _make_llm_agent()
        if agent is None:
            lines = [l for l in timeline.splitlines() if l.strip().startswith("-")]
            return "\n".join(lines[-10:]) if lines else timeline[:800]

        try:
            synth_prompt = (
                f"You are synthesizing memory for an AI worker. "
                f"Topic: {slug}\n\n"
                f"Timeline of observations (most recent at bottom):\n{timeline[-2000:]}\n\n"
                f"Previous summary: {old_truth[:500] if old_truth else 'None'}\n\n"
                f"Write a concise, factual summary (max 200 words) of the current best understanding "
                f"about this topic. Include key facts, patterns, and what the worker should remember "
                f"about this area. No preamble — just the summary."
            )
            result = agent.run_conversation(user_message=synth_prompt)
            new_truth = result.get("final_response", "").strip()
            return new_truth if new_truth else timeline[:800]
        except Exception as e:
            logger.debug("_synthesize failed for %s: %s", slug, e)
            return old_truth or timeline[:800]
