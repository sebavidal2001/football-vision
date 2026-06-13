# Panorama open source per football vision e analytics

Data analisi: 2026-06-13

## Sintesi breve

Siamo ancora lontani da una piattaforma solida, ma non perche il progetto sia
sbagliato. Il motivo e che il problema vero non e "fare due grafici": e
trasformare un video broadcast in dati affidabili. I progetti open seri separano
quasi sempre il lavoro in due strati:

1. **Video -> dati affidabili**
   Detection, tracking, calibrazione campo, squadra, identita, numero di maglia,
   palla. E lo strato difficile, quello dove noi oggi soffriamo.
2. **Dati -> insight**
   Metriche, visualizzazioni, report, confronti, modelli tattici. Qui esistono
   librerie mature e conviene adottarle invece di riscrivere tutto.

La direzione consigliata e quindi: non inseguire subito il frontend. Prima
consolidare il motore dati, scegliere cosa adottare dai progetti open, e
costruire una pipeline onesta che distingua metriche affidabili da metriche
indicative.

## Dove siamo noi oggi

Nel repository esiste gia una pipeline funzionante:

- `vista_tattica/genera_radar_auto.py`: rileva campo, giocatori, portieri,
  arbitro e palla; stima una homography frame-by-frame; produce CSV con
  posizioni in metri.
- `analisi/stats_giocatori.py`: heatmap e statistiche per traccia.
- `analisi/metriche_avanzate.py`: formazione media, baricentro, ampiezza,
  profondita, compattezza, possesso stimato, metriche atletiche indicative.
- `analisi/report_pdf.py`: pacchetto finale in report.
- `notebooks/02_analisi_GPU_colab.ipynb`: esecuzione su Colab GPU.

I limiti principali osservati sono coerenti con quelli riconosciuti nei progetti
open:

- **Team assignment instabile**: oggi dipende molto dal colore maglia e da KMeans.
  Con maglie simili, ombre, portieri, arbitri e crop sporchi sbaglia facilmente.
- **ID giocatore fragili**: se un giocatore esce dal frame o si sovrappone a un
  altro, la traccia puo spezzarsi o scambiarsi.
- **Palla difficile**: piccola, veloce, spesso invisibile o confusa.
- **Calibrazione non sempre robusta**: la homography da keypoint e utile, ma se
  pochi punti campo sono visibili la proiezione diventa rumorosa.
- **Metriche avanzate limitate dalla qualita dei dati**: distanza, sprint e
  velocita da broadcast vanno lette come indicative, non come dati atletici
  professionali.

## Progetti open rilevanti

### 1. SoccerNet `sn-gamestate` + TrackLab

Link: https://github.com/SoccerNet/sn-gamestate

E il riferimento piu vicino al nostro obiettivo. Il task ufficiale di SoccerNet
Game State Reconstruction vuole estrarre da video broadcast:

- posizione 2D delle persone sul campo;
- ruolo: giocatore, portiere, arbitro, altro;
- numero di maglia;
- affiliazione alla squadra;
- visualizzazione su minimap/radar.

La cosa importante: non prova a risolvere tutto con un solo modello semplice.
Divide il problema in sottosistemi:

- pitch localization e camera calibration;
- person detection, re-identification e tracking;
- jersey number recognition;
- team affiliation.

Usa TrackLab come framework modulare per detection, tracking e re-identification.
Il repo specifico SoccerNet aggiunge le parti calcistiche: numero di maglia,
squadra, task GSR e valutazione.

Implicazione per noi:

- e il benchmark da studiare per capire "come si fa bene";
- e probabilmente pesante da integrare subito nel nostro repo;
- pero la sua architettura ci dice la verita: senza ReID, OCR numero e una
  calibrazione robusta, non avremo identita affidabili da partita intera.

### 2. `roboflow/sports`

Link: https://github.com/roboflow/sports

E un progetto piu accessibile e vicino a quello che abbiamo gia costruito:
detection, tracking, team assignment, pitch keypoints, homography e tutorial.
Infatti la nostra direzione attuale assomiglia molto a questa famiglia di
approcci.

Roboflow stesso elenca come problemi aperti:

- ball tracking;
- jersey number reading;
- player tracking;
- player re-identification;
- camera calibration.

Implicazione per noi:

- ottimo come baseline e sorgente di esempi;
- utile per migliorare rapidamente la nostra pipeline;
- non basta, da solo, per una piattaforma professionale su partite intere.

### 3. SportsLabKit

Link: https://github.com/AtomScott/SportsLabKit

SportsLabKit e una libreria Python orientata a trasformare video sportivi in dati.
Include implementazioni di SORT, DeepSORT, ByteTrack e TeamTrack, supporto a
YOLOv8 e modelli ReID, calibrazione 2D del campo e DataFrame per manipolare
bounding box e coordinate.

Implicazione per noi:

- puo essere utile se vogliamo sostituire il tracking custom in coordinate campo
  con un framework piu strutturato;
- puo aiutarci a standardizzare l'output invece di inventare ogni formato CSV;
- va valutata in pratica, perche integrare un framework puo richiedere piu tempo
  che copiare una singola idea.

### 4. SoccerNet challenge repos

Link tracking: https://github.com/SoccerNet/sn-tracking
Link calibrazione: https://github.com/SoccerNet/sn-calibration
Link ReID: https://github.com/SoccerNet/sn-reid

SoccerNet mantiene task separati per tracking, calibrazione, re-identification,
action spotting e altri problemi video calcistici.

Implicazione per noi:

- i nostri problemi non sono "bug banali": sono task di ricerca con benchmark;
- questi repo sono utili per capire metriche, dataset e baseline;
- prima di sviluppare una feature difficile, conviene verificare se esiste gia
  una baseline SoccerNet.

### 5. TVCalib

Link: https://github.com/mm4spa/tvcalib

TVCalib affronta la registrazione/calibrazione del campo da video soccer. La
differenza concettuale importante: non tratta il problema solo come homography,
ma come camera calibration per sports field registration.

Implicazione per noi:

- la nostra homography frame-by-frame e una buona scorciatoia MVP;
- per dati metrici piu stabili serve un approccio di calibrazione piu forte;
- TVCalib e una direzione da studiare, soprattutto se continuiamo con video
  broadcast.

### 6. PnLCalib

Link: https://github.com/mguti97/PnLCalib

PnLCalib usa punti e linee del campo, un modello 3D del campo e un modulo di
refinement non lineare. E pensato proprio per casi broadcast difficili: angoli
camera variabili, occlusioni, pochi punti visibili.

Implicazione per noi:

- direzione molto interessante per sostituire o affiancare la homography attuale;
- potenzialmente piu robusta per le partite intere;
- da testare prima in isolamento su pochi frame, non da integrare subito alla
  cieca.

### 7. floodlight

Link: https://github.com/floodlight-sports/floodlight

floodlight e una libreria Python per analisi di dati sportivi. Gestisce tracking
data, event data, pitch information, teamsheet, filtri, trasformazioni,
visualizzazioni e modelli come:

- centroidi;
- distanze, velocita, accelerazioni;
- metabolic power;
- Voronoi / space control;
- parsing da vari provider e dataset.

Implicazione per noi:

- lo strato analytics e in parte gia risolto da librerie come questa;
- possiamo smettere di mantenere alcune metriche a mano;
- conviene prima esportare i nostri dati in un formato pulito, poi usare/adattare
  floodlight.

### 8. kloppy

Link: https://kloppy.pysport.org

kloppy standardizza dati evento e tracking in soccer analytics. Serve soprattutto
quando si vogliono leggere o produrre dati in formati diversi senza riscrivere
adattatori ogni volta.

Implicazione per noi:

- non migliora direttamente la detection;
- e utile per creare un formato dati serio;
- puo diventare lo strato di interoperabilita tra il nostro CSV e librerie
  analytics esterne.

### 9. mplsoccer

Link: https://mplsoccer.readthedocs.io

mplsoccer e una libreria per visualizzazioni calcistiche: pitch, radar chart,
pizza chart, heatmap, hexbins, scatter, linee e caricamento StatsBomb open-data.

Implicazione per noi:

- ottima per rendere i report piu professionali;
- puo sostituire parte del disegno campo custom;
- non risolve i dati, ma migliora molto il deliverable.

### 10. socceraction

Link: https://github.com/ML-KULeuven/socceraction

socceraction lavora su dati evento e modelli come VAEP, xT e analisi del valore
delle azioni. Non parte dal video grezzo: assume di avere eventi.

Implicazione per noi:

- utile in una fase successiva, quando avremo event detection o import eventi;
- non e il primo problema da risolvere;
- puo diventare rilevante per scouting avanzato e valutazione decisionale.

### 11. OpenSTARLab

Link: https://github.com/open-starlab

OpenSTARLab e una piattaforma open per dati spatio-temporal multi-agent,
inizialmente applicata al calcio. Include strumenti per annotazione eventi,
standardizzazione dati, predictive modeling e reinforcement learning.

Implicazione per noi:

- e piu ricerca/analytics avanzata che pipeline video immediata;
- interessante per una piattaforma futura;
- utile quando avremo dati posizionali/evento abbastanza puliti.

## Lezioni pratiche per il nostro progetto

### Lezione 1: il collo di bottiglia e Video -> Dati

Oggi il problema non e il PDF, il frontend o il database. Il collo di bottiglia e
questo:

```text
video broadcast -> posizioni corrette + squadre corrette + ID stabili + palla
```

Se questa parte e rumorosa, tutte le metriche successive diventano fragili.

### Lezione 2: KMeans sul colore non basta

Il colore medio della maglia e una buona scorciatoia MVP, ma non regge bene:

- cambi luce/ombra;
- maglie simili;
- portieri con colori diversi;
- arbitri e staff;
- giocatori piccoli o sfocati;
- crop con erba o pubblico.

Direzione migliore:

- team assignment con feature visive piu robuste;
- voto temporale per traccia, gia abbozzato nel nostro `TrackerMetrico`;
- correzione manuale nel report/MVP;
- in futuro: ReID e/o jersey number recognition.

### Lezione 3: gli ID non sono giocatori reali

Il nostro `id_giocatore` e un track id, non un giocatore. Su partita intera puo
spezzarsi molte volte. Quindi:

- per ora non promettere scouting individuale preciso su 90 minuti;
- usare metriche per squadra e zone come output principale;
- trattare metriche individuali come "tracce principali", non identita reali;
- prevedere etichettatura manuale se vogliamo collegare ID a nomi.

### Lezione 4: le metriche tattiche sono piu realistiche delle atletiche

Da broadcast, un giocatore puo uscire dall'inquadratura per lunghi periodi.
Quindi:

- baricentro, ampiezza, profondita, compattezza, zone e heatmap squadra sono
  obiettivi sensati;
- distanza totale, sprint e velocita per giocatore sono indicative;
- per atletica seria servono full-pitch camera, multi-camera, tracking provider o
  video tipo Veo/Pixellot.

### Lezione 5: adottare librerie analytics invece di riscrivere tutto

Il nostro strato `analisi/` e utile per imparare e produrre un report, ma la
direzione migliore e:

- continuare ad avere metriche nostre semplici e controllabili;
- esportare dati in un formato piu standard;
- adottare gradualmente `mplsoccer` per visualizzazioni;
- valutare `floodlight` per metriche tracking;
- valutare `kloppy` per formati dati.

## Gap analysis: cosa manca rispetto ai progetti seri

| Area | Noi oggi | Progetti maturi | Priorita |
| --- | --- | --- | --- |
| Detection giocatori/palla | modello calcio + YOLO | modelli specializzati e benchmark | Alta |
| Team assignment | colore maglia + KMeans | team affiliation dedicata, ReID, correzioni temporali | Alta |
| Tracking | tracker metrico custom | ByteTrack/DeepSORT/TrackLab/ReID | Alta |
| Re-identification | assente | modelli ReID e metriche dedicate | Molto alta per scouting player |
| Numero maglia | assente | OCR/jersey number recognition | Media/alta |
| Calibrazione campo | keypoint + homography | TVCalib/PnLCalib/camera calibration | Alta |
| Eventi | assenti/stimati dalla palla | action spotting/event data | Media |
| Analytics | metriche custom | floodlight, kloppy, socceraction | Media |
| Report | PDF/PNG base | visualizzazioni curate e validazione | Alta per vendibilita |
| Piattaforma | documentata, non implementata | web app + job GPU + DB | Dopo validazione motore |

## Direzione consigliata

### Fase A - Stabilizzare un report tattico onesto

Obiettivo: avere un report che si puo mostrare a un allenatore/scout senza
promettere cose false.

Fare:

- separare nel report metriche **affidabili** e **indicative**;
- mettere al centro le metriche di squadra e di zona;
- ridurre enfasi su distanza/sprint individuali;
- aggiungere un riepilogo qualita dati:
  - frame analizzati;
  - percentuale frame con campo riconosciuto;
  - numero tracce generate;
  - durata media tracce;
  - rilevazioni scartate;
  - avviso se il video e troppo corto o parziale.

### Fase B - Migliorare il motore dati senza riscrivere tutto

Obiettivo: ottenere dati meno sporchi prima di costruire la piattaforma.

Fare:

- testare piu configurazioni di detection e tracking su una clip breve annotata;
- misurare qualita: quante tracce per squadra, durata media tracce, cambi squadra;
- migliorare team assignment:
  - calibrazione colori su campioni piu puliti;
  - smoothing temporale;
  - possibilita di invertire/correggere squadre manualmente;
  - esclusione piu robusta di arbitri/staff.
- valutare SportsLabKit o TrackLab come alternativa al tracker custom.

### Fase C - Sostituire/affiancare la calibrazione

Obiettivo: rendere piu stabile la mappa in metri.

Fare:

- testare TVCalib o PnLCalib su frame estratti dal nostro video;
- confrontare errore visivo della proiezione linee campo;
- se funziona, integrare prima come step offline, poi nella pipeline.

### Fase D - Standardizzare dati e visualizzazioni

Obiettivo: preparare il terreno per una piattaforma vera.

Fare:

- definire schema dati stabile:
  - match;
  - frame/time;
  - track_id;
  - team_id;
  - role;
  - x/y campo;
  - confidence;
  - source quality flags.
- valutare export compatibile con kloppy/floodlight;
- usare mplsoccer per rendere le immagini piu pulite.

### Fase E - Solo dopo: piattaforma

Costruire frontend/backend prima di avere dati decenti rischia di impacchettare
un motore fragile. La piattaforma ha senso quando:

- il report tattico e leggibile;
- i limiti sono dichiarati;
- almeno 2-3 persone del calcio dicono che l'output e utile;
- abbiamo un costo stimato per analisi su GPU.

## Raccomandazione netta

Non dobbiamo buttare via il lavoro fatto. Dobbiamo cambiare ambizione immediata:

```text
da "piattaforma completa di scouting automatico"
a  "motore tattico broadcast-first con report onesto e migliorabile"
```

Per il breve periodo, il miglior prodotto e:

- upload/clip o Colab;
- report tattico squadra;
- heatmap e zone;
- andamento baricentro/ampiezza/profondita;
- qualita dati esplicita;
- metriche individuali indicate come tracce, non giocatori reali.

Per arrivare a scouting individuale vero servono:

- ReID;
- jersey OCR o etichettatura manuale;
- tracking robusto su uscite/rientri;
- possibilmente video full-pitch o dataset/provider migliori.

## Fonti principali

- SoccerNet Game State Reconstruction: https://github.com/SoccerNet/sn-gamestate
- SoccerNet Tracking: https://github.com/SoccerNet/sn-tracking
- SoccerNet Calibration: https://github.com/SoccerNet/sn-calibration
- SoccerNet ReID: https://github.com/SoccerNet/sn-reid
- Roboflow Sports: https://github.com/roboflow/sports
- SportsLabKit: https://github.com/AtomScott/SportsLabKit
- TVCalib: https://github.com/mm4spa/tvcalib
- PnLCalib: https://github.com/mguti97/PnLCalib
- floodlight: https://github.com/floodlight-sports/floodlight
- kloppy: https://kloppy.pysport.org
- mplsoccer: https://mplsoccer.readthedocs.io
- socceraction: https://github.com/ML-KULeuven/socceraction
- OpenSTARLab: https://github.com/open-starlab
