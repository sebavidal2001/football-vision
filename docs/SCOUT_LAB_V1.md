# Scout Lab v1

Data: 2026-06-13

## Obiettivo

Scout Lab v1 e una piattaforma locale per scouting calcistico assistito:

- lavora su clip brevi da 30 a 120 secondi;
- importa output generati dalla pipeline Colab/locale;
- trasforma track ID grezzi in profili giocatore tramite revisione manuale;
- genera insight tecnico-tattici e schede scouting;
- usa OpenRouter per report AI con modello selezionabile dinamicamente.

La promessa della v1 non e "riconosco tutto automaticamente". La promessa e:

> carichi/analizzi una clip, rivedi le tracce, assegni identita e ruolo, e ottieni
> un profilo giocatore utile e salvabile.

## Flusso utente

1. L'utente carica una clip o importa risultati Colab.
2. Il backend sincronizza gli output in `output/`.
3. La dashboard mostra analisi disponibili, qualita dati e file prodotti.
4. L'utente seleziona una traccia.
5. L'utente corregge nome, numero, squadra, ruolo e note.
6. Il sistema mostra:
   - heatmap/posizione media;
   - timeline review della traccia/profilo;
   - salto video alla finestra osservata;
   - durata traccia;
   - area d'azione;
   - distanza indicativa;
   - velocita indicativa;
   - coinvolgimento stimato;
   - qualita/confidenza.
7. L'utente seleziona un modello OpenRouter.
8. L'AI genera un report scouting basato sui dati disponibili.

## Ambito tecnico

### Incluso

- Web app locale bella e usabile.
- Backend FastAPI.
- SQLite locale.
- Import automatico da `output/POSIZIONIAUTO_*.csv`.
- Lettura di `STATISTICHE_*.csv` se presente.
- Metadati manuali per traccia/giocatore.
- Merge manuale di piu tracce nello stesso profilo giocatore.
- Suggerimenti automatici di merge basati su gap temporale, distanza spaziale,
  squadra stimata/corretta e zona di campo.
- Identity Engine assistito:
  - crea una identita da un Track ID verificato;
  - propone altri Track ID da agganciare alla stessa identita;
  - applica nome, numero, ruolo e squadra del profilo alle tracce confermate.
- Quality score della clip.
- Dropdown modelli OpenRouter da endpoint `/api/v1/ai/models`.
- Generazione insight AI con OpenRouter oppure fallback locale se manca API key.
- Endpoint per upload clip e avvio job locale opzionale.
- Import diretto zip Colab dal frontend.
- Export Markdown del profilo aggregato.
- Visualizzazione video radar e clip originale se presenti.
- Timeline video per controllare quando una traccia/profilo compare nella clip.

### Non incluso nella v1

- Riconoscimento numero maglia garantito.
- Re-identification automatica multi-partita.
- Metriche atletiche professionali da broadcast.
- SaaS multiutente.
- GPU cloud automatizzata.

## Strategia Colab

Per ora Colab resta il worker GPU:

1. si carica la clip su Colab;
2. si esegue `notebooks/02_analisi_GPU_colab.ipynb`;
3. si scarica lo zip output;
4. si estrae nella cartella `output/` del progetto;
5. Scout Lab sincronizza e visualizza l'analisi.

Quando il motore sara soddisfacente, Colab verra sostituito da un worker GPU
cloud con la stessa interfaccia di import/export.

## Dati principali

- `analyses`: una clip/analisi importata.
- `tracks`: track ID prodotti dalla CV con metriche aggregate.
- `track_annotations`: correzioni manuali su nome, numero, ruolo, squadra, note.
- `player_profiles`: profili giocatore creati unendo una o piu tracce.
- `profile_tracks`: relazione tra profilo e track ID.
- `ai_reports`: report generati via OpenRouter.

## Metriche giocatore v1

- durata osservata;
- numero rilevazioni;
- squadra stimata/corretta;
- posizione media;
- area d'azione;
- distanza indicativa;
- velocita media/max indicativa;
- zona prevalente;
- confidenza.

## Merge tracce

Il merge e assistito nella v1:

1. il sistema propone coppie di tracce compatibili;
2. l'utente puo applicare il suggerimento o selezionare manualmente piu tracce;
3. crea un profilo aggregato;
4. il sistema somma durata osservata, rilevazioni, distanza indicativa e area;
5. l'AI genera insight sul profilo aggregato invece che sulla singola traccia.

Questo e il passaggio chiave per rendere utile lo scouting da broadcast, dove un
giocatore puo essere spezzato in molti track ID.

I suggerimenti non sono ancora re-identification affidabile: sono un filtro per
ridurre il lavoro umano. Vanno sempre confermati guardando clip/radar e dati.

## Identity Engine

La v1 introduce una propagazione identita assistita:

1. l'utente identifica un Track ID su clip/radar;
2. salva nome, numero, ruolo e squadra;
3. crea una identita giocatore da quel Track ID;
4. il sistema cerca altri Track ID compatibili con quella identita;
5. l'utente conferma o rifiuta gli agganci proposti.

La confidenza usa per ora regole euristiche:

- coerenza squadra;
- gap temporale;
- distanza spaziale tra fine/inizio tracce;
- zona di campo;
- durata e confidenza del Track ID.

In seguito potra ricevere embedding ReID visivi e OCR numero maglia dai worker
Colab/GPU cloud.

## Timeline review

La timeline collega i dati tabellari al video importato:

- mostra le tracce come barre temporali;
- permette di scegliere tra clip originale e radar Colab quando entrambi sono disponibili;
- usa radar con `#Track ID` stampati sopra i giocatori nei nuovi output;
- evidenzia la finestra attiva della traccia o del profilo aggregato;
- permette di saltare all'inizio o alla fine della finestra video;
- consente di selezionare una traccia o aggiungerla al merge direttamente dalla
  riga temporale.

Questo modulo e il ponte tra metrica e occhio umano: serve a confermare se una
coppia suggerita appartiene davvero allo stesso giocatore.

## AI nella v1

L'AI non guarda direttamente il video. Lavora su:

- metriche numeriche;
- annotazioni manuali;
- qualita dati;
- contesto clip;
- eventuali note utente.

Output richiesto:

- sintesi scouting;
- punti forti osservabili;
- limiti del campione;
- fit tattico probabile;
- cosa rivedere nel video;
- confidenza.

## Principio di prodotto

Meglio un profilo giocatore semi-automatico ma verificabile che un report
automatico spettacolare e fragile.
