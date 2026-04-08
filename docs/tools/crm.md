# CRM & Sales Tools

See the [Tool Reference overview](index.md) for the full tool list with descriptions.

The `crm` toolset covers the full customer lifecycle: lead capture, discovery, scoping, project management, outreach, and invoicing.

## Required setup

No API keys required — the CRM is file-based, stored in `~/.hermes/data/crm/`.

Enable the toolset:

```bash
hermes --toolset crm
```

## Workflow example

```
1. New lead → crm_save (capture contact)
2. First call → crm_log (log interaction)
3. Discovery → discovery_run (find real problem)
4. Scope → scope_create (SOW)
5. Project → project_create (phases + tasks)
6. Daily → project_standup (progress)
7. Invoice → invoice_create (via invoicing toolset)
```

## Business wiki

The `wiki_*` tools maintain a knowledge base about your business — products, clients, processes.

```
wiki_ingest   ← feed new documents
wiki_query    ← ask questions
wiki_update   ← edit existing pages
wiki_list     ← browse pages
wiki_read     ← read a full page
```
