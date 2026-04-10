# Hermes Self-Grading System — Claude Code Brief

Branch off: `feature/ai-sdr-workers`
New branch: `feature/self-grading`
Files to touch: `scale/worker.py`, `scale/migrations/002_add_quality_scores.sql`, `scale/gateway.py`

---

## The Problem

Hermes currently saves a "learning" sentence after each autonomous task — but it's vibes, not data.
There's no number. No comparison. No way to know if the worker is actually improving.

Karpathy's autoresearch shows the right model:
- Every experiment produces `val_bpb` (a number)
- Agent compares new score to previous score
- Keeps improvements, learns from regressions
- Over 100 experiments overnight it measurably gets better

This brief makes Hermes work the same way.

---

## Step 1: DB Migration — `scale/migrations/002_add_quality_scores.sql`

```sql
-- Add quality_score to worker_actions
ALTER TABLE worker_actions
    ADD COLUMN IF NOT EXISTS quality_score INTEGER,        -- 0-100
    ADD COLUMN IF NOT EXISTS task_type TEXT,               -- 'lead_research' | 'content' | 'outreach' | 'research' | 'ops'
    ADD COLUMN IF NOT EXISTS grader_reasoning TEXT;        -- why the score was given

-- Index for fetching historical scores by task type
CREATE INDEX IF NOT EXISTS idx_worker_actions_type_score
    ON worker_actions(tenant_id, task_type, created_at DESC);
```

---

## Step 2: Grading Rubrics

Add this constant near the top of `scale/worker.py`, below the `_DECISION_PROMPT`:

```python
_TASK_TYPE_PROMPT = """You are classifying a task.

Task: {task}

Classify into exactly one of these types (respond with just the type keyword, nothing else):
- lead_research   (finding leads, prospects, companies, contacts)
- content         (writing posts, articles, newsletters, copy, social media)
- outreach        (drafting emails, messages, pitches, follow-ups)
- research        (competitor analysis, market research, news monitoring, intel)
- ops             (scheduling, organizing, summarizing, reporting, admin)
- other           (anything that doesn't fit above)
"""

_GRADER_PROMPTS = {
    "lead_research": """You are grading an AI worker's lead research output.

Task given: {task}
Output produced: {output}

Score on these dimensions (each 0-25 points):
1. Quantity — how many leads/companies found vs what was asked
2. Relevance — how well do they match the stated criteria
3. Completeness — how much useful info per lead (name, company, signal, contact)
4. Actionability — can a human immediately act on this without more research

Respond in JSON only:
{{
  "quantity_score": 0-25,
  "relevance_score": 0-25,
  "completeness_score": 0-25,
  "actionability_score": 0-25,
  "total": 0-100,
  "best_thing": "one specific thing done well",
  "biggest_gap": "one specific thing missing or weak",
  "beat_this_next_time": "one concrete instruction for how to score higher next time"
}}""",

    "content": """You are grading an AI worker's content writing output.

Task given: {task}
Output produced: {output}

Score on these dimensions (each 0-25 points):
1. On-brief — does it match what was asked (format, topic, audience, tone)
2. Quality — is it well-written, clear, engaging, not generic
3. Specificity — specific details, examples, data — not vague filler
4. Completeness — is it a finished, usable draft or just an outline

Respond in JSON only:
{{
  "on_brief_score": 0-25,
  "quality_score": 0-25,
  "specificity_score": 0-25,
  "completeness_score": 0-25,
  "total": 0-100,
  "best_thing": "one specific thing done well",
  "biggest_gap": "one specific thing missing or weak",
  "beat_this_next_time": "one concrete instruction for how to score higher next time"
}}""",

    "outreach": """You are grading an AI worker's outreach draft.

Task given: {task}
Output produced: {output}

Score on these dimensions (each 0-25 points):
1. Personalization — specific to the recipient, not generic
2. Clarity — clear value prop, easy to understand in 10 seconds
3. Call to action — specific, low-friction ask
4. Tone — appropriate for the relationship and context

Respond in JSON only:
{{
  "personalization_score": 0-25,
  "clarity_score": 0-25,
  "cta_score": 0-25,
  "tone_score": 0-25,
  "total": 0-100,
  "best_thing": "one specific thing done well",
  "biggest_gap": "one specific thing missing or weak",
  "beat_this_next_time": "one concrete instruction for how to score higher next time"
}}""",

    "research": """You are grading an AI worker's research output.

Task given: {task}
Output produced: {output}

Score on these dimensions (each 0-25 points):
1. Depth — how thoroughly was the topic covered
2. Sources — were multiple sources used, are they credible
3. Synthesis — is raw info turned into useful insight, not just facts
4. Actionability — does it tell the reader what to DO with this information

Respond in JSON only:
{{
  "depth_score": 0-25,
  "sources_score": 0-25,
  "synthesis_score": 0-25,
  "actionability_score": 0-25,
  "total": 0-100,
  "best_thing": "one specific thing done well",
  "biggest_gap": "one specific thing missing or weak",
  "beat_this_next_time": "one concrete instruction for how to score higher next time"
}}""",

    "ops": """You are grading an AI worker's operations/admin output.

Task given: {task}
Output produced: {output}

Score on these dimensions (each 0-25 points):
1. Accuracy — is the information correct and complete
2. Clarity — easy to read and act on
3. Format — appropriate structure for the type of output (table, bullets, prose)
4. Time-saving — does this actually save the manager meaningful time

Respond in JSON only:
{{
  "accuracy_score": 0-25,
  "clarity_score": 0-25,
  "format_score": 0-25,
  "time_saving_score": 0-25,
  "total": 0-100,
  "best_thing": "one specific thing done well",
  "biggest_gap": "one specific thing missing or weak",
  "beat_this_next_time": "one concrete instruction for how to score higher next time"
}}""",

    "other": """You are grading an AI worker's output.

Task given: {task}
Output produced: {output}

Score holistically (0-100):
- Was the task completed as requested?
- Is the output high quality and usable?
- Is it specific rather than generic?
- Does it save the manager time?

Respond in JSON only:
{{
  "total": 0-100,
  "best_thing": "one specific thing done well",
  "biggest_gap": "one specific thing missing or weak",
  "beat_this_next_time": "one concrete instruction for how to score higher next time"
}}""",
}
```

---

## Step 3: Grading + Hill-Climbing in `_run_autonomous_decision`

After Step 4 (log the action) and before Step 5 (learning extraction), add a grading block.

**Replace the existing Step 4 + Step 5 block** with this:

```python
    # Step 4: Classify task type
    task_type = "other"
    if output and len(output) > 30:
        try:
            classify_agent = AIAgent(
                model=or_model, api_key=or_key,
                base_url="https://openrouter.ai/api/v1", provider="openrouter",
                max_iterations=1, quiet_mode=True,
                skip_memory=True, skip_context_files=True, enabled_toolsets=[],
            )
            raw_type = classify_agent.run_conversation(
                user_message=_TASK_TYPE_PROMPT.format(task=task)
            ).get("final_response", "other").strip().lower()
            if raw_type in _GRADER_PROMPTS:
                task_type = raw_type
        except Exception:
            pass

    # Step 5: Grade the output (Karpathy-style — every action gets a number)
    quality_score = None
    grader_reasoning = None
    beat_this = None

    if output and len(output) > 50:
        try:
            grade_agent = AIAgent(
                model=or_model, api_key=or_key,
                base_url="https://openrouter.ai/api/v1", provider="openrouter",
                max_iterations=1, quiet_mode=True,
                skip_memory=True, skip_context_files=True, enabled_toolsets=[],
            )
            rubric = _GRADER_PROMPTS.get(task_type, _GRADER_PROMPTS["other"])
            grade_result = grade_agent.run_conversation(
                user_message=rubric.format(task=task, output=output[:1500])
            )
            raw_grade = grade_result.get("final_response", "").strip()
            if raw_grade.startswith("```"):
                import re as _re
                raw_grade = _re.sub(r"^```[a-z]*\n?", "", raw_grade)
                raw_grade = _re.sub(r"\n?```$", "", raw_grade.rstrip())
            grade = json.loads(raw_grade)
            quality_score = int(grade.get("total", 0))
            beat_this = grade.get("beat_this_next_time", "")
            grader_reasoning = json.dumps({
                k: v for k, v in grade.items() if k != "total"
            })
        except Exception as e:
            logger.debug("Grading failed for tenant %s: %s", str(tenant_id)[:8], e)

    # Step 6: Log action WITH score
    summary = f"{datetime.now().strftime('%Y-%m-%d %H:%M')} — {task[:120]}"
    if quality_score is not None:
        summary += f" [score: {quality_score}/100]"

    await self.db.execute(
        """INSERT INTO worker_actions
           (tenant_id, summary, full_output, task_type, quality_score, grader_reasoning, created_at)
           VALUES ($1, $2, $3, $4, $5, $6, NOW())""",
        tenant_id, summary, output, task_type, quality_score, grader_reasoning,
    )

    # Step 7: Hill-climb — compare to previous score for same task type
    if quality_score is not None and task_type != "other":
        prev = await self.db.fetchrow(
            """SELECT quality_score, grader_reasoning FROM worker_actions
               WHERE tenant_id=$1 AND task_type=$2 AND quality_score IS NOT NULL
               AND created_at < NOW() - INTERVAL '10 minutes'
               ORDER BY created_at DESC LIMIT 1""",
            tenant_id, task_type,
        )
        if prev and prev["quality_score"] is not None:
            prev_score = prev["quality_score"]
            delta = quality_score - prev_score
            if delta > 0:
                trend = f"IMPROVED +{delta} points ({prev_score} → {quality_score})"
            elif delta < 0:
                trend = f"REGRESSED {delta} points ({prev_score} → {quality_score})"
            else:
                trend = f"SAME score ({quality_score}/100)"

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            hill_note = (
                f"{trend} on {task_type}.\n"
                f"Task: {task[:100]}\n"
                f"{'What worked: ' + grade.get('best_thing','') if delta >= 0 else 'What went wrong: ' + grade.get('biggest_gap','')}\n"
                f"Next time: {beat_this or 'maintain approach'}"
            )
            await self.db.execute(
                """INSERT INTO tenant_memory (tenant_id, memory_type, content)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (tenant_id, memory_type)
                   DO UPDATE SET content = EXCLUDED.content, updated_at = NOW()""",
                tenant_id, f"hill_climb_{task_type}_{ts}", hill_note,
            )

    # Step 8: Save beat_this as standing instruction for next time
    if beat_this:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        await self.db.execute(
            """INSERT INTO tenant_memory (tenant_id, memory_type, content)
               VALUES ($1, $2, $3)
               ON CONFLICT (tenant_id, memory_type)
               DO UPDATE SET content = EXCLUDED.content, updated_at = NOW()""",
            tenant_id, f"learning_{ts}",
            f"[{task_type}] Score: {quality_score}/100. Next time: {beat_this}",
        )

    logger.info(
        "Autonomous task complete [%s] type=%s score=%s",
        str(tenant_id)[:8], task_type,
        f"{quality_score}/100" if quality_score is not None else "ungraded",
    )
```

---

## Step 4: Use Previous Score in Decision Prompt

In `_run_autonomous_decision`, before building `_DECISION_PROMPT`, load the last score per task type and inject it.

Add this block right **before** the `decision_agent.run_conversation(...)` call:

```python
    # Load recent scores per task type so LLM can aim to beat them
    score_rows = await self.db.fetch(
        """SELECT task_type, quality_score, grader_reasoning
           FROM worker_actions
           WHERE tenant_id=$1 AND quality_score IS NOT NULL
           ORDER BY created_at DESC LIMIT 10""",
        tenant_id,
    )
    scores_by_type = {}
    for row in score_rows:
        if row["task_type"] not in scores_by_type:
            scores_by_type[row["task_type"]] = row["quality_score"]

    scores_text = ""
    if scores_by_type:
        scores_text = "\n## Your Recent Quality Scores (beat these)\n"
        for t, s in scores_by_type.items():
            scores_text += f"- {t}: {s}/100\n"
```

Then append `{scores_text}` to the `_DECISION_PROMPT.format(...)` call by adding it to the memory section:

Change:
```python
            memory=memory_text,
```
To:
```python
            memory=memory_text + scores_text,
```

---

## Step 5: Expose Scores in `/stats` Endpoint

In `scale/gateway.py`, update the existing `GET /stats/{tenant_slug}` to include score trends:

Add to the stats response dict:
```python
    # Quality scores by task type
    score_rows = await db_pool.fetch(
        """SELECT task_type,
                  ROUND(AVG(quality_score)) as avg_score,
                  MAX(quality_score) as best_score,
                  COUNT(*) as attempts
           FROM worker_actions
           WHERE tenant_id = $1 AND quality_score IS NOT NULL
           GROUP BY task_type""",
        tenant["id"],
    )
    quality_trends = {
        r["task_type"]: {
            "avg": int(r["avg_score"]),
            "best": r["best_score"],
            "attempts": r["attempts"],
        }
        for r in score_rows
    }
```

And include `"quality_trends": quality_trends` in the returned dict.

---

## Verification Checklist

After deploying:

1. Run the migration: `psql ... -f scale/migrations/002_add_quality_scores.sql`
2. Rebuild + restart worker: `docker compose ... up -d --build`
3. Wait 10 minutes — let the autonomous loop fire twice
4. Check: `SELECT task_type, quality_score, grader_reasoning FROM worker_actions WHERE quality_score IS NOT NULL ORDER BY created_at DESC LIMIT 5;`
   - Should see rows with scores like `78`, `62`, `85`
   - `grader_reasoning` should have JSON with dimension scores and `beat_this_next_time`
5. Check: `SELECT memory_type, content FROM tenant_memory WHERE memory_type LIKE 'hill_climb_%' ORDER BY updated_at DESC LIMIT 3;`
   - Should see hill-climb notes like "IMPROVED +12 points (66 → 78) on lead_research"
6. Check: `GET /stats/{slug}` — should return `quality_trends` dict
7. After 5+ actions of same type — scores should trend upward as learnings compound

---

## What This Unlocks

- **Visible improvement**: `quality_trends` in `/stats` shows avg score per task type over time
- **Compounding**: every `beat_this_next_time` becomes a memory that loads into every future decision
- **Hill-climbing**: worker sees "lead_research: 66/100" and explicitly tries to beat it next time
- **Specific feedback**: not "do better" but "next time include LinkedIn URL and specific hiring signal for each lead"
- **No human required**: the grader LLM runs automatically, scores accumulate, behavior improves
