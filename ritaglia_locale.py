"""
Ritaglia Clip in Locale — Football Vision
------------------------------------------
Lavora su un video GIA' scaricato sul tuo PC. Il taglio è ISTANTANEO,
da qualsiasi minuto, quante volte vuoi (non riscarica niente).

Flusso consigliato:
  1. Scarica UNA volta la partita intera (anche con lo Scaricatore Clip
     mettendo inizio 00:00 e fine alla durata totale, oppure a mano).
  2. Apri questo programma, scegli il file, e ritaglia gli spezzoni che vuoi.

Le clip ritagliate vengono salvate in  clips_input/
"""

import os
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "clips_input")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def normalizza_tempo(testo):
    testo = testo.strip()
    if not testo:
        raise ValueError("vuoto")
    if testo.isdigit():
        s = int(testo)
        return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"
    parti = testo.split(":")
    if not all(p.isdigit() for p in parti):
        raise ValueError("non valido")
    parti = [int(p) for p in parti]
    while len(parti) < 3:
        parti.insert(0, 0)
    return f"{parti[-3]:02d}:{parti[-2]:02d}:{parti[-1]:02d}"


def secondi(hhmmss):
    h, m, s = (int(x) for x in hhmmss.split(":"))
    return h * 3600 + m * 60 + s


class App:
    def __init__(self, root):
        self.root = root
        root.title("Ritaglia Clip in Locale — Football Vision")
        root.geometry("640x420")
        root.configure(padx=16, pady=12)
        self.file_video = ""

        ttk.Label(root, text="✂ Ritaglia Clip (istantaneo)",
                  font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(root, text="Taglia spezzoni da un video già sul tuo PC. Nessun download.",
                  foreground="#555").pack(anchor="w", pady=(0, 12))

        # Scelta file
        riga0 = ttk.Frame(root)
        riga0.pack(fill="x", pady=(0, 10))
        ttk.Button(riga0, text="📂 Scegli il video...", command=self.scegli_file).pack(side="left")
        self.lbl_file = ttk.Label(riga0, text="nessun file scelto", foreground="#888")
        self.lbl_file.pack(side="left", padx=10)

        # Inizio / Fine
        riga = ttk.Frame(root)
        riga.pack(fill="x", pady=(0, 10))
        ttk.Label(riga, text="Inizio (mm:ss):").grid(row=0, column=0, sticky="w")
        self.inizio = ttk.Entry(riga, width=12)
        self.inizio.insert(0, "11:20")
        self.inizio.grid(row=0, column=1, padx=(6, 24))
        ttk.Label(riga, text="Fine (mm:ss):").grid(row=0, column=2, sticky="w")
        self.fine = ttk.Entry(riga, width=12)
        self.fine.insert(0, "11:40")
        self.fine.grid(row=0, column=3, padx=(6, 0))

        self.btn = ttk.Button(root, text="✂  Ritaglia", command=self.avvia)
        self.btn.pack(pady=(4, 10))

        ttk.Label(root, text="Stato:").pack(anchor="w")
        self.log = tk.Text(root, height=10, wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)
        self.scrivi(f"Le clip ritagliate finiscono in:\n{OUTPUT_DIR}\n")

    def scrivi(self, t):
        self.log.insert("end", t + ("\n" if not t.endswith("\n") else ""))
        self.log.see("end")
        self.root.update_idletasks()

    def scegli_file(self):
        f = filedialog.askopenfilename(
            initialdir=OUTPUT_DIR,
            title="Scegli il video da cui ritagliare",
            filetypes=[("Video", "*.mp4 *.mkv *.webm *.avi *.mov"), ("Tutti", "*.*")])
        if f:
            self.file_video = f
            self.lbl_file.config(text=os.path.basename(f), foreground="#000")
            self.scrivi(f"Video scelto: {os.path.basename(f)}")

    def avvia(self):
        if not self.file_video:
            messagebox.showwarning("Manca il video", "Scegli prima un file video.")
            return
        try:
            ini = normalizza_tempo(self.inizio.get())
            fin = normalizza_tempo(self.fine.get())
        except ValueError:
            messagebox.showerror("Tempo non valido", "Usa il formato mm:ss (es. 11:20).")
            return
        if secondi(fin) <= secondi(ini):
            messagebox.showerror("Intervallo errato", "La fine deve venire dopo l'inizio.")
            return
        self.btn.config(state="disabled")
        threading.Thread(target=self.taglia, args=(ini, fin), daemon=True).start()

    def taglia(self, ini, fin):
        dur = secondi(fin) - secondi(ini)
        base = os.path.splitext(os.path.basename(self.file_video))[0][:30]
        out = os.path.join(OUTPUT_DIR, f"taglio_{base}_{ini.replace(':','')}-{fin.replace(':','')}.mp4")
        self.root.after(0, self.scrivi, f"\nRitaglio {dur}s ({ini} → {fin})... (istantaneo)")
        # -ss prima di -i = seek veloce; -c copy = nessuna ricodifica (immediato)
        comando = ["ffmpeg", "-y", "-ss", ini, "-i", self.file_video,
                   "-t", str(dur), "-c", "copy", "-avoid_negative_ts", "make_zero", out]
        try:
            r = subprocess.run(comando, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace")
            if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 1000:
                mb = os.path.getsize(out) / 1e6
                self.root.after(0, self.scrivi, f"✅ FATTO! ({mb:.1f} MB)\n   {os.path.basename(out)}")
                self.root.after(0, lambda: messagebox.showinfo("Completato",
                    "Clip ritagliata!\nÈ in clips_input."))
            else:
                # Fallback con ricodifica (più lento ma robusto se -c copy fallisce)
                self.root.after(0, self.scrivi, "   taglio rapido fallito, riprovo con ricodifica...")
                comando2 = ["ffmpeg", "-y", "-ss", ini, "-i", self.file_video,
                            "-t", str(dur), "-c:v", "libx264", "-preset", "veryfast",
                            "-c:a", "aac", out]
                r2 = subprocess.run(comando2, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace")
                if r2.returncode == 0:
                    self.root.after(0, self.scrivi, f"✅ FATTO (con ricodifica)\n   {os.path.basename(out)}")
                else:
                    self.root.after(0, self.scrivi, "❌ Errore nel ritaglio.")
        except FileNotFoundError:
            self.root.after(0, self.scrivi, "❌ ffmpeg non trovato sul sistema.")
        except Exception as e:
            self.root.after(0, self.scrivi, f"❌ Problema: {e}")
        finally:
            self.root.after(0, lambda: self.btn.config(state="normal"))


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
