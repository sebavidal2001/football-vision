# 🗺️ Piano — Come muoverci (da motore a prodotto)

## Dove siamo (giugno 2026)
Motore funzionante su Colab GPU: rilevamento giocatori/palla, riconoscimento campo
(broadcast), tracking, **metriche tattiche affidabili** + report. Codice su GitHub.
Limite noto: atletico per-giocatore limitato da broadcast (frammentazione).

## Principio guida
Il rischio del progetto NON è costruire il sito (parte facile/standard).
È **dimostrare che gli insight servono e che qualcuno li vuole**.
→ Validare il valore PRIMA di costruire il frontend.

---

## FASE 0 — Consolidare il motore "tactical-first"  *(ora, ~1-2 settimane)*
Obiettivo: un **report di scouting per partita** solido, onesto e che TU mostreresti a una società.
- [ ] Report onesto: separare metriche AFFIDABILI (tattiche/posizionali) da INDICATIVE (atletiche).
- [ ] Arricchire le tattiche: formazione/modulo, baricentro nel tempo, zone di pressing,
      ampiezza/profondità nel tempo, possesso per zone.
- [ ] Definire il "deliverable partita": 1 PDF/insieme di immagini + CSV che racconta la partita.
- [ ] Migliorare tracking quanto ragionevole (accettando il limite broadcast).
*Frontend: NO. Output = file (PNG/CSV/PDF).*

## FASE 1 — Validare con persone vere  *(la più importante, ~2-4 settimane)*
Obiettivo: capire se il prodotto serve, PRIMA di investire nel sito.
- [ ] Mostrare i report a 2-3 persone del calcio (allenatori, scout, DS di settori giovanili).
- [ ] Domande: cosa è utile? cosa manca? lo useresti? lo pagheresti? quanto?
- [ ] Capire il caso d'uso n.1 (scouting avversario? valutazione giocatori? analisi propria squadra?).
*Questo orienta TUTTO. Non serve frontend: bastano i file che già produci.*

## FASE 2 — Interfaccia minima (primo "frontend")  *(quando il valore è validato)*
Obiettivo: MVP usabile da non-tecnici.
- [ ] Web-app: carica video → job su GPU → vedi/scarica il report.
- [ ] Stack: **Next.js (Vercel)** + **Supabase** (DB/auth/storage) + **worker GPU a noleggio**.
- [ ] Login, una pagina "nuova analisi", una pagina "risultati".
*Decisione chiave qui: economia GPU (ogni analisi costa). Chi paga, quanto.*

## FASE 3 — Prodotto scouting  *(dopo l'MVP)*
- [ ] Database partite/giocatori, storico, confronti tra giocatori/partite.
- [ ] Multi-utente / società, ricerca, filtri.

## FASE 4 — Espansioni
- [ ] Event detection (passaggi/tiri → xG, PPDA vero).
- [ ] Atletico full-pitch (footage Veo/Pixellot dei clienti, o adattamento modello).

---

## Risposta alla domanda "quando il frontend?"
**Fase 2.** Non perché sia difficile, ma perché va costruito attorno a un valore
**già validato** (Fase 1). Capacità tecnica per farlo: l'abbiamo già.

## Prossimo passo concreto consigliato
Iniziare la **Fase 0**: trasformare l'output attuale in un **report partita professionale e
onesto** — il biglietto da visita con cui andrai a parlare con le persone del calcio (Fase 1).
