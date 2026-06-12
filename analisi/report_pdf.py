"""
report_pdf.py — Assembla tutti gli output in un unico REPORT PDF per partita.

Mette insieme: copertina con riepilogo squadre, formazione, andamento tattico,
report scouting, dashboard confronto, heatmap squadre.

Uso:
  python report_pdf.py <base>            (es. clip_input)  [--dir output]
  oppure: python report_pdf.py <output/METRICHE_SQUADRE_xxx.csv>
"""

import os
import sys
import csv
import glob
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import argparse
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


def pagina_immagine(pdf, path, titolo=None):
    if not path or not os.path.exists(path):
        return
    img = plt.imread(path)
    h, w = img.shape[:2]
    fig = plt.figure(figsize=(11.7, 8.3))   # A4 orizzontale
    ax = fig.add_axes([0.03, 0.03, 0.94, 0.90])
    ax.imshow(img); ax.axis("off")
    if titolo:
        fig.suptitle(titolo, fontsize=14, fontweight="bold", y=0.98)
    pdf.savefig(fig); plt.close(fig)


def copertina(pdf, base, squadre_csv):
    fig = plt.figure(figsize=(11.7, 8.3)); ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off")
    ax.text(0.5, 0.92, "REPORT SCOUTING", ha="center", fontsize=26, fontweight="bold")
    ax.text(0.5, 0.86, base, ha="center", fontsize=14, color="#555")
    righe = []
    if os.path.exists(squadre_csv):
        righe = list(csv.DictReader(open(squadre_csv, encoding="utf-8")))
    y = 0.74
    intest = ["", "Squadra 1", "Squadra 2"]
    campi = [("Modulo", "modulo"), ("Possesso %", "possesso_pct"),
             ("Ampiezza (m)", "ampiezza_media_m"), ("Profondità (m)", "profondita_media_m"),
             ("Compattezza (m)", "compattezza_media_m"),
             ("Baricentro con palla", "baricentro_con_palla_m"),
             ("Baricentro senza palla", "baricentro_senza_palla_m")]
    def val(sq, k):
        for r in righe:
            if r.get("squadra") == str(sq):
                return r.get(k, "-")
        return "-"
    ax.text(0.30, y, intest[1], fontsize=12, fontweight="bold", ha="center", color="#1f6fff")
    ax.text(0.62, y, intest[2], fontsize=12, fontweight="bold", ha="center", color="#ff3b3b")
    y -= 0.05
    for etich, k in campi:
        ax.text(0.08, y, etich, fontsize=11)
        ax.text(0.30, y, str(val(1, k)), fontsize=11, ha="center")
        ax.text(0.62, y, str(val(2, k)), fontsize=11, ha="center")
        y -= 0.045
    ax.text(0.5, 0.12,
            "Legenda affidabilità: metriche TATTICHE e di POSIZIONE = affidabili da broadcast.\n"
            "Metriche ATLETICHE per-giocatore = INDICATIVE (limite del broadcast: giocatori fuori campo).",
            ha="center", fontsize=9, color="#666",
            bbox=dict(boxstyle="round", fc="#f3f3f3", ec="#ccc"))
    pdf.savefig(fig); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base_o_csv")
    ap.add_argument("--dir", default="output")
    args = ap.parse_args()

    arg = args.base_o_csv
    if arg.endswith(".csv"):
        out_dir = os.path.dirname(os.path.abspath(arg))
        base = os.path.basename(arg).replace("METRICHE_SQUADRE_", "").replace(".csv", "")
    else:
        out_dir = os.path.abspath(args.dir)
        base = arg
    sq_csv = os.path.join(out_dir, f"METRICHE_SQUADRE_{base}.csv")
    pdf_path = os.path.join(out_dir, f"REPORT_COMPLETO_{base}.pdf")

    def trova(pattern):
        f = glob.glob(os.path.join(out_dir, pattern))
        return f[0] if f else None

    with PdfPages(pdf_path) as pdf:
        copertina(pdf, base, sq_csv)
        pagina_immagine(pdf, trova(f"FORMAZIONE_{base}.png"), "Formazione / Modulo (tattico)")
        pagina_immagine(pdf, trova(f"ANDAMENTO_{base}.png"), "Andamento tattico nel tempo")
        pagina_immagine(pdf, trova(f"REPORT_{base}.png"), "Report scouting")
        pagina_immagine(pdf, trova(f"DASHBOARD_{base}.png"), "Confronto giocatori")
        for hp in [os.path.join(out_dir, f"heatmaps_{base}", "_SQUADRA_1.png"),
                   os.path.join(out_dir, f"heatmaps_{base}", "_SQUADRA_2.png")]:
            pagina_immagine(pdf, hp if os.path.exists(hp) else None, "Heatmap di squadra")

    print(f"✅ Report PDF: {pdf_path}")


if __name__ == "__main__":
    main()
