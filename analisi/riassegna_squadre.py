"""
riassegna_squadre.py — Riassegna le squadre usando le impronte Re-ID (più robusto del colore).

Le maglie simili / ombre fanno sbagliare il clustering sul colore medio. Le impronte
visive (embeddings) catturano meglio la divisa: KMeans(2) sulle impronte per traccia
separa le due squadre. Riscrive la colonna 'squadra' nel CSV POSIZIONI.

Uso:
  python riassegna_squadre.py <POSIZIONIAUTO_*.csv>
(richiede il file EMBEDDINGS_<base>.npz accanto; se manca, non fa nulla)
"""
import sys
import csv
from collections import Counter
from pathlib import Path

import numpy as np


def main():
    csv_path = Path(sys.argv[1])
    base = csv_path.stem.replace("POSIZIONIAUTO_", "")
    emb_path = csv_path.parent / f"EMBEDDINGS_{base}.npz"
    if not emb_path.exists():
        print("Nessun file embeddings: salto la riassegnazione squadre.")
        return

    from sklearn.cluster import KMeans
    d = np.load(emb_path)
    ids, vecs = d["ids"], d["vectors"]
    if len(ids) < 4:
        print("Troppo poche tracce per riassegnare.")
        return

    labels = KMeans(n_clusters=2, n_init=10, random_state=0).fit(vecs).labels_
    team_of = {int(t): int(l) + 1 for t, l in zip(ids, labels)}  # cluster 0->1, 1->2

    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    if not rows:
        return
    fields = list(rows[0].keys())
    cambiati = 0
    for r in rows:
        tid = int(float(r["id_giocatore"]))
        if tid and tid in team_of and r["squadra"] != str(team_of[tid]):
            r["squadra"] = str(team_of[tid])
            cambiati += 1
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"Squadre riassegnate da Re-ID: {dict(Counter(team_of.values()))} "
          f"({cambiati} righe aggiornate)")


if __name__ == "__main__":
    main()
