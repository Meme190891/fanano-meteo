"""Confronta la taratura salita-del-Leo / pioggia usando Pratignano, Scaffaiolo, media e massimo."""
import csv, sys, statistics as st
from datetime import datetime, timedelta
from collections import defaultdict
def leggi(f, fine=False):
    return sorted((datetime.fromisoformat(a[1] if fine else a[0]), float(a[2]))
                  for a in csv.reader(open(f, encoding="utf-8")) if len(a) == 3 and a[0][:2] == "20" and a[2].strip())
liv = [(t, v) for t, v in leggi(sys.argv[1]) if not (v < -0.7 and t.month == 12)]
pr = dict(leggi(sys.argv[2], True)); sc = dict(leggi(sys.argv[3], True))
print(f"totale anno: Pratignano {sum(pr.values()):.0f} mm, Scaffaiolo {sum(sc.values()):.0f} mm "
      f"(Scaffaiolo valori {len(sc)}, Pratignano {len(pr)})")
tempi = sorted(set(pr) | set(sc))
serie = {"pratignano": [(t, pr.get(t, 0.0)) for t in tempi], "scaffaiolo": [(t, sc.get(t, 0.0)) for t in tempi],
         "media": [(t, (pr.get(t, 0.0) + sc.get(t, 0.0)) / 2) for t in tempi]}
ld = dict(liv)
def L(t):
    for d in range(0, 9):
        for s in (1, -1):
            x = ld.get(t + s * timedelta(minutes=15 * d))
            if x is not None: return x
# eventi definiti sulla media delle due stazioni (stessi eventi per tutti i confronti)
ev, cur = [], None
for t, v in serie["media"]:
    if v <= 0: continue
    if cur and t - cur["fine"] <= timedelta(hours=12): cur["fine"] = t
    else:
        if cur: ev.append(cur)
        cur = {"ini": t - timedelta(minutes=30), "fine": t}
ev.append(cur)
risultati = {}
for nome, s in serie.items():
    righe = []
    for e in ev:
        mm = sum(v for t, v in s if e["ini"] < t <= e["fine"])
        if mm < 15: continue
        l0 = L(e["ini"]); w = [v for t, v in liv if e["ini"] <= t <= e["fine"] + timedelta(hours=12)]
        if l0 is None or len(w) < 10: continue
        righe.append((e["ini"], mm, max(w) - l0))
    k = sorted(r[2] / r[1] for r in righe)
    q = lambda p: k[round(p * (len(k) - 1))]
    err = [abs(r[2] - q(0.5) * r[1]) for r in righe]
    # correlazione di Pearson tra mm e salita
    xs, ys = [r[1] for r in righe], [r[2] for r in righe]
    mx, my = st.mean(xs), st.mean(ys)
    corr = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    dentro = sum(1 for r in righe if q(0.2) * r[1] - 0.03 <= r[2] <= q(0.8) * r[1] + 0.03)
    risultati[nome] = righe
    print(f"{nome:11s} eventi {len(righe):2d} | k p20 {q(0.2):.4f} p50 {q(0.5):.4f} p80 {q(0.8):.4f} | "
          f"correlazione {corr:.2f} | errore mediano {st.median(err):.3f} m | dentro forbice {dentro}/{len(righe)}")
print("\nconfronto eventi (mm Prat / mm Scaff / salita Leo):")
p = {r[0]: r for r in risultati["pratignano"]}; s_ = {r[0]: r for r in risultati["scaffaiolo"]}
for t in sorted(set(p) | set(s_)):
    print(f"  {t:%d/%m/%y}  {p[t][1] if t in p else 0:6.1f}  {s_[t][1] if t in s_ else 0:6.1f}  "
          f"{(p.get(t) or s_.get(t))[2]:+.2f}")
