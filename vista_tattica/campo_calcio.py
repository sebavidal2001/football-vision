"""
campo_calcio.py — Modello del campo + disegno mappa 2D dall'alto.

Usa la geometria del modello automatico (roboflow sports): campo 120 x 70 m,
così i 32 keypoint rilevati cadono esattamente sulle linee disegnate.

Coordinate REALI (metri): origine (0,0) = angolo alto-sinistra.
x = lunghezza (0->120), y = larghezza (0->70).
"""

import numpy as np
import cv2

# Dimensioni del modello-campo (roboflow sports)
LUNGHEZZA = 120.0
LARGHEZZA = 70.0
_PBW, _PBL = 41.0, 20.15      # area di rigore: larghezza, profondità
_GBW, _GBL = 18.32, 5.50      # area piccola: larghezza, profondità
_R = 9.15                     # raggio cerchio
_PS = 11.0                    # distanza dischetto
_C = (60.0, 35.0)             # centro campo
_y_pb1, _y_pb2 = (LARGHEZZA - _PBW) / 2, (LARGHEZZA + _PBW) / 2   # 14.5 / 55.5
_y_gb1, _y_gb2 = (LARGHEZZA - _GBW) / 2, (LARGHEZZA + _GBW) / 2   # 25.84 / 44.16

# 32 keypoint del modello automatico (indice 0-31 -> metri), ordine ufficiale.
KEYPOINTS_32 = [
    (0.0, 0.0), (0.0, 14.5), (0.0, 25.84), (0.0, 44.16), (0.0, 55.5), (0.0, 70.0),
    (5.5, 25.84), (5.5, 44.16), (11.0, 35.0),
    (20.15, 14.5), (20.15, 25.84), (20.15, 44.16), (20.15, 55.5),
    (60.0, 0.0), (60.0, 25.85), (60.0, 44.15), (60.0, 70.0),
    (99.85, 14.5), (99.85, 25.84), (99.85, 44.16), (99.85, 55.5),
    (109.0, 35.0), (114.5, 25.84), (114.5, 44.16),
    (120.0, 0.0), (120.0, 14.5), (120.0, 25.84), (120.0, 44.16), (120.0, 55.5), (120.0, 70.0),
    (50.85, 35.0), (69.15, 35.0),
]

# Punti notevoli per la calibrazione MANUALE (nome -> metri), stessa geometria.
PUNTI_CAMPO = {
    "Angolo alto-sinistra": (0.0, 0.0), "Angolo alto-destra": (120.0, 0.0),
    "Angolo basso-sinistra": (0.0, 70.0), "Angolo basso-destra": (120.0, 70.0),
    "Meta campo - lato alto": (60.0, 0.0), "Meta campo - lato basso": (60.0, 70.0),
    "Centro del campo": (60.0, 35.0),
    "Cerchio centro - alto": (60.0, 25.85), "Cerchio centro - basso": (60.0, 44.15),
    "Cerchio centro - lato SX": (50.85, 35.0), "Cerchio centro - lato DX": (69.15, 35.0),
    "Area SX - angolo alto": (20.15, 14.5), "Area SX - angolo basso": (20.15, 55.5),
    "Area SX - su linea alto": (0.0, 14.5), "Area SX - su linea basso": (0.0, 55.5),
    "Dischetto SX": (11.0, 35.0),
    "Area piccola SX - alto": (5.5, 25.84), "Area piccola SX - basso": (5.5, 44.16),
    "Area DX - angolo alto": (99.85, 14.5), "Area DX - angolo basso": (99.85, 55.5),
    "Area DX - su linea alto": (120.0, 14.5), "Area DX - su linea basso": (120.0, 55.5),
    "Dischetto DX": (109.0, 35.0),
    "Area piccola DX - alto": (114.5, 25.84), "Area piccola DX - basso": (114.5, 44.16),
}

SCALA = 8          # pixel per metro
MARGINE = 28


def metri_a_pixel(x, y):
    return int(MARGINE + x * SCALA), int(MARGINE + y * SCALA)


def dimensioni_mappa():
    return int(LUNGHEZZA * SCALA + 2 * MARGINE), int(LARGHEZZA * SCALA + 2 * MARGINE)


def disegna_campo():
    w, h = dimensioni_mappa()
    img = np.full((h, w, 3), (40, 120, 40), dtype=np.uint8)
    b, t = (255, 255, 255), 2

    def L(p1, p2):
        cv2.line(img, metri_a_pixel(*p1), metri_a_pixel(*p2), b, t)

    L((0, 0), (120, 0)); L((120, 0), (120, 70)); L((120, 70), (0, 70)); L((0, 70), (0, 0))
    L((60, 0), (60, 70))
    cv2.circle(img, metri_a_pixel(*_C), int(_R * SCALA), b, t)
    cv2.circle(img, metri_a_pixel(*_C), 3, b, -1)
    # aree di rigore
    L((0, _y_pb1), (_PBL, _y_pb1)); L((_PBL, _y_pb1), (_PBL, _y_pb2)); L((_PBL, _y_pb2), (0, _y_pb2))
    L((120, _y_pb1), (120-_PBL, _y_pb1)); L((120-_PBL, _y_pb1), (120-_PBL, _y_pb2)); L((120-_PBL, _y_pb2), (120, _y_pb2))
    # aree piccole
    L((0, _y_gb1), (_GBL, _y_gb1)); L((_GBL, _y_gb1), (_GBL, _y_gb2)); L((_GBL, _y_gb2), (0, _y_gb2))
    L((120, _y_gb1), (120-_GBL, _y_gb1)); L((120-_GBL, _y_gb1), (120-_GBL, _y_gb2)); L((120-_GBL, _y_gb2), (120, _y_gb2))
    cv2.circle(img, metri_a_pixel(_PS, 35), 3, b, -1)
    cv2.circle(img, metri_a_pixel(120-_PS, 35), 3, b, -1)
    return img


def disegna_giocatori(mappa, posizioni):
    img = mappa.copy()
    for x, y, colore in posizioni:
        if 0 <= x <= LUNGHEZZA and 0 <= y <= LARGHEZZA:
            cv2.circle(img, metri_a_pixel(x, y), 6, colore, -1)
            cv2.circle(img, metri_a_pixel(x, y), 6, (0, 0, 0), 1)
    return img


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(__file__), "_test_campo.png")
    cv2.imwrite(out, disegna_campo())
    print(f"Campo test: {out} | keypoints: {len(KEYPOINTS_32)}")
