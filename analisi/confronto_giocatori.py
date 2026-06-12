"""
confronto_giocatori.py — Dashboard di confronto giocatori (scouting).

Legge un file STATISTICHE_<clip>.csv e crea una dashboard PNG con:
  - Mappa delle POSIZIONI MEDIE sul campo (la "forma" delle squadre)
  - Classifica per AREA D'AZIONE (m²)
  - Classifica per DISTANZA percorsa (approssimata)

Uso:
  python confronto_giocatori.py <file_STATISTICHE.csv> [--top 12]
"""

import os
import sys
import csv
import argparse
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

L, W = 120.0, 70.0
COL = {1: "#1f6fff", 2: "#ff3b3b"}


def disegna_campo(ax):
    ax.set_xlim(-3, L + 3); ax.set_ylim(W + 3, -3)
    ax.set_aspect("equal"); ax.axis("off")
    ax.set_facecolor("#2e7d32")
    lc = dict(color="white", lw=1.2)
    ax.plot([0, L, L, 0, 0], [0, 0, W, W, 0], **lc)
    ax.plot([L/2, L/2], [0, W], **lc)
    circ = plt.Circle((L/2, W/2), 9.15, fill=False, **lc); ax.add_patch(circ)
    for x0 in (0, L):
        s = 1 if x0 == 0 else -1
        ax.plot([x0, x0 + s*20.15, x0 + s*20.15, x0], [14.5, 14.5, 55.5, 55.5], **lc)
        ax.plot([x0, x0 + s*5.5, x0 + s*5.5, x0], [25.84, 25.84, 44.16, 44.16], **lc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    righe = list(csv.DictReader(open(args.csv, encoding="utf-8")))
    if not righe:
        print("Nessun dato nel file."); return
    for r in righe:
        r["squadra"] = int(r["squadra"])
        for k in ("x_medio", "y_medio", "area_azione_m2", "distanza_m_approx", "n_rilevazioni"):
            r[k] = float(r[k])

    base = os.path.splitext(os.path.basename(args.csv))[0].replace("STATISTICHE_", "")
    out = os.path.join(os.path.dirname(os.path.abspath(args.csv)), f"DASHBOARD_{base}.png")

    fig = plt.figure(figsize=(16, 8))
    fig.suptitle(f"Confronto giocatori — {base}", fontsize=15, fontweight="bold")

    # 1) Mappa posizioni medie
    ax1 = fig.add_subplot(1, 2, 1)
    disegna_campo(ax1)
    ax1.set_title("Posizione media in campo (forma squadre)")
    for r in righe:
        ax1.scatter(r["x_medio"], r["y_medio"], s=260, c=COL.get(r["squadra"], "#888"),
                    edgecolors="black", zorder=3)
        ax1.text(r["x_medio"], r["y_medio"], str(int(float(r["id_giocatore"]))),
                 color="white", fontsize=7, ha="center", va="center", zorder=4, fontweight="bold")

    # 2) Classifiche (barre)
    top = sorted(righe, key=lambda r: -r["area_azione_m2"])[:args.top]
    ax2 = fig.add_subplot(2, 2, 2)
    et = [f"#{int(float(r['id_giocatore']))} (S{r['squadra']})" for r in top]
    ax2.barh(et, [r["area_azione_m2"] for r in top],
             color=[COL.get(r["squadra"], "#888") for r in top])
    ax2.invert_yaxis(); ax2.set_title("Area d'azione (m²) — chi copre più campo")
    ax2.tick_params(labelsize=8)

    topd = sorted(righe, key=lambda r: -r["distanza_m_approx"])[:args.top]
    ax3 = fig.add_subplot(2, 2, 4)
    etd = [f"#{int(float(r['id_giocatore']))} (S{r['squadra']})" for r in topd]
    ax3.barh(etd, [r["distanza_m_approx"] for r in topd],
             color=[COL.get(r["squadra"], "#888") for r in topd])
    ax3.invert_yaxis(); ax3.set_title("Distanza percorsa (m, approx.) — più dinamici")
    ax3.tick_params(labelsize=8)

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out, dpi=110)
    print(f"Giocatori confrontati: {len(righe)}")
    print(f"Dashboard salvata: {out}")


if __name__ == "__main__":
    main()
