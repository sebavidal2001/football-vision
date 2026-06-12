"""
calibra_campo.py — Calibrazione manuale del campo (homography).

Come si usa:
  1. Scegli il video e il secondo da cui prendere il fotogramma.
  2. Dal menu scegli un punto noto del campo (es. "Angolo area SX - angolo alto").
  3. Clicca sull'immagine dove si trova quel punto.
  4. Ripeti per ALMENO 4 punti BEN DISTRIBUITI (non tutti in fila!).
  5. Premi "Calcola e salva": viene salvata la trasformazione (file .json)
     e mostrata un'anteprima della mappa 2D.

Consiglio: scegli un fotogramma dove si vede bene un'area di rigore
(così hai punti sparsi: angoli area + linea di metà campo + cerchio).
"""

import os
import sys
import json
import numpy as np
import cv2
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import campo_calcio as cc

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIPS_DIR = os.path.join(BASE_DIR, "clips_input")
CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibrazioni")
os.makedirs(CONFIG_DIR, exist_ok=True)

MAX_W = 1000  # larghezza massima di visualizzazione del fotogramma


class App:
    def __init__(self, root):
        self.root = root
        root.title("Calibrazione Campo — Vista Tattica 2D")
        self.frame_bgr = None      # fotogramma originale
        self.scala = 1.0           # fattore di scala visualizzazione
        self.video_path = ""
        self.punti = []            # lista di (nome, (px_orig, py_orig))
        self.tk_img = None

        # --- Barra superiore: scelta video + secondo ---
        top = ttk.Frame(root, padding=8)
        top.pack(fill="x")
        ttk.Button(top, text="📂 Scegli video", command=self.scegli_video).pack(side="left")
        self.lbl_video = ttk.Label(top, text="nessun video", foreground="#888")
        self.lbl_video.pack(side="left", padx=8)
        ttk.Label(top, text="Secondo:").pack(side="left", padx=(12, 2))
        self.sec = ttk.Entry(top, width=8)
        self.sec.insert(0, "0")
        self.sec.pack(side="left")
        ttk.Button(top, text="Carica fotogramma", command=self.carica_frame).pack(side="left", padx=8)

        # --- Barra punto: scelta landmark ---
        mid = ttk.Frame(root, padding=(8, 0))
        mid.pack(fill="x")
        ttk.Label(mid, text="Punto da posizionare:").pack(side="left")
        self.combo = ttk.Combobox(mid, values=list(cc.PUNTI_CAMPO.keys()),
                                  state="readonly", width=32)
        self.combo.pack(side="left", padx=6)
        if self.combo["values"]:
            self.combo.current(0)
        ttk.Button(mid, text="↩ Annulla ultimo", command=self.annulla_ultimo).pack(side="left", padx=4)
        ttk.Button(mid, text="✅ Calcola e salva", command=self.calcola).pack(side="left", padx=4)
        self.lbl_stato = ttk.Label(mid, text="punti: 0/4", foreground="#0066cc")
        self.lbl_stato.pack(side="left", padx=10)

        # --- Canvas immagine ---
        self.canvas = tk.Canvas(root, bg="#222", width=MAX_W, height=560)
        self.canvas.pack(padx=8, pady=8)
        self.canvas.bind("<Button-1>", self.click)

        self.aiuto = ttk.Label(root, foreground="#555",
            text="1) Scegli video e secondo  2) Carica fotogramma  "
                 "3) Per ogni punto: scegli dal menu e clicca sull'immagine  "
                 "4) Almeno 4 punti distribuiti  5) Calcola e salva")
        self.aiuto.pack(pady=(0, 8))

    # ---------- gestione video / frame ----------
    def scegli_video(self):
        f = filedialog.askopenfilename(initialdir=CLIPS_DIR, title="Scegli video",
                                       filetypes=[("Video", "*.mp4 *.mkv *.webm *.avi *.mov"),
                                                  ("Tutti", "*.*")])
        if f:
            self.video_path = f
            self.lbl_video.config(text=os.path.basename(f), foreground="#000")

    def carica_frame(self):
        if not self.video_path:
            messagebox.showwarning("Manca il video", "Scegli prima un video.")
            return
        try:
            sec = float(self.sec.get())
        except ValueError:
            messagebox.showerror("Errore", "Il secondo dev'essere un numero (es. 5 o 12.5).")
            return
        cap = cv2.VideoCapture(self.video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(sec * fps))
        ok, frame = cap.read()
        cap.release()
        if not ok:
            messagebox.showerror("Errore", "Impossibile leggere quel fotogramma.")
            return
        self.frame_bgr = frame
        self.punti = []
        self.mostra_frame()
        self.aggiorna_stato()

    def mostra_frame(self):
        h, w = self.frame_bgr.shape[:2]
        self.scala = min(1.0, MAX_W / w)
        disp = cv2.resize(self.frame_bgr, (int(w * self.scala), int(h * self.scala)))
        rgb = cv2.cvtColor(disp, cv2.COLOR_BGR2RGB)
        self.canvas.config(width=rgb.shape[1], height=rgb.shape[0])
        self.tk_img = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_img)
        self.ridisegna_punti()

    def ridisegna_punti(self):
        for i, (nome, (px, py)) in enumerate(self.punti, 1):
            x, y = px * self.scala, py * self.scala
            self.canvas.create_oval(x-5, y-5, x+5, y+5, fill="yellow", outline="black")
            self.canvas.create_text(x+8, y, anchor="w", text=f"{i}. {nome}",
                                    fill="yellow", font=("Segoe UI", 8, "bold"))

    # ---------- click ----------
    def click(self, ev):
        if self.frame_bgr is None:
            return
        nome = self.combo.get()
        if not nome:
            return
        px, py = int(ev.x / self.scala), int(ev.y / self.scala)
        # se il punto era già stato messo, lo sostituisce
        self.punti = [p for p in self.punti if p[0] != nome]
        self.punti.append((nome, (px, py)))
        self.mostra_frame()
        self.aggiorna_stato()
        # avanza automaticamente al prossimo punto del menu
        vals = list(self.combo["values"])
        i = vals.index(nome)
        if i + 1 < len(vals):
            self.combo.current(i + 1)

    def annulla_ultimo(self):
        if self.punti:
            self.punti.pop()
            self.mostra_frame()
            self.aggiorna_stato()

    def aggiorna_stato(self):
        n = len(self.punti)
        if n < 4:
            self.lbl_stato.config(text=f"punti: {n}/4 (servono almeno 4)", foreground="#0066cc")
            return
        # Controllo dal vivo: calcola errore e segnala il punto peggiore
        src = np.array([[px, py] for _, (px, py) in self.punti], dtype=np.float32)
        dst = np.array([cc.PUNTI_CAMPO[nm] for nm, _ in self.punti], dtype=np.float32)
        H, _ = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
        if H is None:
            self.lbl_stato.config(text=f"punti: {n}  ⚠ punti troppo in fila", foreground="#cc0000")
            return
        proj = cv2.perspectiveTransform(src.reshape(-1, 1, 2), H).reshape(-1, 2)
        errs = np.linalg.norm(proj - dst, axis=1)
        em = float(errs.mean())
        i_peggio = int(errs.argmax())
        if em < 2:
            self.lbl_stato.config(text=f"punti: {n}  ✓ errore {em:.1f} m — OTTIMO", foreground="#00a000")
        elif em < 4:
            self.lbl_stato.config(text=f"punti: {n}  errore {em:.1f} m — ok", foreground="#88aa00")
        else:
            peggio = self.punti[i_peggio][0]
            self.lbl_stato.config(
                text=f"punti: {n}  ⚠ errore {em:.1f} m — controlla: «{peggio}»",
                foreground="#cc0000")

    # ---------- calcolo homography ----------
    def calcola(self):
        if len(self.punti) < 4:
            messagebox.showwarning("Servono più punti", "Metti almeno 4 punti del campo.")
            return
        src = np.array([[px, py] for _, (px, py) in self.punti], dtype=np.float32)
        dst = np.array([cc.PUNTI_CAMPO[nome] for nome, _ in self.punti], dtype=np.float32)
        H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
        if H is None:
            messagebox.showerror("Errore",
                "Calcolo fallito. Probabilmente i punti sono troppo in fila: "
                "scegline di più sparsi (angoli area + metà campo).")
            return

        # Salva
        nome_file = os.path.splitext(os.path.basename(self.video_path))[0]
        out_json = os.path.join(CONFIG_DIR, f"calib_{nome_file}.json")
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump({
                "video": os.path.basename(self.video_path),
                "secondo": float(self.sec.get()),
                "homography": H.tolist(),
                "punti": [{"nome": n, "px": p[0], "py": p[1]} for n, p in self.punti],
            }, f, indent=2, ensure_ascii=False)

        # Anteprima: proietta i punti cliccati sulla mappa per verificare
        self.anteprima(H)
        messagebox.showinfo("Salvato",
            f"Calibrazione salvata!\n{os.path.basename(out_json)}\n\n"
            "Controlla l'anteprima: i punti gialli devono cadere sui punti giusti del campo.\n"
            "Se sono storti, ricarica il fotogramma e rifai i click con più precisione.")

    def anteprima(self, H):
        mappa = cc.disegna_campo()
        # proietta tutti i giocatori? Qui mostriamo i punti cliccati (verifica bontà)
        pts = np.array([[[px, py]] for _, (px, py) in self.punti], dtype=np.float32)
        proj = cv2.perspectiveTransform(pts, H).reshape(-1, 2)
        posizioni = [(x, y, (0, 255, 255)) for x, y in proj]
        mappa = cc.disegna_giocatori(mappa, posizioni)
        out = os.path.join(CONFIG_DIR, "_anteprima_calibrazione.png")
        cv2.imwrite(out, mappa)
        win = cv2.imread(out)
        cv2.imshow("Anteprima calibrazione (chiudi con un tasto)", win)
        cv2.waitKey(1)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
