# Scout Lab

Interfaccia locale per revisione tracce, profili giocatore e insight AI.

## Avvio

Terminale 1:

```powershell
cd C:\Users\sebav\Desktop\VISUAL_COMPUTING\scout_lab\backend
python -m pip install -r requirements.txt
python run.py
```

Terminale 2:

```powershell
cd C:\Users\sebav\Desktop\VISUAL_COMPUTING\scout_lab\frontend
npm install
npm run dev
```

Apri: http://127.0.0.1:5173

## Uso con Colab

1. Analizza la clip in Colab.
2. Scarica lo zip output.
3. In Scout Lab usa "Importa zip Colab".
4. In alternativa estrai i file nella cartella `output/` del progetto e premi
   "Sincronizza output".

## Job locale

Per clip molto brevi puoi caricare il video e premere "Job locale breve". Su CPU
puo essere lento e non sostituisce Colab per analisi serie.

## OpenRouter

La lista modelli viene letta da `https://openrouter.ai/api/v1/models`.
Per generare insight reali inserisci la API key nel campo dedicato oppure imposta
la variabile:

```powershell
$env:OPENROUTER_API_KEY="..."
```

Senza API key, Scout Lab genera un fallback locale utile per testare il flusso.
