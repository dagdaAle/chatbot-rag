# Design — Intecha su Open WebUI

Aggiornamento: 30 ottobre 2026. L'interfaccia corrente deriva da Open WebUI v0.12.5:
layout, componenti, navigazione e temi seguono upstream. Non applicare i componenti
React/shadcn del frontend legacy all'app corrente, che usa il frontend Svelte upstream.

## Personalizzazione presente

Nome Intecha in UI e metadati; icona derivata dal marchio geometrico già presente
nel repository; favicon e splash chiaro/scuro sostituiti. Lingua iniziale italiana.
L'overlay è in `deploy/openwebui/brand.py`, non in un foglio CSS che nasconde il marchio.
Licenza e attribuzioni originali sono conservate nell'immagine e nel repository.

Il rebranding usa l'eccezione <=50 utenti/30 giorni confermata dal proprietario.
[Condizioni](../deploy/openwebui/NOTICE.md). Non rimuovere o alterare avvisi legali
per effetto di una personalizzazione grafica.

## Convenzioni

Mantenere temi chiaro/scuro e comportamento responsive upstream. Modifiche grafiche
minime per ridurre conflitti con gli aggiornamenti. Non mostrare segnaposto PII o
errori provider grezzi: il gateway completa il ripristino prima della visualizzazione.
La risposta arriva al termine della generazione; non simulare uno streaming progressivo.

Verificare accesso, titolo, splash, favicon, sidebar, citazioni, schermate mobile e
lingua al cambio release. Separare la visualizzazione delle fonti dalla certezza
che ogni affermazione sia supportata: una citazione non è una certificazione.

I vecchi token Geist/Tailwind/shadcn rimangono nel frontend legacy e non descrivono
lo stile corrente. Il nuovo stile segue la release upstream fissata.
