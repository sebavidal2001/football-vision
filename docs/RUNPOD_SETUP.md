# 🚀 RunPod — configurazione (worker GPU on-demand)

Esegue il passo pesante (rilevamento) su una GPU cloud RunPod, accesa solo per il
tempo necessario e **spenta automaticamente** a fine job. I passi leggeri restano sul PC.

## 0) Sicurezza credito
- Su RunPod → **Settings → Billing**: assicurati che **auto-reload/auto-pay sia DISATTIVATO**.
  Così i $10 caricati sono un tetto rigido: a credito esaurito i pod si fermano, niente sorprese.

## 1) Chiave SSH (una volta sola)
Serve per far parlare il PC col pod.

1. Apri PowerShell e crea una chiave (se non ce l'hai già):
   ```
   ssh-keygen -t ed25519 -f $HOME\.ssh\id_ed25519 -N '""'
   ```
   Crea due file: `id_ed25519` (privata, resta sul PC) e `id_ed25519.pub` (pubblica).
2. Copia il contenuto della **pubblica**:
   ```
   Get-Content $HOME\.ssh\id_ed25519.pub
   ```
3. Su RunPod → **Settings → SSH Public Keys** → incolla la chiave pubblica e salva.

## 2) Chiave API e configurazione
1. Su RunPod → **Settings → API Keys** → crea/copia la tua API key.
2. Copia il file modello:
   ```
   copy scout_lab\secrets.env.example scout_lab\data\secrets.env
   ```
3. Apri `scout_lab\data\secrets.env` e incolla:
   - `RUNPOD_API_KEY=` la tua key
   - `RUNPOD_SSH_KEY=` il percorso della chiave PRIVATA (es. `C:/Users/sebav/.ssh/id_ed25519`)
   - `RUNPOD_GPU=` la GPU (default RTX 4090)

   👉 Questo file è in `scout_lab/data/` che è **ignorato da git**: la chiave non finisce nel repository.

## 3) Dipendenze backend
Il backend ora usa `runpod` e `paramiko`. Si installano da soli al primo avvio
(`AVVIA_scout_lab.bat` esegue `pip install -r requirements.txt`).

## 4) Uso
- Da Scout Lab: avvia un'analisi locale con l'opzione **"Esegui su RunPod"** attiva.
- Oppure test diretto del worker:
  ```
  cd scout_lab\backend\app
  python runpod_worker.py C:\percorso\al\video.mp4
  ```
  Vedrai: accensione pod → setup → upload video → rilevamento GPU → download CSV → spegnimento pod.

## Costi e sicurezza
- Paghi solo i minuti di pod acceso (~$0,1–0,25 a partita su 4090).
- Il pod viene **terminato automaticamente** a fine job. Se vedi un avviso che la
  terminazione è fallita, spegnilo a mano da runpod.io (sezione Pods).
- Verifica ogni tanto su runpod.io che non ci siano pod accesi dimenticati.

## Note tecniche
- Prima esecuzione: il pod scarica repo + modelli + dipendenze (~3-5 min di setup) prima
  dell'analisi. Si può ottimizzare in seguito con un'immagine/volume pre-pronti.
- Worker: `scout_lab/backend/app/runpod_worker.py` (testabile da solo).
- Configurazione via `scout_lab/data/secrets.env` o variabili d'ambiente.
