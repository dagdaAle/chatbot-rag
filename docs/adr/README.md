# Decisioni architetturali

Decisione corrente: [006 — Open WebUI Intecha](006-openwebui-intecha.md).
Le ADR 001–005 descrivono il prodotto legacy: le scelte di base applicativa,
persistenza e IAM sono sostituite dalla 006 nel nuovo runtime. Il principio di
protezione delle uscite esterne rimane e viene applicato dal gateway.


ADR iniziali ricostruite il 30 ottobre 2026 dal codice al commit `09467b4`.
Lo stato «adottata» indica una scelta implementata. Le motivazioni sono una
ricostruzione tecnica attuale, non un verbale storico di approvazione.

| ADR | Decisione | Stato |
| --- | --- | --- |
| [001](001-persistenza-specializzata.md) | Persistenza specializzata per applicazione, ricerca e file | Adottata |
| [002](002-iam-supabase.md) | Supabase Auth e autorizzazioni centralizzate in SQL | Adottata |
| [003](003-worker-import.md) | Import asincrono persistente con worker separato | Adottata |
| [004](004-protezione-provider.md) | Embedding locali e protezione obbligatoria delle chat esterne | Adottata |
| [005](005-retrieval-listini-agente.md) | Retrieval ibrido, listini deterministici e agente limitato | Adottata |

Per nuove decisioni usare un numero progressivo e indicare: data, stato
(proposta/adottata/superata), contesto, decisione, alternative, conseguenze,
evidenze e criterio di riesame. Il lavoro ancora da decidere resta nei
[piani](../plans/README.md); non trasformarlo in una decisione già adottata.
