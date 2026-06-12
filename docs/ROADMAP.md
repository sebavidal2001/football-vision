# ⚽ Football Vision — Roadmap

Piattaforma di computer vision per analisi calcistica (tattica, atletica, performance) a supporto dello scouting.

## Contesto / vincoli
- **Input iniziale:** clip broadcast/TV (camera mobile). Ottimo per tattica/eventi, limitato per distanze atletiche totali.
- **Hardware:** PC solo CPU (16GB RAM) → calcolo pesante su **Google Colab (GPU gratis)**, eventuale GPU a noleggio più avanti.
- **Profilo:** utente lato calcio/scouting, poca esperienza di codice → si procede a moduli, con spiegazioni.

## Gli strati tecnici (mattoni)
1. **Detection & tracking** — giocatori, palla, arbitro frame-by-frame + ID stabile nel tempo.
2. **Team & player ID** — squadra (da colori maglia); numero/identità giocatore (avanzato).
3. **Homography / calibrazione campo** — da pixel a coordinate reali (105×68 m). Sblocca i dati veri.
4. **Metriche derivate** — heatmap, distanze, velocità, possesso, baricentro, pressing, ampiezza/profondità.
5. **Storage & confronto** — DB metriche per giocatore/partita + dashboard di comparazione (scouting).

## Fasi
- [x] **Fase 1 — Video annotato (MVP)** ✓ fatto
      detection + tracking + squadre. Notebook Colab + `analizza_locale.py` (CPU).
      Feedback utente: box troppo invadenti, numeri illeggibili da broadcast.
- [~] **Fase 2 — Dati reali (Vista Tattica 2D)** ← *in corso*
      Homography manuale → mappa 2D dall'alto + posizioni in metri su CSV.
      Strumenti: `vista_tattica/` (campo_calcio, calibra_campo GUI, genera_radar).
      Grafica rifatta pulita (ellissi ai piedi). Demo funzionante (calibrazione
      provvisoria sbilanciata → serve calibrazione precisa dell'utente).
      TODO: (a) calibrazione utente accurata; (b) modello specifico calcio per
      tracking stabile; (c) calibrazione AUTOMATICA per camera in movimento.
- [ ] **Fase 3 — Metriche tattiche + scouting**
      Dal CSV: heatmap, distanze, velocità, baricentro, ampiezza, pressing;
      dashboard di confronto giocatori.
- [ ] **Fase 4 — Eventi & avversario**
      passaggi, tiri, duelli; analisi pattern avversario.

## Setup tecnico raggiunto
- Download YouTube ottimizzato: client web + `--js-runtimes node` = 720p a piena
  velocità fibra (~9 MiB/s). Strumenti: scaricatore_clip + ritaglia_locale (taglio
  istantaneo da file locale, evita lo "scorrimento" ffmpeg dei segmenti tardivi).
- Stack analisi locale (CPU): ultralytics 8.4 + torch CPU + supervision + Pillow.
- Partita di test scaricata: clips_input/PARTITA_PSG_Inter_full_720p.mp4 (1h52m).

## Aspettative oneste
- Da clip broadcast: ottima analisi tattica/eventi; distanze atletiche totali inaffidabili (servono camera fissa o multi-camera).
- "Analisi di tutto" = obiettivo finale, costruito modulo per modulo.

## Risorse utili
- `roboflow/sports` (GitHub) — codice open source detection/tracking/homography calcio.
- Roboflow Universe — modelli pre-addestrati "football players detection".
- Librerie: `ultralytics` (YOLO), `supervision` (tracking/annot.), `scikit-learn`.
