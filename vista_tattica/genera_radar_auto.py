"""
genera_radar_auto.py — Vista Tattica 2D AUTOMATICA (niente calibrazione manuale).

Usa un modello AI (yolo-football-pitch-detection.pt) che riconosce i 32 punti
del campo a OGNI fotogramma: ricalcola l'homography frame per frame, quindi
gestisce anche la telecamera in movimento (broadcast).

Produce:
  - video affiancato: [video con grafica pulita] | [radar 2D dall'alto]
  - CSV con le posizioni reali (metri) dei giocatori nel tempo

Uso:
  python genera_radar_auto.py <video> [--salto N] [--imgsz 1280]
                              [--conf_campo 0.5] [--modello_giocatori yolov8s.pt]

Nota: usa DUE modelli per frame (campo + giocatori) -> su CPU è lento.
Tienilo su clip brevi (10-20 s) e usa --salto 3 o più.
"""

import os
import sys
import csv
import argparse
from collections import Counter
import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import campo_calcio as cc

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
_DIR = os.path.dirname(os.path.abspath(__file__))
MODELLO_CAMPO = os.path.join(_DIR, "yolo-football-pitch-detection.pt")
MODELLO_GIOCATORI = os.path.join(_DIR, "giocatori_calcio.pt")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Classi del modello specifico calcio
BALL_ID, GK_ID, PLAYER_ID, REF_ID = 0, 1, 2, 3
COL_SQUADRA = [(255, 90, 0), (0, 90, 255)]
COL_PALLA = (0, 255, 255)
COL_ARBITRO = (0, 215, 255)   # arbitro: giallo-arancio, fuori squadra
KP_REALI = np.array(cc.KEYPOINTS_32, dtype=np.float32)


def colore_maglia(frame, box):
    """Colore medio della maglia (busto), robusto: ritaglio stretto, niente erba, mediana."""
    x1, y1, x2, y2 = map(int, box)
    h, w = y2 - y1, x2 - x1
    cx1, cx2 = x1 + int(0.2*w), x2 - int(0.2*w)     # restringe lateralmente (no sfondo)
    cy1, cy2 = y1 + int(0.15*h), y1 + int(0.45*h)   # fascia busto
    crop = frame[max(0, cy1):max(0, cy2), max(0, cx1):max(0, cx2)]
    if crop.size == 0:
        return np.array([0, 0, 0], dtype=np.float32)
    px = crop.reshape(-1, 3).astype(np.float32)
    b, g, r = px[:, 0], px[:, 1], px[:, 2]
    non_erba = ~((g > b * 1.1) & (g > r * 1.1))      # scarta i pixel verdi (campo)
    if non_erba.sum() > 5:
        px = px[non_erba]
    return np.median(px, axis=0)


def piedi(box):
    x1, y1, x2, y2 = box
    return np.array([[[(x1 + x2) / 2.0, y2]]], dtype=np.float32)


def proietta_in_campo(box, H, margine=25.0):
    """Proietta i piedi sul campo. Accetta chi sborda di poco (lato lontano)
    riportandolo sul bordo; scarta le proiezioni assurde (oltre il margine)."""
    if H is None:
        return None
    p = cv2.perspectiveTransform(piedi(box), H).reshape(2)
    x, y = float(p[0]), float(p[1])
    if not (-margine <= x <= cc.LUNGHEZZA + margine and -margine <= y <= cc.LARGHEZZA + margine):
        return None
    return (min(max(x, 0.0), cc.LUNGHEZZA), min(max(y, 0.0), cc.LARGHEZZA))


class TrackerMetrico:
    """Tracking dei giocatori nelle coordinate del CAMPO (metri).
    - associa con PREVISIONE del movimento (la traccia ricorda la velocità)
    - tollera sparizioni temporanee (riaggancia invece di creare nuovi ID)
    - squadra stabile per traccia (voto di maggioranza, niente sfarfallio)
    """
    def __init__(self, max_dist=4.0, max_miss=30):
        self.max_dist = max_dist     # gate base (metri)
        self.max_miss = max_miss     # frame analizzati di tolleranza assenza
        self.tracce = {}             # id -> dict(x,y,vx,vy,last,team,voti)
        self.next_id = 1
        self.frame = 0

    def update(self, rilevazioni):
        """rilevazioni: lista di ((x,y), squadra). Ritorna lista di id."""
        self.frame += 1
        ids = [None] * len(rilevazioni)
        validi = [(i, p, t) for i, (p, t) in enumerate(rilevazioni) if p is not None]

        # costruisci tutte le coppie compatibili (rilevazione, traccia)
        coppie = []
        for i, p, t in validi:
            for tid, tr in self.tracce.items():
                dt = self.frame - tr["last"]
                dtp = min(dt, 5)                          # previsione max 5 frame avanti
                px = tr["x"] + tr["vx"] * dtp
                py = tr["y"] + tr["vy"] * dtp
                d = ((p[0]-px)**2 + (p[1]-py)**2) ** 0.5
                gate = min(self.max_dist + 1.0 * dt, 12.0)  # più tolleranza dopo gap lunghi
                if d <= gate:
                    pen = 0.0 if (t is None or tr["team"] == t) else 2.5  # preferisci stessa squadra
                    coppie.append((d + pen, i, tid))
        coppie.sort()

        assegn, usate = {}, set()
        for _, i, tid in coppie:
            if i in assegn or tid in usate:
                continue
            assegn[i] = tid
            usate.add(tid)

        for i, p, t in validi:
            if i in assegn:
                tid = assegn[i]
                tr = self.tracce[tid]
                dt = max(1, self.frame - tr["last"])
                tr["vx"] = 0.6 * tr["vx"] + 0.4 * ((p[0]-tr["x"]) / dt)
                tr["vy"] = 0.6 * tr["vy"] + 0.4 * ((p[1]-tr["y"]) / dt)
                tr["x"], tr["y"] = p
                tr["last"] = self.frame
                if t is not None:                        # vota solo squadre note (no calibrazione)
                    tr["voti"][t] += 1
                    tr["team"] = tr["voti"].most_common(1)[0][0]
                ids[i] = tid
            else:
                tid = self.next_id
                self.next_id += 1
                voti = Counter({t: 1}) if t is not None else Counter()
                self.tracce[tid] = {"x": p[0], "y": p[1], "vx": 0.0, "vy": 0.0,
                                    "last": self.frame, "team": (t if t is not None else 0),
                                    "voti": voti}
                ids[i] = tid

        self.tracce = {tid: tr for tid, tr in self.tracce.items()
                       if self.frame - tr["last"] <= self.max_miss}
        return ids

    def squadra(self, tid):
        """Squadra stabile della traccia (voto di maggioranza)."""
        tr = self.tracce.get(tid)
        return tr["team"] if tr else 0


class GestoreSquadre:
    """Assegna le squadre dai colori maglia e SCARTA i non-giocatori
    (allenatore, staff, guardalinee in tenuta diversa) come outlier di colore."""
    def __init__(self):
        self.km = None
        self.campioni = []
        self.soglia = 1e9

    def calibra(self, colore):
        self.campioni.append(colore)

    def pronto(self):
        return self.km is not None

    def allena(self):
        from sklearn.cluster import KMeans
        X = np.array(self.campioni, dtype=np.float32)
        self.km = KMeans(n_clusters=2, n_init=10, random_state=42).fit(X)
        d = np.linalg.norm(X - self.km.cluster_centers_[self.km.labels_], axis=1)
        self.soglia = float(d.mean() + 2.5 * d.std() + 1e-6)

    def classifica(self, colore):
        """Ritorna 0/1 (squadra) oppure None se NON sembra un giocatore."""
        if self.km is None:
            return 0
        c = np.array(colore, dtype=np.float32)
        dist = np.linalg.norm(self.km.cluster_centers_ - c, axis=1)
        i = int(dist.argmin())
        return None if dist[i] > self.soglia else i

    def classifica_forzata(self, colore):
        """Assegna SEMPRE la squadra più vicina (per i portieri, niente scarto)."""
        if self.km is None:
            return 0
        c = np.array(colore, dtype=np.float32)
        return int(np.linalg.norm(self.km.cluster_centers_ - c, axis=1).argmin())


def homography_da_keypoints(kp_xy, kp_conf, soglia):
    """Calcola l'homography (pixel -> metri) dai keypoint visibili del campo."""
    vis = kp_conf > soglia
    if vis.sum() < 4:
        return None, int(vis.sum())
    src = kp_xy[vis].astype(np.float32)
    dst = KP_REALI[vis]
    H, _ = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    return H, int(vis.sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--salto", type=int, default=3)
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--conf_campo", type=float, default=0.5)
    ap.add_argument("--ogni_campo", type=int, default=1,
                    help="riconosci il campo ogni N frame analizzati (>1 = più veloce su clip lunghe)")
    ap.add_argument("--modello_giocatori", default=MODELLO_GIOCATORI)
    args = ap.parse_args()

    from ultralytics import YOLO
    import supervision as sv
    from sklearn.cluster import KMeans

    print("⚙  Carico i modelli (campo + giocatori)...")
    model_campo = YOLO(MODELLO_CAMPO)
    model_giocatori = YOLO(args.modello_giocatori)

    info = sv.VideoInfo.from_video_path(args.video)
    print(f"🎞  {info.width}x{info.height}, {info.total_frames} frame, {info.fps} fps")

    mappa_vuota = cc.disegna_campo()
    map_h, map_w = mappa_vuota.shape[:2]
    radar_w = int(map_w * info.height / map_h)
    out_fps = max(1, info.fps // args.salto)
    base = os.path.splitext(os.path.basename(args.video))[0]
    out_path = os.path.join(OUTPUT_DIR, "RADARAUTO_" + base + ".mp4")
    writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"),
                             out_fps, (info.width + radar_w, info.height))
    csv_path = os.path.join(OUTPUT_DIR, "POSIZIONIAUTO_" + base + ".csv")
    csv_f = open(csv_path, "w", newline="", encoding="utf-8")
    csv_w = csv.writer(csv_f)
    csv_w.writerow(["frame", "tempo_s", "id_giocatore", "squadra", "x_m", "y_m"])

    # tolleranza assenza ~2.5 s (adattata al frame-rate effettivo dopo il salto)
    tracker = TrackerMetrico(max_dist=4.0, max_miss=max(8, int(out_fps * 2.5)))
    gestore = GestoreSquadre()
    CALIB = 30
    n_ok_campo = 0
    n_analizzati = 0
    n_scartati = 0
    H = None
    n_vis = 0

    print("▶  Genero il radar automatico...")
    for idx, frame in enumerate(sv.get_video_frames_generator(args.video)):
        if idx % args.salto != 0:
            continue
        n_analizzati += 1
        tempo = idx / info.fps

        # 1) Campo: riconosci ogni 'ogni_campo' frame, riusa l'ultimo nel mezzo
        if (n_analizzati - 1) % args.ogni_campo == 0:
            rc = model_campo(frame, verbose=False, imgsz=args.imgsz)[0]
            if rc.keypoints is not None and len(rc.keypoints) > 0:
                kp_xy = rc.keypoints.xy[0].cpu().numpy()
                kp_cf = rc.keypoints.conf[0].cpu().numpy() if rc.keypoints.conf is not None else np.ones(len(kp_xy))
                Hn, n_vis = homography_da_keypoints(kp_xy, kp_cf, args.conf_campo)
                if Hn is not None:
                    H = Hn
        if H is not None:
            n_ok_campo += 1

        # 2) Giocatori (modello specifico: palla/portiere/giocatore/arbitro)
        rg = model_giocatori(frame, verbose=False, imgsz=args.imgsz, conf=0.25)[0]
        det = sv.Detections.from_ultralytics(rg)
        palla = det[det.class_id == BALL_ID]
        arbitri = det[det.class_id == REF_ID]
        giocatori = det[det.class_id == PLAYER_ID]   # di movimento
        portieri = det[det.class_id == GK_ID]        # portieri (colori a parte)

        # Calibrazione squadre: SOLO giocatori di movimento dentro al campo
        # (esclude portieri e staff, che falsano i due colori-squadra)
        if not gestore.pronto():
            for box in giocatori.xyxy:
                if proietta_in_campo(box, H, margine=-2) is not None:
                    gestore.calibra(colore_maglia(frame, box))
            if n_analizzati >= CALIB and len(gestore.campioni) > 6:
                gestore.allena()

        # Posizione + squadra. Giocatori: scarta i colori anomali (staff/guardalinee).
        # Portieri: assegnati sempre alla squadra più vicina.
        info_giocatori = []
        posizioni = []
        for box in giocatori.xyxy:
            pos = proietta_in_campo(box, H, margine=12)
            sq = gestore.classifica(colore_maglia(frame, box)) if gestore.pronto() else 0
            if pos is None or sq is None:
                n_scartati += 1
                continue
            info_giocatori.append((box, sq, pos))
            posizioni.append(pos)
        for box in portieri.xyxy:
            pos = proietta_in_campo(box, H, margine=12)
            if pos is None:
                n_scartati += 1
                continue
            sq = gestore.classifica_forzata(colore_maglia(frame, box)) if gestore.pronto() else 0
            info_giocatori.append((box, sq, pos))
            posizioni.append(pos)
        pronto = gestore.pronto()
        ids = tracker.update([(pos, sq if pronto else None) for (box, sq, pos) in info_giocatori])

        vista = frame.copy()
        radar = mappa_vuota.copy()
        col_q = (0, 200, 0) if H is not None else (0, 0, 255)
        cv2.putText(vista, f"campo: {n_vis} punti", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, col_q, 2)

        for box in palla.xyxy:
            cx, cy = int((box[0]+box[2])/2), int(box[3])
            cv2.circle(vista, (cx, cy), 5, COL_PALLA, -1)
            if H is not None:
                p = cv2.perspectiveTransform(piedi(box), H).reshape(2)
                if 0 <= p[0] <= cc.LUNGHEZZA and 0 <= p[1] <= cc.LARGHEZZA:
                    cv2.circle(radar, cc.metri_a_pixel(*p), 5, COL_PALLA, -1)
                    # palla salvata nel CSV: id_giocatore=0, squadra=0
                    csv_w.writerow([idx, f"{tempo:.2f}", 0, 0, f"{p[0]:.2f}", f"{p[1]:.2f}"])
                    break   # una sola palla per frame

        for (box, sq, pos), tid in zip(info_giocatori, ids):
            squadra = tracker.squadra(tid) if tid is not None else sq  # stabile (voto maggioranza)
            colore = COL_SQUADRA[squadra]
            cx, cy = int((box[0]+box[2])/2), int(box[3])
            cv2.ellipse(vista, (cx, cy), (16, 7), 0, 0, 360, colore, 2)
            if pos is not None:
                cv2.circle(radar, cc.metri_a_pixel(*pos), 6, colore, -1)
                cv2.circle(radar, cc.metri_a_pixel(*pos), 6, (0, 0, 0), 1)
                if tid is not None:
                    csv_w.writerow([idx, f"{tempo:.2f}", int(tid), squadra+1,
                                    f"{pos[0]:.2f}", f"{pos[1]:.2f}"])

        # arbitri (colore neutro, non in squadra, non nel CSV)
        for box in arbitri.xyxy:
            cx, cy = int((box[0]+box[2])/2), int(box[3])
            cv2.ellipse(vista, (cx, cy), (16, 7), 0, 0, 360, COL_ARBITRO, 2)
            if H is not None:
                p = cv2.perspectiveTransform(piedi(box), H).reshape(2)
                if 0 <= p[0] <= cc.LUNGHEZZA and 0 <= p[1] <= cc.LARGHEZZA:
                    cv2.circle(radar, cc.metri_a_pixel(*p), 5, COL_ARBITRO, -1)

        combo = np.hstack([vista, cv2.resize(radar, (radar_w, info.height))])
        writer.write(combo)
        if n_analizzati % 10 == 0:
            print(f"   frame {idx}/{info.total_frames}  campo riconosciuto: {n_ok_campo}/{n_analizzati}")

    writer.release()
    csv_f.close()
    print("\n=========== FATTO ===========")
    print(f"Frame analizzati:        {n_analizzati}")
    print(f"Campo riconosciuto in:   {n_ok_campo}/{n_analizzati} frame")
    print(f"Rilevazioni scartate:    {n_scartati} (fuori campo o non-giocatori)")
    print(f"Video radar automatico:  {out_path}")
    print(f"Dati posizioni:          {csv_path}")
    print("=============================")


if __name__ == "__main__":
    main()
