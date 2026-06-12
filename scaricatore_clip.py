"""
Scaricatore Clip — Football Vision
-----------------------------------
Finestra semplice per scaricare uno spezzone da un video YouTube.
1. Incolli il link
2. Scegli inizio e fine (formato mm:ss oppure h:mm:ss)
3. Scegli la risoluzione
4. Premi "Scarica"

Le clip vengono salvate nella cartella  clips_input/  accanto a questo file.
"""

import os
import re
import sys
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox

# Cartella dove salvare le clip (clips_input accanto a questo script)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "clips_input")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Risoluzione -> altezza massima
RISOLUZIONI = {
    "360p (leggera, veloce)": 360,
    "480p (consigliata)": 480,
    "720p (buona qualità)": 720,
    "1080p (alta)": 1080,
    "1440p / 2K (se disponibile)": 1440,
    "2160p / 4K (se disponibile)": 2160,
    "Massima disponibile": 99999,
}


def _trova_node():
    """True se Node è installato (serve a sbloccare 720p/1080p a piena velocità)."""
    import shutil
    return shutil.which("node") is not None


def normalizza_tempo(testo):
    """Accetta '90', '1:30', '01:30', '1:02:03' e restituisce 'HH:MM:SS'."""
    testo = testo.strip()
    if not testo:
        raise ValueError("tempo vuoto")
    if testo.isdigit():  # solo secondi
        s = int(testo)
        return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"
    parti = testo.split(":")
    if not all(p.isdigit() for p in parti):
        raise ValueError(f"tempo non valido: {testo}")
    parti = [int(p) for p in parti]
    while len(parti) < 3:
        parti.insert(0, 0)
    h, m, s = parti[-3], parti[-2], parti[-1]
    return f"{h:02d}:{m:02d}:{s:02d}"


def tempo_in_secondi(hhmmss):
    h, m, s = (int(x) for x in hhmmss.split(":"))
    return h * 3600 + m * 60 + s


def nome_file_sicuro(testo):
    testo = re.sub(r"[^\w\-]+", "_", testo).strip("_")
    return testo[:50] if testo else "clip"


class App:
    def __init__(self, root):
        self.root = root
        root.title("Scaricatore Clip — Football Vision")
        root.geometry("640x520")
        root.configure(padx=16, pady=12)

        ttk.Label(root, text="⚽ Scaricatore Clip", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(root, text="Scarica uno spezzone da YouTube per l'analisi.",
                  foreground="#555").pack(anchor="w", pady=(0, 12))

        # Link
        ttk.Label(root, text="Link YouTube:").pack(anchor="w")
        self.url = ttk.Entry(root, width=80)
        self.url.pack(fill="x", pady=(0, 10))

        # Inizio / Fine
        riga = ttk.Frame(root)
        riga.pack(fill="x", pady=(0, 10))
        ttk.Label(riga, text="Inizio (mm:ss):").grid(row=0, column=0, sticky="w")
        self.inizio = ttk.Entry(riga, width=12)
        self.inizio.insert(0, "00:00")
        self.inizio.grid(row=0, column=1, padx=(6, 24))
        ttk.Label(riga, text="Fine (mm:ss):").grid(row=0, column=2, sticky="w")
        self.fine = ttk.Entry(riga, width=12)
        self.fine.insert(0, "00:30")
        self.fine.grid(row=0, column=3, padx=(6, 0))

        # Risoluzione
        riga2 = ttk.Frame(root)
        riga2.pack(fill="x", pady=(0, 10))
        ttk.Label(riga2, text="Risoluzione:").grid(row=0, column=0, sticky="w")
        self.risoluzione = ttk.Combobox(riga2, values=list(RISOLUZIONI.keys()),
                                        state="readonly", width=28)
        self.risoluzione.current(1)  # 480p
        self.risoluzione.grid(row=0, column=1, padx=(6, 0))

        # Bottone
        self.btn = ttk.Button(root, text="⬇  Scarica clip", command=self.avvia)
        self.btn.pack(pady=(4, 6))

        # Riga di avanzamento (si aggiorna in tempo reale)
        self.progresso = ttk.Label(root, text="", foreground="#0066cc",
                                   font=("Consolas", 9))
        self.progresso.pack(anchor="w", pady=(0, 6))

        # Log
        ttk.Label(root, text="Stato:").pack(anchor="w")
        self.log = tk.Text(root, height=12, wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)
        self.scrivi(f"Le clip verranno salvate in:\n{OUTPUT_DIR}\n")
        self.scrivi("\nSuggerimento: se YouTube rallenta, prova una risoluzione più bassa.\n")

    def scrivi(self, testo):
        self.log.insert("end", testo + ("\n" if not testo.endswith("\n") else ""))
        self.log.see("end")
        self.root.update_idletasks()

    def aggiorna_progresso(self, testo):
        # Mostra l'ultima riga di avanzamento (download % oppure scorrimento ffmpeg)
        self.progresso.config(text=testo[:90])
        self.root.update_idletasks()

    def avvia(self):
        url = self.url.get().strip()
        if not url:
            messagebox.showwarning("Manca il link", "Incolla un link YouTube.")
            return
        try:
            inizio = normalizza_tempo(self.inizio.get())
            fine = normalizza_tempo(self.fine.get())
        except ValueError:
            messagebox.showerror("Tempo non valido",
                                 "Usa il formato mm:ss (es. 01:30) oppure h:mm:ss.")
            return
        if tempo_in_secondi(fine) <= tempo_in_secondi(inizio):
            messagebox.showerror("Intervallo errato", "La fine deve venire dopo l'inizio.")
            return

        altezza = RISOLUZIONI[self.risoluzione.get()]
        self.btn.config(state="disabled")
        self.log.delete("1.0", "end")
        durata = tempo_in_secondi(fine) - tempo_in_secondi(inizio)
        self.scrivi(f"Scarico {durata}s ({inizio} → {fine}) a {altezza}p...")
        if tempo_in_secondi(inizio) > 120:
            self.scrivi("⚠ Nota: lo spezzone è lontano dall'inizio del video,\n"
                        "   il download può richiedere più tempo.")
        threading.Thread(target=self.scarica, args=(url, inizio, fine, altezza),
                         daemon=True).start()

    def scarica(self, url, inizio, fine, altezza):
        nome = os.path.join(OUTPUT_DIR, f"clip_%(title).40s_{altezza}p.mp4")
        comando = [
            sys.executable, "-m", "yt_dlp",
            "-N", "4",                       # 4 download in parallelo
            "--download-sections", f"*{inizio}-{fine}",
            "-f", f"bestvideo[height<={altezza}]+bestaudio/best[height<={altezza}]",
            "--merge-output-format", "mp4",
            "--newline",
            "--restrict-filenames",
            "-o", nome,
            url,
        ]
        # Motore JavaScript (Node) = sblocca le risoluzioni alte a piena velocità.
        # Senza, YouTube limita il download del client web.
        if _trova_node():
            comando[2:2] = ["--js-runtimes", "node"]
        try:
            proc = subprocess.Popen(comando, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True,
                                    encoding="utf-8", errors="replace")
            for linea in proc.stdout:
                linea = linea.rstrip()
                # Avanzamento "in tempo reale": aggiorna la riga di stato in basso
                if "[download]" in linea or linea.startswith("frame=") or "time=" in linea:
                    self.root.after(0, self.aggiorna_progresso, linea)
                # Messaggi importanti: vanno nel log
                if any(k in linea for k in ("Destination:", "Merging", "ERROR", "time ranges")):
                    self.root.after(0, self.scrivi, linea)
            proc.wait()
            if proc.returncode == 0:
                self.root.after(0, self.scrivi, "\n✅ FATTO! Clip salvata nella cartella clips_input.")
                self.root.after(0, lambda: messagebox.showinfo(
                    "Completato", "Download riuscito!\nLa clip è in clips_input."))
            else:
                self.root.after(0, self.scrivi,
                                f"\n❌ Errore (codice {proc.returncode}). Prova risoluzione più bassa.")
        except Exception as e:
            self.root.after(0, self.scrivi, f"\n❌ Problema: {e}")
        finally:
            self.root.after(0, lambda: self.btn.config(state="normal"))


def assicura_ytdlp():
    """Installa yt-dlp se manca."""
    try:
        import yt_dlp  # noqa
        return True
    except ImportError:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "yt-dlp"])
            return True
        except Exception:
            return False


if __name__ == "__main__":
    if not assicura_ytdlp():
        print("Impossibile installare yt-dlp. Apri il terminale e digita: pip install yt-dlp")
        input("Premi Invio per chiudere...")
        sys.exit(1)
    root = tk.Tk()
    App(root)
    root.mainloop()
