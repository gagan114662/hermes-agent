---
name: second-brain-ingest
description: Process source files from a vault's raw/ directory into structured wiki pages. YOU do the reading and writing — no external LLM needed.
version: 2.0.0
author: Hermes Agent
tags: [knowledge, second-brain, ingest, wiki, knowledge-management]
---

# Second Brain — Ingest Pipeline

You are the librarian. Read each raw source, extract knowledge, and write it into
structured wiki pages. No external tool does this — you do it directly using the
second_brain_* tools as file I/O primitives.

## When to Use

- User says "ingest", "process my sources", "add to my second brain"
- After files are dropped into raw/

## Steps

1. **Identify the vault** — call `second_brain_list()` if not specified, ask if multiple

2. **List unprocessed files** — call `second_brain_raw_list(vault_name)`
   - Show the user what's pending
   - Ask if they want all or specific files (default: all)

3. **For each unprocessed file:**

   a. **Read it** — call `second_brain_read_source(vault_name, filename)`

   b. **Write a sources/ summary** — call `second_brain_write_page(vault_name, "sources", stem, content)` where content is:
      ```markdown
      # [Title]

      *Source: [filename] — ingested [date]*

      ## Key Takeaways
      - [3-5 bullet points of the most important ideas]

      ## Key Entities
      [people, tools, companies mentioned — link with [[entity-name]]]

      ## Key Concepts
      [ideas, frameworks, theories — link with [[concept-name]]]

      ## Notes
      [anything else worth preserving]
      ```

   c. **Create/update entity pages** — for each person, tool, company, or organization found:
      - Check if page exists: `second_brain_read_page(vault_name, "entities", entity-name)`
      - Write/update: `second_brain_write_page(vault_name, "entities", entity-name, content)`
      - Entity page format:
        ```markdown
        # [Entity Name]

        **Type:** person | tool | company | organization

        ## What I Know
        [facts, role, relevance to the domain]

        ## Mentioned In
        - [[sources/filename]]
        ```

   d. **Create/update concept pages** — for each idea, framework, pattern, or theory:
      - Check if exists, write/update with `second_brain_write_page(vault_name, "concepts", concept-name, content)`
      - Concept page format:
        ```markdown
        # [Concept Name]

        ## What It Is
        [clear 1-3 sentence definition]

        ## Why It Matters
        [significance to the domain]

        ## Related Concepts
        - [[concept-name]]

        ## Mentioned In
        - [[sources/filename]]
        ```

   e. **Log it** — `second_brain_append_log(vault_name, "Ingested [filename] → [N] entity pages, [M] concept pages")`

4. **Rebuild index** — `second_brain_update_index(vault_name)` after all files are done

5. **Report** — tell the user:
   - How many sources processed
   - How many entity and concept pages created/updated
   - Suggest: "Open in Obsidian to see the knowledge graph"

## Quality Bar

- Entity pages: only create if the entity is genuinely relevant to the domain
- Concept pages: create for reusable ideas, not one-off facts
- Cross-references: always use [[page-name]] syntax to link related pages
- Keep pages concise — facts only, no filler

## Notes

- Process one file at a time — don't try to batch in one tool call
- An already-ingested file (has wiki/sources/ page) can be re-ingested if user asks
- After 5+ sources, the graph in Obsidian starts showing interesting connections
