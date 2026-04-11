---
name: second-brain-query
description: Ask questions against a vault's wiki. YOU read the pages and synthesize the answer directly using your intelligence.
version: 2.0.0
author: Hermes Agent
tags: [knowledge, second-brain, query, wiki, knowledge-management]
---

# Second Brain — Query Interface

You answer questions by reading wiki pages directly. No external tool synthesizes
for you — you read and reason using your own intelligence.

## When to Use

- User asks a question about their domain
- User wants to synthesize knowledge across sources
- User wants to find gaps or contradictions

## Steps

1. **Identify the vault** — `second_brain_list()` if not specified

2. **List what's available** — `second_brain_list_pages(vault_name, "all")`

3. **Read relevant pages** — use `second_brain_read_page()` to read:
   - Relevant sources/ pages
   - Relevant entity/ pages
   - Relevant concept/ pages
   - Any synthesis/ pages that might apply

4. **Synthesize and answer** — use your own reasoning across what you read.
   Cite pages using [[section/page-name]] format.

5. **Offer to save as synthesis** — if the answer is analytical or non-obvious:
   > "Want me to save this as a synthesis page for future reference?"

   If yes: `second_brain_write_page(vault_name, "synthesis", slug, content)`
   Then: `second_brain_append_log(...)` + `second_brain_update_index(...)`

## Power Queries

These get the most value from accumulated knowledge:
- "What topics appear across multiple sources but have no synthesis yet?"
- "What are the contradictions between [source A] and [source B]?"
- "What entities appear most and what do we know about them?"
- "Based on everything, what am I missing in my understanding of [topic]?"
- "Summarize everything about [[entity-name]] across all sources"
