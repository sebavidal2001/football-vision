"""
Analisi Tattica Completa — Football Vision
-------------------------------------------
Un solo strumento: scegli una clip e ottieni
  1) il video con la mappa tattica 2D (radar automatico)
  2) le heatmap per giocatore e per squadra
  3) le statistiche per giocatore (CSV)

Tutto automatico: il campo viene riconosciuto da solo (nessuna calibrazione).
Su CPU è lento: usa clip BREVI (10-20 s). 'Salto' più alto = più veloce.
"""

import os
import sys
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

BASE = os.path.dirname(os.path.abspath(__file__))
CLIPS = os.path.join(BASE, "clips_input")
OUTPUT = os.path.join(BASE, "output")
RADAR = os.path.join(BASE, "vista_tattica", "genera_radar_auto.py")
STATS = os.path.join(BASE, "analisi", "stats_giocatori.py")
DASH = os.path.join(BASE, "analisi", "confronto_giocatori.py")
METRICHE = os.path.join(BASE, "analisi", "metriche_avanzate.py")
REPORTPDF = os.path.join(BASE, "analisi", "report_pdf.py")


class App:
    def __init__(self, root):
        self.root = root
        root.title("Analisi Tattica Completa — Football Vision")
        root.geometry("720x520")
        root.configure(padx=14, pady=12)
        self.video = ""

        ttk.Label(root, text="📊 Analisi Tattica Completa", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(root, text="Clip → radar 2D + heatmap per giocatore + statistiche.",
                  foreground="#555").pack(anchor="w", pady=(0, 10))

        r0 = ttk.Frame(root); r0.pack(fill="x", pady=4)
        ttk.Button(r0, text="📂 Scegli clip", command=self.scegli).pack(side="left")
        self.lbl = ttk.Label(r0, text="nessuna clip", foreground="#888"); self.lbl.pack(side="left", padx=8)

        r1 = ttk.Frame(root); r1.pack(fill="x", pady=4)
        ttk.Label(r1, text="Salto frame (2-5, più alto = più veloce):").pack(side="left")
        self.salto = ttk.Spinbox(r1, from_=1, to=8, width=5); self.salto.set(3); self.salto.pack(side="left", padx=6)
        ttk.Label(r1, text="Min. rilevazioni:").pack(side="left", padx=(16, 0))
        self.minr = ttk.Spinbox(r1, from_=5, to=60, width=5); self.minr.set(12); self.minr.pack(side="left", padx=6)
        ttk.Label(r1, text="Campo ogni N (clip lunghe):").pack(side="left", padx=(16, 0))
        self.ognic = ttk.Spinbox(r1, from_=1, to=6, width=5); self.ognic.set(2); self.ognic.pack(side="left", padx=6)

        self.btn = ttk.Button(root, text="▶  Avvia analisi completa", command=self.avvia)
        self.btn.pack(pady=8)

        self.log = tk.Text(root, height=18, wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)
        self.scrivi("Pronto. Scegli una clip breve e premi Avvia.\n"
                    "Nota: la prima volta carica i modelli (qualche secondo).")

    def scrivi(self, t):
        self.log.insert("end", t + "\n"); self.log.see("end"); self.root.update_idletasks()

    def scegli(self):
        f = filedialog.askopenfilename(initialdir=CLIPS, title="Scegli la clip",
                                       filetypes=[("Video", "*.mp4 *.mkv *.avi *.mov"), ("Tutti", "*.*")])
        if f:
            self.video = f
            self.lbl.config(text=os.path.basename(f), foreground="#000")

    def avvia(self):
        if not self.video:
            messagebox.showwarning("Manca la clip", "Scegli prima una clip.")
            return
        self.btn.config(state="disabled")
        self.log.delete("1.0", "end")
        threading.Thread(target=self.esegui, daemon=True).start()

    def _run(self, comando):
        proc = subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
        for linea in proc.stdout:
            linea = linea.rstrip()
            if linea and not any(s in linea for s in ("WARNING", "Speed:", "FutureWarning", "warnings.warn")):
                self.root.after(0, self.scrivi, linea)
        proc.wait()
        return proc.returncode

    def esegui(self):
        try:
            base = os.path.splitext(os.path.basename(self.video))[0]
            csv_pos = os.path.join(OUTPUT, f"POSIZIONIAUTO_{base}.csv")
            self.root.after(0, self.scrivi, "▶ FASE 1/2 — Radar 2D + rilevamento giocatori (lento su CPU)...")
            r = self._run([sys.executable, RADAR, self.video, "--salto", self.salto.get(),
                           "--ogni_campo", self.ognic.get(), "--imgsz", "1280"])
            if r != 0 or not os.path.exists(csv_pos):
                self.root.after(0, self.scrivi, "❌ Errore nella fase 1."); return
            self.root.after(0, self.scrivi, "\n▶ FASE 2/3 — Heatmap e statistiche per giocatore...")
            self._run([sys.executable, STATS, csv_pos, "--min_rilevazioni", self.minr.get()])
            stats_csv = os.path.join(OUTPUT, f"STATISTICHE_{base}.csv")
            self.root.after(0, self.scrivi, "\n▶ FASE 3/4 — Dashboard di confronto giocatori...")
            if os.path.exists(stats_csv):
                self._run([sys.executable, DASH, stats_csv])
            self.root.after(0, self.scrivi, "\n▶ FASE 4/5 — Metriche scouting (atletiche + tattiche)...")
            self._run([sys.executable, METRICHE, csv_pos, "--min_rilevazioni", self.minr.get()])
            self.root.after(0, self.scrivi, "\n▶ FASE 5/5 — Report PDF unico...")
            self._run([sys.executable, REPORTPDF, base, "--dir", OUTPUT])
            self.root.after(0, self.scrivi, "\n✅ FATTO! Risultati nella cartella 'output':")
            self.root.after(0, self.scrivi, f"   • Report PDF:   REPORT_COMPLETO_{base}.pdf")
            self.root.after(0, self.scrivi, f"   • Video radar:  RADARAUTO_{base}.mp4")
            self.root.after(0, self.scrivi, f"   • Heatmap:      heatmaps_{base}/")
            self.root.after(0, self.scrivi, f"   • Dashboard:    DASHBOARD_{base}.png")
            self.root.after(0, self.scrivi, f"   • Report scout: REPORT_{base}.png")
            self.root.after(0, self.scrivi, f"   • Dati: STATISTICHE / METRICHE_GIOCATORI / METRICHE_SQUADRE .csv")
            try:
                os.startfile(OUTPUT)
            except Exception:
                pass
        except Exception as e:
            self.root.after(0, self.scrivi, f"❌ Problema: {e}")
        finally:
            self.root.after(0, lambda: self.btn.config(state="normal"))


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
