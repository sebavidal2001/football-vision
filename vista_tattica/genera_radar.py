"""
genera_radar.py — Dal video alla Vista Tattica 2D + dati posizioni.

Usa una calibrazione salvata (calibra_campo.py) per proiettare i giocatori
sulla mappa dall'alto. Produce:
  - un video affiancato:  [video con grafica pulita] | [radar 2D dall'alto]
  - un file CSV con le posizioni reali (metri) di ogni giocatore nel tempo

Uso:
  python genera_radar.py <video> <calibrazione.json> [--salto N] [--imgsz 1280] [--modello yolov8s.pt]

Nota onesta: con una sola calibrazione il radar è corretto finché la
telecamera resta ~ferma. Quando l'inquadratura cambia molto, le posizioni
si spostano: è il limite del metodo manuale (lo risolveremo con la
calibrazione automatica).
"""

import os
import sys
import csv
import json
import argparse
import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import campo_calcio as cc

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

PERSON_ID, BALL_ID = 0, 32
COL_SQUADRA = [(255, 90, 0), (0, 90, 255)]   # BGR: squadra 1 (blu), squadra 2 (rosso)
COL_PALLA = (0, 255, 255)


def colore_maglia(frame, box):
    x1, y1, x2, y2 = map(int, box)
    h = y2 - y1
    crop = frame[max(0, y1+int(0.15*h)):max(0, y1+int(0.45*h)), max(0, x1):max(0, x2)]
    if crop.size == 0:
        return np.array([0, 0, 0])
    return crop.reshape(-1, 3).mean(axis=0)


def piedi(box):
    """Punto ai piedi del giocatore (centro-basso del box)."""
    x1, y1, x2, y2 = box
    return np.array([[[(x1 + x2) / 2.0, y2]]], dtype=np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("calibrazione")
    ap.add_argument("--salto", type=int, default=3)
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--modello", default="yolov8s.pt")
    ap.add_argument("--conf", type=float, default=0.25)
    args = ap.parse_args()

    with open(args.calibrazione, encoding="utf-8") as f:
        H = np.array(json.load(f)["homography"], dtype=np.float32)

    from ultralytics import YOLO
    import supervision as sv
    from sklearn.cluster import KMeans

    model = YOLO(args.modello)
    info = sv.VideoInfo.from_video_path(args.video)
    print(f"🎞  {info.width}x{info.height}, {info.total_frames} frame, {info.fps} fps")

    mappa_vuota = cc.disegna_campo()
    map_h, map_w = mappa_vuota.shape[:2]
    # Il radar viene ridimensionato all'altezza del video per affiancarlo
    scala_radar = info.height / map_h
    radar_w = int(map_w * scala_radar)

    out_fps = max(1, info.fps // args.salto)
    out_w = info.width + radar_w
    out_path = os.path.join(OUTPUT_DIR, "RADAR_" + os.path.splitext(os.path.basename(args.video))[0] + ".mp4")
    writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"),
                             out_fps, (out_w, info.height))

    csv_path = os.path.join(OUTPUT_DIR, "POSIZIONI_" + os.path.splitext(os.path.basename(args.video))[0] + ".csv")
    csv_f = open(csv_path, "w", newline="", encoding="utf-8")
    csv_w = csv.writer(csv_f)
    csv_w.writerow(["frame", "tempo_s", "id_giocatore", "squadra", "x_m", "y_m"])

    tracker = sv.ByteTrack(frame_rate=out_fps)
    kmeans, calib_colori = None, []
    CALIB = 20
    frame_gen = sv.get_video_frames_generator(args.video)
    n_analizzati = 0

    print("▶  Genero il radar...")
    for idx, frame in enumerate(frame_gen):
        if idx % args.salto != 0:
            continue
        tempo = idx / info.fps
        result = model(frame, verbose=False, imgsz=args.imgsz, conf=args.conf)[0]
        det = sv.Detections.from_ultralytics(result)
        palla = det[det.class_id == BALL_ID]
        persone = det[det.class_id == PERSON_ID]
        persone = tracker.update_with_detections(persone)
        n_analizzati += 1

        if kmeans is None and n_analizzati <= CALIB:
            for box in persone.xyxy:
                calib_colori.append(colore_maglia(frame, box))
        elif kmeans is None and len(calib_colori) > 4:
            kmeans = KMeans(n_clusters=2, n_init=10, random_state=42).fit(calib_colori)

        vista = frame.copy()
        radar = mappa_vuota.copy()

        # palla
        for box in palla.xyxy:
            p = cv2.perspectiveTransform(piedi(box), H).reshape(2)
            cx, cy = int((box[0]+box[2])/2), int(box[3])
            cv2.circle(vista, (cx, cy), 5, COL_PALLA, -1)
            if 0 <= p[0] <= cc.LUNGHEZZA and 0 <= p[1] <= cc.LARGHEZZA:
                cv2.circle(radar, cc.metri_a_pixel(*p), 5, COL_PALLA, -1)

        # giocatori
        for box, tid in zip(persone.xyxy, persone.tracker_id):
            sq = int(kmeans.predict([colore_maglia(frame, box)])[0]) if kmeans is not None else 0
            colore = COL_SQUADRA[sq]
            # grafica pulita: ellisse sotto i piedi, niente box
            cx, cy = int((box[0]+box[2])/2), int(box[3])
            cv2.ellipse(vista, (cx, cy), (16, 7), 0, 0, 360, colore, 2)
            # proiezione sul campo
            p = cv2.perspectiveTransform(piedi(box), H).reshape(2)
            if 0 <= p[0] <= cc.LUNGHEZZA and 0 <= p[1] <= cc.LARGHEZZA:
                cv2.circle(radar, cc.metri_a_pixel(*p), 6, colore, -1)
                cv2.circle(radar, cc.metri_a_pixel(*p), 6, (0, 0, 0), 1)
                csv_w.writerow([idx, f"{tempo:.2f}", int(tid), sq+1, f"{p[0]:.2f}", f"{p[1]:.2f}"])

        radar_resized = cv2.resize(radar, (radar_w, info.height))
        combo = np.hstack([vista, radar_resized])
        writer.write(combo)

        if n_analizzati % 20 == 0:
            print(f"   frame {idx}/{info.total_frames}")

    writer.release()
    csv_f.close()
    print("\n=========== FATTO ===========")
    print(f"Frame analizzati: {n_analizzati}")
    print(f"Video radar:      {out_path}")
    print(f"Dati posizioni:   {csv_path}")
    print("=============================")


if __name__ == "__main__":
    main()
