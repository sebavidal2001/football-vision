"""
stats_giocatori.py — Heatmap e statistiche per giocatore, dal file POSIZIONI.

Legge un CSV prodotto dal radar (frame, tempo_s, id_giocatore, squadra, x_m, y_m)
e produce:
  - STATISTICHE_<clip>.csv : una riga per giocatore (distanza, velocità, ...)
  - cartella heatmaps_<clip>/ : una heatmap PNG per ogni giocatore + per squadra

Uso:
  python stats_giocatori.py <file_POSIZIONI.csv> [--min_rilevazioni 15]

Nota onesta: gli "id giocatore" sono gli ID del tracking. Su clip brevi e con
camera in movimento il tracking può spezzare un giocatore in più ID: le stats
sono quindi per "traccia", una buona approssimazione su spezzoni brevi.
"""

import os
import sys
import csv
import argparse
from collections import defaultdict
import numpy as np
import cv2

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vista_tattica"))
import campo_calcio as cc

VEL_MAX_PLAUSIBILE = 10.0   # m/s (~36 km/h): oltre = salto del tracking, ignorato


def smussa(a, finestra=5):
    """Media mobile per togliere il tremolio dalla traiettoria."""
    a = np.asarray(a, dtype=float)
    if len(a) < finestra:
        return a
    k = np.ones(finestra) / finestra
    s = np.convolve(a, k, mode="same")
    # ripara i bordi (il convolve 'same' li attenua)
    h = finestra // 2
    s[:h] = a[:h]
    s[-h:] = a[-h:]
    return s


def carica(csv_path):
    dati = defaultdict(list)   # id -> lista di (tempo, x, y, squadra)
    with open(csv_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            dati[int(r["id_giocatore"])].append(
                (float(r["tempo_s"]), float(r["x_m"]), float(r["y_m"]), int(r["squadra"])))
    for k in dati:
        dati[k].sort()
    return dati


def statistiche_giocatore(tracce):
    """Calcola distanza, velocità media/max, posizione media da una lista ordinata."""
    t = np.array([p[0] for p in tracce])
    xr = np.array([p[1] for p in tracce])
    yr = np.array([p[2] for p in tracce])
    x = smussa(xr, 9)   # traiettoria smussata (anti-tremolio)
    y = smussa(yr, 9)
    squadra = max(set(p[3] for p in tracce), key=[p[3] for p in tracce].count)

    # Spostamenti su intervalli di ~0.5 s: il movimento reale supera il rumore.
    DT_MIN = 0.5
    dist_tot = 0.0
    vels = []
    last = 0
    for i in range(1, len(t)):
        dt = t[i] - t[last]
        if dt < DT_MIN:
            continue
        d = float(np.hypot(x[i]-x[last], y[i]-y[last]))
        v = d / dt
        if v <= VEL_MAX_PLAUSIBILE:
            dist_tot += d
            vels.append(v)
        last = i
    vels = np.array(vels) if vels else np.array([0.0])

    # Metriche di posizione (AFFIDABILI anche da broadcast)
    x_med = float(np.median(xr))
    y_med = float(np.median(yr))
    # area d'azione: rettangolo tra i percentili 10-90 (esclude gli sbalzi)
    larg_x = float(np.percentile(xr, 90) - np.percentile(xr, 10))
    larg_y = float(np.percentile(yr, 90) - np.percentile(yr, 10))
    meta = "attacco (dx)" if x_med > 66 else ("difesa (sx)" if x_med < 54 else "centrocampo")

    return {
        "squadra": squadra,
        "n_rilevazioni": len(tracce),
        "durata_s": round(float(t[-1] - t[0]), 1),
        "x_medio": round(x_med, 1),
        "y_medio": round(y_med, 1),
        "zona": meta,
        "area_azione_m2": round(larg_x * larg_y),
        "distanza_m_approx": round(dist_tot),
        "vel_media_kmh_approx": round(float(vels.mean()) * 3.6, 1),
        "vel_max_kmh_approx": round(float(vels.max()) * 3.6, 1),
    }


def heatmap(tracce, titolo, out_path):
    """Disegna una heatmap delle posizioni sopra il campo."""
    campo = cc.disegna_campo()
    h, w = campo.shape[:2]
    griglia = np.zeros((h, w), dtype=np.float32)
    for _, x, y, _ in tracce:
        px, py = cc.metri_a_pixel(x, y)
        if 0 <= px < w and 0 <= py < h:
            griglia[py, px] += 1
    if griglia.max() > 0:
        griglia = cv2.GaussianBlur(griglia, (0, 0), sigmaX=18)
        griglia = (griglia / griglia.max() * 255).astype(np.uint8)
        heat = cv2.applyColorMap(griglia, cv2.COLORMAP_JET)
        mask = (griglia > 12).astype(np.float32)[..., None]
        out = (campo * (1 - 0.65 * mask) + heat * (0.65 * mask)).astype(np.uint8)
    else:
        out = campo
    cv2.putText(out, titolo, (30, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.imwrite(out_path, out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--min_rilevazioni", type=int, default=15)
    args = ap.parse_args()

    base = os.path.splitext(os.path.basename(args.csv))[0].replace("POSIZIONIAUTO_", "").replace("POSIZIONI_", "")
    out_dir = os.path.dirname(os.path.abspath(args.csv))
    heat_dir = os.path.join(out_dir, f"heatmaps_{base}")
    os.makedirs(heat_dir, exist_ok=True)

    dati = carica(args.csv)
    print(f"Giocatori (tracce) trovati: {len(dati)}")

    # statistiche per giocatore
    righe = []
    for pid, tracce in dati.items():
        if len(tracce) < args.min_rilevazioni:
            continue
        s = statistiche_giocatore(tracce)
        s["id_giocatore"] = pid
        righe.append(s)
        heatmap(tracce, f"Giocatore #{pid} (Squadra {s['squadra']})",
                os.path.join(heat_dir, f"giocatore_{pid:03d}_sq{s['squadra']}.png"))

    righe.sort(key=lambda r: (r["squadra"], -r["distanza_m_approx"]))
    stats_path = os.path.join(out_dir, f"STATISTICHE_{base}.csv")
    campi = ["id_giocatore", "squadra", "n_rilevazioni", "durata_s",
             "x_medio", "y_medio", "zona", "area_azione_m2",
             "distanza_m_approx", "vel_media_kmh_approx", "vel_max_kmh_approx"]
    with open(stats_path, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=campi)
        wr.writeheader()
        for r in righe:
            wr.writerow({k: r[k] for k in campi})

    # heatmap di squadra
    for sq in (1, 2):
        tutte = [p for tr in dati.values() for p in tr if p[3] == sq]
        if tutte:
            heatmap(tutte, f"Squadra {sq} - tutte le posizioni",
                    os.path.join(heat_dir, f"_SQUADRA_{sq}.png"))

    print(f"\nGiocatori analizzati (>= {args.min_rilevazioni} rilevazioni): {len(righe)}")
    print(f"Statistiche: {stats_path}")
    print(f"Heatmap:     {heat_dir}/")
    print("\n--- Anteprima statistiche per giocatore ---")
    print(f"{'ID':>4} {'Sq':>3} {'rilev':>6} {'x_med':>6} {'y_med':>6} {'zona':>14} "
          f"{'area_m2':>8} {'dist~':>6} {'vmax~':>6}")
    for r in righe[:14]:
        print(f"{r['id_giocatore']:>4} {r['squadra']:>3} {r['n_rilevazioni']:>6} "
              f"{r['x_medio']:>6} {r['y_medio']:>6} {r['zona']:>14} "
              f"{r['area_azione_m2']:>8} {r['distanza_m_approx']:>6} {r['vel_max_kmh_approx']:>6}")


if __name__ == "__main__":
    main()
