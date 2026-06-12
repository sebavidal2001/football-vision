"""
Analizza Clip in Locale — Football Vision (Fase 1)
---------------------------------------------------
Rileva giocatori + palla, li segue nel tempo (tracking), assegna le squadre
dai colori delle maglie e produce un video annotato. Gira sulla CPU.

Uso da terminale:
    python analizza_locale.py  <video_input>  [--salto N]  [--imgsz 1280]  [--modello yolov8s.pt]

  --salto N : analizza 1 frame ogni N (default 1 = tutti). Su CPU, usa 2 o 3
              per andare più veloce mantenendo un buon risultato.
  --imgsz   : risoluzione interna del modello (1280 = più preciso sui giocatori piccoli).
  --modello : yolov8n.pt (veloce) / yolov8s.pt (equilibrato) / yolov8m.pt (preciso, lento).

Output: nella cartella  output/  un file  ANNOTATO_<nome>.mp4  + statistiche a schermo.
"""

import os
import sys
import argparse
import numpy as np
import cv2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

PERSON_ID = 0   # classe COCO: persona
BALL_ID = 32    # classe COCO: pallone sportivo


def colore_maglia(frame, box):
    x1, y1, x2, y2 = map(int, box)
    h = y2 - y1
    ty1, ty2 = y1 + int(0.15 * h), y1 + int(0.45 * h)
    crop = frame[max(0, ty1):max(0, ty2), max(0, x1):max(0, x2)]
    if crop.size == 0:
        return np.array([0, 0, 0])
    return crop.reshape(-1, 3).mean(axis=0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--salto", type=int, default=1)
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--modello", default="yolov8s.pt")
    ap.add_argument("--conf", type=float, default=0.25)
    args = ap.parse_args()

    if not os.path.exists(args.video):
        print(f"❌ Video non trovato: {args.video}")
        sys.exit(1)

    from ultralytics import YOLO
    import supervision as sv
    from sklearn.cluster import KMeans
    import torch

    print(f"⚙  Dispositivo: {'GPU' if torch.cuda.is_available() else 'CPU'}")
    print(f"⚙  Modello: {args.modello} | imgsz: {args.imgsz} | salto: {args.salto}")
    model = YOLO(args.modello)

    info = sv.VideoInfo.from_video_path(args.video)
    print(f"🎞  Video: {info.width}x{info.height}, {info.total_frames} frame, {info.fps} fps")
    out_fps = max(1, info.fps // args.salto)
    out_info = sv.VideoInfo(width=info.width, height=info.height, fps=out_fps,
                            total_frames=info.total_frames // args.salto)

    nome_out = os.path.join(OUTPUT_DIR, "ANNOTATO_" + os.path.basename(args.video))
    tracker = sv.ByteTrack(frame_rate=out_fps)
    COLORI = sv.ColorPalette.from_hex(['#00BFFF', '#FF1493', '#FFD700'])
    box_annot = sv.BoxAnnotator(color=COLORI, thickness=2)
    label_annot = sv.LabelAnnotator(color=COLORI, text_scale=0.4, text_thickness=1)
    ball_annot = sv.TriangleAnnotator(color=sv.Color.from_hex('#FFD700'), base=18, height=16)

    kmeans = None
    colori_calib = []
    CALIB = 25

    # statistiche
    tot_giocatori = 0
    frame_analizzati = 0
    frame_con_palla = 0

    frame_gen = sv.get_video_frames_generator(args.video)
    print("\n▶  Analisi in corso...")
    with sv.VideoSink(nome_out, out_info) as sink:
        for idx, frame in enumerate(frame_gen):
            if idx % args.salto != 0:
                continue
            result = model(frame, verbose=False, imgsz=args.imgsz, conf=args.conf)[0]
            det = sv.Detections.from_ultralytics(result)
            palla = det[det.class_id == BALL_ID]
            persone = det[det.class_id == PERSON_ID]
            persone = tracker.update_with_detections(persone)

            n = len(persone)
            tot_giocatori += n
            frame_analizzati += 1
            if len(palla) > 0:
                frame_con_palla += 1

            if kmeans is None and frame_analizzati <= CALIB:
                for box in persone.xyxy:
                    colori_calib.append(colore_maglia(frame, box))
            elif kmeans is None and len(colori_calib) > 4:
                kmeans = KMeans(n_clusters=2, n_init=10, random_state=42).fit(colori_calib)

            labels, squadre = [], []
            for box, tid in zip(persone.xyxy, persone.tracker_id):
                sq = int(kmeans.predict([colore_maglia(frame, box)])[0]) if kmeans is not None else 0
                squadre.append(sq)
                labels.append(f"#{tid} S{sq+1}")
            if squadre:
                persone.class_id = np.array(squadre)

            out = frame.copy()
            out = box_annot.annotate(out, persone)
            out = label_annot.annotate(out, persone, labels=labels)
            if len(palla) > 0:
                out = ball_annot.annotate(out, palla)
            sink.write_frame(out)

            if frame_analizzati % 25 == 0:
                print(f"   frame {idx}/{info.total_frames}  |  giocatori in scena: {n}")

    media = tot_giocatori / max(1, frame_analizzati)
    perc_palla = 100 * frame_con_palla / max(1, frame_analizzati)
    print("\n=========== RISULTATI ===========")
    print(f"Frame analizzati:        {frame_analizzati}")
    print(f"Giocatori medi per frame: {media:.1f}  (ideale ~22 + arbitri)")
    print(f"Palla rilevata:          {perc_palla:.0f}% dei frame")
    print(f"Video annotato salvato:  {nome_out}")
    print("=================================")


if __name__ == "__main__":
    main()
