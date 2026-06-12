"""
metriche_avanzate.py — Metriche di scouting (atletiche + tattiche) dal tracking.

Legge un CSV POSIZIONI (frame, tempo_s, id_giocatore, squadra, x_m, y_m)
dove id_giocatore=0 è la PALLA, e produce:
  - METRICHE_GIOCATORI_<clip>.csv : atletica + posizione per ogni giocatore
  - METRICHE_SQUADRE_<clip>.csv   : forma/compattezza/possesso per squadra
  - REPORT_<clip>.png             : sintesi visiva

Uso:
  python metriche_avanzate.py <POSIZIONI.csv> [--min_rilevazioni 20]

Onesto: da broadcast distanza/velocità sono APPROSSIMATE (vanno lette in modo
relativo). Posizione, zona, forma e possesso sono affidabili.
"""

import os
import sys
import csv
import argparse
try:
    sys.stdout.reconfigure(encoding="utf-8")   # stampe Unicode anche su Windows
except Exception:
    pass
from collections import defaultdict, Counter
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

L, W = 120.0, 70.0
COL = {1: "#1f6fff", 2: "#ff3b3b"}
VEL_MAX = 10.0  # m/s
# fasce di velocità (km/h): camminata, jogging, corsa, corsa veloce, sprint
FASCE = [("camminata", 0, 7), ("jogging", 7, 14), ("corsa", 14, 20),
         ("corsa_veloce", 20, 25), ("sprint", 25, 999)]


def smussa(a, w=9):
    a = np.asarray(a, float)
    if len(a) < w:
        return a
    k = np.ones(w) / w
    s = np.convolve(a, k, mode="same")
    h = w // 2
    s[:h] = a[:h]; s[-h:] = a[-h:]
    return s


def carica(path):
    giocatori = defaultdict(list)     # id -> [(t,x,y,team)]
    palla = []                        # [(t,x,y)]
    per_frame = defaultdict(list)     # frame -> [(id,team,x,y)]
    for r in csv.DictReader(open(path, encoding="utf-8")):
        pid = int(r["id_giocatore"]); team = int(r["squadra"])
        t = float(r["tempo_s"]); x = float(r["x_m"]); y = float(r["y_m"])
        if pid == 0:
            palla.append((t, x, y))
        else:
            giocatori[pid].append((t, x, y, team))
            per_frame[r["frame"]].append((pid, team, x, y))
    for k in giocatori:
        giocatori[k].sort()
    return giocatori, palla, per_frame


def atletiche(tr):
    """Metriche atletiche di una traccia ordinata [(t,x,y,team)]."""
    t = np.array([p[0] for p in tr])
    x = smussa([p[1] for p in tr]); y = smussa([p[2] for p in tr])
    team = Counter(p[3] for p in tr).most_common(1)[0][0]
    dist = 0.0
    dist_fascia = {f[0]: 0.0 for f in FASCE}
    vmax = 0.0; n_sprint = 0; n_accel = 0
    in_sprint = False; prev_v = None; last = 0
    for i in range(1, len(t)):
        dt = t[i] - t[last]
        if dt < 0.4:
            continue
        d = float(np.hypot(x[i]-x[last], y[i]-y[last]))
        v = d / dt; vk = v * 3.6
        if v <= VEL_MAX:
            dist += d
            for nome, lo, hi in FASCE:
                if lo <= vk < hi:
                    dist_fascia[nome] += d; break
            vmax = max(vmax, vk)
            if vk >= 25 and not in_sprint:
                n_sprint += 1; in_sprint = True
            elif vk < 25:
                in_sprint = False
            if prev_v is not None and (v - prev_v) / dt > 2.0:
                n_accel += 1
            prev_v = v
        last = i
    xr = np.array([p[1] for p in tr]); yr = np.array([p[2] for p in tr])
    x_med, y_med = float(np.median(xr)), float(np.median(yr))
    larg_x = float(np.percentile(xr, 90) - np.percentile(xr, 10))
    larg_y = float(np.percentile(yr, 90) - np.percentile(yr, 10))
    zona = "terzo dx" if x_med > 80 else ("terzo sx" if x_med < 40 else "terzo centrale")
    return {
        "squadra": team, "n_rilevazioni": len(tr), "durata_s": round(float(t[-1]-t[0]), 1),
        "x_medio": round(x_med, 1), "y_medio": round(y_med, 1), "zona": zona,
        "area_azione_m2": round(larg_x * larg_y),
        "distanza_m": round(dist), "alta_intensita_m": round(dist_fascia["corsa_veloce"]+dist_fascia["sprint"]),
        "sprint_m": round(dist_fascia["sprint"]), "n_sprint": n_sprint,
        "vel_max_kmh": round(vmax, 1), "n_accelerazioni": n_accel,
        "dist_camminata_m": round(dist_fascia["camminata"]),
        "dist_corsa_m": round(dist_fascia["corsa"]),
    }


def metriche_squadre(per_frame):
    """Forma e compattezza per squadra, aggregate sui frame."""
    agg = {1: defaultdict(list), 2: defaultdict(list)}
    for frame, gente in per_frame.items():
        for sq in (1, 2):
            pts = np.array([(x, y) for (pid, t, x, y) in gente if t == sq])
            if len(pts) < 6:
                continue
            cx, cy = pts[:, 0].mean(), pts[:, 1].mean()
            larghezza = np.percentile(pts[:, 1], 90) - np.percentile(pts[:, 1], 10)
            profondita = np.percentile(pts[:, 0], 90) - np.percentile(pts[:, 0], 10)
            compattezza = np.mean(np.hypot(pts[:, 0]-cx, pts[:, 1]-cy))
            agg[sq]["cx"].append(cx); agg[sq]["larghezza"].append(larghezza)
            agg[sq]["profondita"].append(profondita); agg[sq]["compattezza"].append(compattezza)
    out = {}
    for sq in (1, 2):
        if agg[sq]["cx"]:
            out[sq] = {
                "baricentro_x": round(float(np.mean(agg[sq]["cx"])), 1),
                "ampiezza_media_m": round(float(np.mean(agg[sq]["larghezza"])), 1),
                "profondita_media_m": round(float(np.mean(agg[sq]["profondita"])), 1),
                "compattezza_media_m": round(float(np.mean(agg[sq]["compattezza"])), 1),
            }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--min_rilevazioni", type=int, default=20)
    args = ap.parse_args()

    giocatori, palla, per_frame = carica(args.csv)
    base = os.path.splitext(os.path.basename(args.csv))[0].replace("POSIZIONIAUTO_", "").replace("POSIZIONI_", "")
    out_dir = os.path.dirname(os.path.abspath(args.csv))

    # --- per giocatore ---
    righe = []
    for pid, tr in giocatori.items():
        if len(tr) < args.min_rilevazioni:
            continue
        m = atletiche(tr); m["id_giocatore"] = pid
        righe.append(m)
    righe.sort(key=lambda r: (r["squadra"], -r["distanza_m"]))
    campi = ["id_giocatore", "squadra", "n_rilevazioni", "durata_s", "x_medio", "y_medio",
             "zona", "area_azione_m2", "distanza_m", "alta_intensita_m", "sprint_m",
             "n_sprint", "vel_max_kmh", "n_accelerazioni", "dist_camminata_m", "dist_corsa_m"]
    gpath = os.path.join(out_dir, f"METRICHE_GIOCATORI_{base}.csv")
    with open(gpath, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=campi); wr.writeheader()
        for r in righe:
            wr.writerow({k: r[k] for k in campi})

    # --- per squadra ---
    squadre = metriche_squadre(per_frame)
    # possesso: giocatore più vicino alla palla, per istante (match per tempo arrotondato)
    pos_per_t = defaultdict(list)
    for pid, tr in giocatori.items():
        for (t, x, y, team) in tr:
            pos_per_t[round(t, 2)].append((team, x, y))
    poss = Counter(); terzi = Counter()
    for (t, bx, by) in palla:
        terzi["dx" if bx > 80 else ("sx" if bx < 40 else "centro")] += 1
        cand = pos_per_t.get(round(t, 2), [])
        if cand:
            team, _, _ = min(cand, key=lambda c: (c[1]-bx)**2 + (c[2]-by)**2)
            poss[team] += 1
    tot_poss = sum(poss.values()) or 1
    spath = os.path.join(out_dir, f"METRICHE_SQUADRE_{base}.csv")
    with open(spath, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["squadra", "baricentro_x_m", "ampiezza_media_m", "profondita_media_m",
                     "compattezza_media_m", "possesso_pct"])
        for sq in (1, 2):
            s = squadre.get(sq, {})
            wr.writerow([sq, s.get("baricentro_x", ""), s.get("ampiezza_media_m", ""),
                         s.get("profondita_media_m", ""), s.get("compattezza_media_m", ""),
                         round(100*poss.get(sq, 0)/tot_poss)])

    # --- REPORT visivo ---
    crea_report(base, righe, squadre, poss, terzi, out_dir)

    print(f"Giocatori analizzati: {len(righe)}")
    print(f"  → {gpath}")
    print(f"  → {spath}")
    print(f"  → REPORT_{base}.png")
    print("\n--- Squadre ---")
    for sq in (1, 2):
        s = squadre.get(sq, {})
        print(f"  Squadra {sq}: possesso {round(100*poss.get(sq,0)/tot_poss)}% | "
              f"ampiezza {s.get('ampiezza_media_m','?')}m | profondità {s.get('profondita_media_m','?')}m | "
              f"compattezza {s.get('compattezza_media_m','?')}m")
    print("\n--- Top distanza (atletico) ---")
    for r in sorted(righe, key=lambda r: -r["distanza_m"])[:8]:
        print(f"  #{r['id_giocatore']} (S{r['squadra']}): {r['distanza_m']}m | "
              f"alta int. {r['alta_intensita_m']}m | {r['n_sprint']} sprint | vmax {r['vel_max_kmh']}km/h")


def crea_report(base, righe, squadre, poss, terzi, out_dir):
    fig = plt.figure(figsize=(16, 9))
    fig.suptitle(f"Report Scouting — {base}", fontsize=15, fontweight="bold")
    tot = sum(poss.values()) or 1

    # 1) Distanza per giocatore
    ax = fig.add_subplot(2, 2, 1)
    top = sorted(righe, key=lambda r: -r["distanza_m"])[:12]
    ax.barh([f"#{r['id_giocatore']} S{r['squadra']}" for r in top],
            [r["distanza_m"] for r in top],
            color=[COL.get(r["squadra"], "#888") for r in top])
    ax.invert_yaxis(); ax.set_title("Distanza percorsa (m) — atletico"); ax.tick_params(labelsize=8)

    # 2) Alta intensità + sprint
    ax = fig.add_subplot(2, 2, 2)
    topi = sorted(righe, key=lambda r: -r["alta_intensita_m"])[:12]
    ax.barh([f"#{r['id_giocatore']} S{r['squadra']}" for r in topi],
            [r["alta_intensita_m"] for r in topi],
            color=[COL.get(r["squadra"], "#888") for r in topi])
    ax.invert_yaxis(); ax.set_title("Distanza ad alta intensità (>20 km/h)"); ax.tick_params(labelsize=8)

    # 3) Possesso
    ax = fig.add_subplot(2, 2, 3)
    vals = [poss.get(1, 0)/tot*100, poss.get(2, 0)/tot*100]
    ax.bar(["Squadra 1", "Squadra 2"], vals, color=[COL[1], COL[2]])
    ax.set_title("Possesso territoriale (%)"); ax.set_ylim(0, 100)
    for i, v in enumerate(vals):
        ax.text(i, v+2, f"{v:.0f}%", ha="center")

    # 4) Forma squadre (tabella testuale)
    ax = fig.add_subplot(2, 2, 4); ax.axis("off")
    ax.set_title("Forma e compattezza squadre")
    testo = f"{'':12}{'Sq.1':>10}{'Sq.2':>10}\n"
    etich = [("Ampiezza", "ampiezza_media_m"), ("Profondità", "profondita_media_m"),
             ("Compattezza", "compattezza_media_m"), ("Baricentro x", "baricentro_x")]
    for nome, k in etich:
        v1 = squadre.get(1, {}).get(k, "?"); v2 = squadre.get(2, {}).get(k, "?")
        testo += f"{nome:12}{str(v1):>10}{str(v2):>10}\n"
    testo += "\n(metri; ampiezza/profondità = estensione media,\ncompattezza = distanza media dal baricentro)"
    ax.text(0.05, 0.9, testo, va="top", family="monospace", fontsize=10)

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(os.path.join(out_dir, f"REPORT_{base}.png"), dpi=110)


if __name__ == "__main__":
    main()
