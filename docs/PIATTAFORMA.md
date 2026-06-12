# 🏗️ Architettura della Piattaforma — Football Vision

Documento di lavoro per progettare il backend/piattaforma che ospiterà il sistema.

## Idea in una frase
Un utente carica una clip → il sistema la analizza (CV su GPU) → salva video annotato,
heatmap, posizioni e statistiche in un database → l'utente le consulta e confronta i
giocatori tramite un'interfaccia web (scouting).

## I componenti (cosa serve)

```
   [ UTENTE / SCOUT ]
          │  (browser)
   ┌──────▼───────┐
   │  FRONTEND    │  Sito web: upload clip, vedi radar/heatmap/dashboard, confronta giocatori
   │  (Next.js)   │
   └──────┬───────┘
          │  API
   ┌──────▼───────┐      ┌─────────────────┐
   │  BACKEND API │─────▶│  CODA DI LAVORO  │  mette in fila i job di analisi
   │  (FastAPI)   │      │  (Redis/queue)   │
   └──────┬───────┘      └────────┬────────┘
          │                       │
   ┌──────▼───────┐      ┌────────▼─────────┐
   │   DATABASE   │      │  WORKER GPU      │  ESEGUE la pipeline CV (i nostri script)
   │ (PostgreSQL) │◀─────│  (cloud GPU)     │  campo+giocatori → posizioni/stats
   │  + STORAGE   │      └──────────────────┘
   │ (video/file) │
   └──────────────┘
```

### 1. Frontend (interfaccia)
Sito web dove l'utente carica clip e vede i risultati (radar, heatmap, dashboard, confronti).
- Tecnologia consigliata: **Next.js**, hosting su **Vercel**.

### 2. Backend API
Riceve le clip, crea i "job" di analisi, espone i risultati al frontend.
- Tecnologia: **FastAPI (Python)** — naturale, perché tutta la nostra CV è in Python.

### 3. Worker GPU (il motore)
Esegue la pipeline pesante (modello campo + giocatori + stats). **Richiede GPU.**
- Opzioni: GPU a noleggio on-demand (RunPod, Modal, Lambda, Vast) oppure un server GPU.
- I nostri script attuali (`genera_radar_auto.py`, `stats_giocatori.py`, ...) sono già il
  cuore del worker: vanno solo "impacchettati" come job.

### 4. Database + Storage
- **Storage file**: video caricati + output (radar.mp4, heatmap.png, dashboard.png).
- **Database (PostgreSQL)**: dati strutturati per lo scouting (vedi sotto).
- Tecnologia consigliata: **Supabase** (Postgres + autenticazione + storage in uno).

## Modello dati (le tabelle principali)

- **partite**: id, squadra_casa, squadra_ospite, data, video_url, stato_analisi
- **giocatori**: id, nome, squadra, ruolo  *(l'identità per nome è difficile: all'inizio
  si lavora per "track id" di partita, poi etichettatura manuale)*
- **posizioni**: partita_id, frame, tempo_s, track_id, squadra, x_m, y_m
  *(tabella enorme → spesso conviene salvarla come file per-partita, non riga per riga)*
- **statistiche**: partita_id, track_id, squadra, distanza, area_azione, pos_media, velocità...
- **risultati_file**: riferimenti a radar.mp4 / heatmap / dashboard

## Le 3 decisioni che contano

1. **Dove gira la GPU** (è il costo principale): noleggio on-demand ~0,5–1,5 $/ora;
   una partita = pochi minuti di GPU. Si paga solo quando si analizza.
2. **Identità giocatore**: collegare i track-id ai nomi reali tra partite diverse è
   IL problema difficile dello scouting. Si parte per-partita + etichettatura manuale.
3. **Scala/utenti**: solo tu? una società? vendita a scout? Cambia tutto il dimensionamento.

## Percorso a fasi (consigliato)

- **Fase A — App locale usabile:** interfaccia semplice (es. Streamlit/FastAPI) sopra gli
  script attuali, gira sul tuo PC o su una GPU noleggiata. Niente account. Rende il tool
  utilizzabile senza terminale. *(piccolo sforzo, grande comodità)*
- **Fase B — Cloud minimo:** frontend Next.js (Vercel) + Supabase (DB/auth/storage) +
  worker GPU. Multiutente, carichi e vedi i risultati online.
- **Fase C — Prodotto scouting:** database giocatori tra più partite, confronti e
  classifiche, ricerca, gestione società/account.

## Stack consigliato (moderno e gestibile da solo)
- Frontend: **Next.js + Vercel**
- Backend/DB/Auth/Storage: **Supabase**
- Worker CV: **Python su GPU a noleggio** (i nostri script)

> Nota: prima di "industrializzare", conviene rifinire ancora il motore CV (bilanciamento
> squadre, validazione con dataset full-pitch). La piattaforma impacchetta un motore che
> deve già funzionare bene.
