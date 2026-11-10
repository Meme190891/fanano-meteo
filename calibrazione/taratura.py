import csv, sys, math, statistics as st
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
R = ZoneInfo("Europe/Rome")
def leggi(f, fine=False):
    return sorted((datetime.fromisoformat(a[1] if fine else a[0]), float(a[2]))
                  for a in csv.reader(open(f, encoding="utf-8")) if len(a) == 3 and a[0][:2] == "20" and a[2].strip())
liv = [(t, v) for t, v in leggi(sys.argv[1]) if not (v < -0.7 and t.month == 12)]
pio = leggi(sys.argv[2], True)
ld = dict(liv)
def L(t):
    for d in range(0, 9):
        for s in (1, -1):
            x = ld.get(t + s * timedelta(minutes=15 * d))
            if x is not None: return x
# eventi di pioggia: separati da >= 12h asciutte, totale >= 5 mm
ev, cur = [], None
for t, v in pio:
    if v <= 0: continue
    if cur and t - cur["fine"] <= timedelta(hours=12):
        cur["fine"] = t; cur["mm"] += v; cur["max30"] = max(cur["max30"], v)
    else:
        if cur: ev.append(cur)
        cur = {"ini": t - timedelta(minutes=30), "fine": t, "mm": v, "max30": v}
ev.append(cur)
ev = [e for e in ev if e["mm"] >= 5]
righe = []
for e in ev:
    l0 = L(e["ini"])
    fin = e["fine"] + timedelta(hours=12)
    w = [(t, v) for t, v in liv if e["ini"] <= t <= fin]
    if l0 is None or len(w) < 10: continue
    tp, lp = max(w, key=lambda x: x[1])
    api = sum(v for t, v in pio if e["ini"] - timedelta(days=7) < t <= e["ini"])
    mese = e["ini"].astimezone(R).month
    righe.append((e["ini"], e["mm"], e["max30"], l0, lp - l0, (tp - e["ini"]).total_seconds() / 3600, api, mese))
print("inizio            mm   max30  L0     salita  ore_al_picco  pioggia7gg_prima")
for r in righe:
    print(f"{r[0].astimezone(R):%d/%m/%y %H:%M}  {r[1]:5.1f} {r[2]:5.1f}  {r[3]:+.2f}  {r[4]:+.2f}   {r[5]:5.1f}   {r[6]:5.1f}")
# coefficiente salita/mm per stagione (eventi >= 15 mm)
fredda = [r for r in righe if r[7] in (11, 12, 1, 2, 3, 4) and r[1] >= 15]
calda = [r for r in righe if r[7] in (5, 6, 7, 8, 9, 10) and r[1] >= 15]
for nome, g in (("ott-apr", fredda), ("mag-ott", calda)):
    k = [r[4] / r[1] for r in g]
    print(f"{nome}: {len(g)} eventi >=15 mm, salita per mm: mediana {st.median(k):.4f}, min {min(k):.4f}, max {max(k):.4f}")
# regressione salita = a * mm^b (log-log) su tutti gli eventi con salita > 0.02
xs = [(math.log(r[1]), math.log(r[4])) for r in righe if r[4] > 0.02]
mx = st.mean(x for x, _ in xs); my = st.mean(y for _, y in xs)
b = sum((x - mx) * (y - my) for x, y in xs) / sum((x - mx) ** 2 for x, _ in xs); a = math.exp(my - b * mx)
print(f"regressione salita = {a:.4f} * mm^{b:.2f}  (n={len(xs)})")
# ritardo pioggia -> picco
print("ore dall'inizio pioggia al picco (eventi >=15 mm): mediana", st.median(r[5] for r in righe if r[1] >= 15))
# recessione: dopo i picchi principali, tempo di dimezzamento dell'eccesso sopra la base
base = st.median(v for _, v in liv)
print("livello mediano annuo", base)
for r in sorted(righe, key=lambda r: -r[4])[:6]:
    tp = r[0] + timedelta(hours=r[5]); lp = L(tp)
    for h in (12, 24, 48):
        pass
    vals = [L(tp + timedelta(hours=h)) for h in (6, 12, 24, 48, 72)]
    print(f"recessione dopo picco {tp.astimezone(R):%d/%m %H:%M} {lp:+.2f}: " + " ".join(f"{h}h {v:+.2f}" for h, v in zip((6,12,24,48,72), vals) if v is not None))
k = sorted(r[4] / r[1] for r in righe if r[1] >= 15)
q = lambda p: k[min(len(k) - 1, max(0, round(p * (len(k) - 1))))]
print(f"\nk (m/mm) su {len(k)} eventi >=15 mm: p20 {q(0.2):.4f}  p50 {q(0.5):.4f}  p80 {q(0.8):.4f}")
# verifica in-sample: errore della stima centrale sulla salita
err = [r[4] - q(0.5) * r[1] for r in righe if r[1] >= 15]
print("errore stima centrale (m): mediana", round(st.median(err), 3), "| |err| mediano", round(st.median(abs(e) for e in err), 3),
      "| dentro [p20,p80]:", sum(1 for r in righe if r[1] >= 15 and q(0.2) * r[1] - 0.03 <= r[4] <= q(0.8) * r[1] + 0.03), "/", len(err))
