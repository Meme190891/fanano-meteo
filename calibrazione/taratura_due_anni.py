"""Eventi di pioggia vs salita del Leo su due anni; confronto di regole con verifica incrociata tra anni."""
import csv, sys, statistics as st
from datetime import datetime, timedelta, timezone
def leggi(f, fine=False):
    return sorted((datetime.fromisoformat(a[1] if fine else a[0]), float(a[2]))
                  for a in csv.reader(open(f, encoding="utf-8")) if len(a) == 3 and a[0][:2] == "20" and a[2].strip())
liv = [(t, v) for t, v in leggi(sys.argv[1]) if v > -0.7 or t.month not in (12,)]
pr = dict(leggi(sys.argv[2], True)); sc = dict(leggi(sys.argv[3], True))
ld = dict(liv)
def L(t):
    for d in range(0, 9):
        for s in (1, -1):
            x = ld.get(t + s * timedelta(minutes=15 * d))
            if x is not None: return x
print(f"livello: min {min(v for _,v in liv):.2f}  max {max(v for _,v in liv):.2f}  (giorno max {max(liv,key=lambda x:x[1])[0]:%d/%m/%Y})")
tempi = sorted(set(pr) | set(sc))
ev, cur = [], None
for t in tempi:
    if max(pr.get(t, 0), sc.get(t, 0)) <= 0: continue
    if cur and t - cur["fine"] <= timedelta(hours=12): cur["fine"] = t
    else:
        if cur: ev.append(cur)
        cur = {"ini": t - timedelta(minutes=30), "fine": t}
ev.append(cur)
E = []
for e in ev:
    passi = [t for t in tempi if e["ini"] < t <= e["fine"]]
    n_att = max(1, int((e["fine"] - e["ini"]).total_seconds() // 1800))
    pp = sum(pr.get(t, 0) for t in passi); ps = sum(sc.get(t, 0) for t in passi)
    cop_s = sum(1 for t in passi if t in sc) / n_att
    cop_p = sum(1 for t in passi if t in pr) / n_att
    if max(pp, ps) < 15: continue
    l0 = L(e["ini"]); w = [v for t, v in liv if e["ini"] <= t <= e["fine"] + timedelta(hours=12)]
    if l0 is None or len(w) < 10: continue
    anno = "A" if e["ini"] < datetime(2025, 11, 1, tzinfo=timezone.utc) else "B"
    # scaffaiolo "affidabile" se coperto e non a zero mentre Pratignano registra >=15 mm
    s_ok = cop_s > 0.9 and not (ps < 0.2 * pp and pp >= 15)
    E.append(dict(t=e["ini"], pp=pp, ps=ps, s_ok=s_ok, p_ok=cop_p > 0.9, sal=max(w) - l0, l0=l0, anno=anno))
print(f"eventi >=15 mm: {len(E)} (anno A 2024-25: {sum(e['anno']=='A' for e in E)}, anno B 2025-26: {sum(e['anno']=='B' for e in E)}); "
      f"Scaffaiolo affidabile in {sum(e['s_ok'] for e in E)}")
def pioggia(e, regola, par):
    if regola == "prat": return e["pp"]
    if regola == "scaf": return e["ps"] if e["s_ok"] else e["pp"] * par.get("rapporto", 1)
    if regola == "media": return (e["pp"] + e["ps"]) / 2 if e["s_ok"] else e["pp"]
    if regola == "max": return max(e["pp"], e["ps"]) if e["s_ok"] else e["pp"]
def tara(train, regola):
    par = {}
    if regola == "scaf":
        r = [e["ps"] / e["pp"] for e in train if e["s_ok"] and e["pp"] > 5]
        par["rapporto"] = st.median(r) if r else 1
    k = sorted(e["sal"] / pioggia(e, regola, par) for e in train if pioggia(e, regola, par) > 0)
    q = lambda p: k[round(p * (len(k) - 1))]
    par.update(b=q(0.2), c=q(0.5), a=q(0.8)); return par
def prova(test, regola, par):
    err = [abs(e["sal"] - par["c"] * pioggia(e, regola, par)) for e in test]
    dentro = sum(1 for e in test if par["b"] * pioggia(e, regola, par) - 0.03 <= e["sal"] <= par["a"] * pioggia(e, regola, par) + 0.03)
    return st.median(err), dentro / len(test)
print("\nregola   | tara A prova B: err mediano, dentro forbice | tara B prova A | tara su tutto: k basso/centr/alto")
for regola in ("prat", "scaf", "media", "max"):
    A = [e for e in E if e["anno"] == "A"]; B = [e for e in E if e["anno"] == "B"]
    pAB = prova(B, regola, tara(A, regola)); pBA = prova(A, regola, tara(B, regola)); tutto = tara(E, regola)
    print(f"{regola:8s} | {pAB[0]:.3f} m, {pAB[1]:.0%}                   | {pBA[0]:.3f} m, {pBA[1]:.0%}   | "
          f"{tutto['b']:.4f} / {tutto['c']:.4f} / {tutto['a']:.4f}" + (f"  (rapporto Scaff/Prat {tutto['rapporto']:.2f})" if 'rapporto' in tutto else ""))
# effetto stagione e terreno bagnato (pioggia dei 7 giorni prima) sul coefficiente, regola 'media'
print("\ncoefficiente (salita/mm, regola media) per stagione e per terreno:")
for nome, f in (("ott-apr", lambda e: e["t"].month in (10, 11, 12, 1, 2, 3, 4)), ("mag-set", lambda e: e["t"].month in (5, 6, 7, 8, 9))):
    k = [e["sal"] / pioggia(e, "media", {}) for e in E if f(e)]
    print(f"  {nome}: n {len(k)}, mediana {st.median(k):.4f}")
for nome, f in (("partenza alta (>= -0.35 m)", lambda e: e["l0"] >= -0.35), ("partenza bassa (< -0.35 m)", lambda e: e["l0"] < -0.35)):
    k = [e["sal"] / pioggia(e, "media", {}) for e in E if f(e)]
    print(f"  {nome}: n {len(k)}, mediana {st.median(k):.4f}")
print("\npiene maggiori (salita) e stima con regola 'prat' tarata su tutto:")
par = tara(E, "prat")
for e in sorted(E, key=lambda e: -e["sal"])[:10]:
    p = e["pp"]
    print(f"  {e['t']:%d/%m/%y}  Prat {e['pp']:6.1f}  Scaff {e['ps']:6.1f}{'' if e['s_ok'] else '(n.a.)'}  partenza {e['l0']:+.2f}  "
          f"salita reale {e['sal']:+.2f}  stimata {par['b']*p:+.2f}..{par['a']*p:+.2f}")
# esaurimento dopo le piene maggiori: costante di tempo stimata dall'eccesso sopra la base a 24 h
print("\nesaurimento (tau, ore) dopo le piene:")
taus = []
import math
for e in sorted(E, key=lambda e: -e["sal"])[:12]:
    w = [(t, v) for t, v in liv if e["t"] <= t <= e["t"] + timedelta(days=4)]
    tp, vp = max(w, key=lambda x: x[1]); base = e["l0"]
    v24 = L(tp + timedelta(hours=24))
    if v24 is None or vp - base < 0.15: continue
    pioggia_dopo = sum(pr.get(t, 0) for t in tempi if tp < t <= tp + timedelta(hours=24))
    if pioggia_dopo > 3: continue
    r = (v24 - base) / (vp - base)
    if 0 < r < 1:
        taus.append(-24 / math.log(r)); print(f"  {tp:%d/%m/%y}  picco {vp:+.2f} -> 24h {v24:+.2f}  tau {taus[-1]:.0f} h")
print("  tau mediana", round(st.median(taus)))
# Regola a due stazioni: salita = a*Prat + b*Scaff (minimi quadrati senza intercetta), solo eventi con Scaffaiolo affidabile
def fit2(train):
    T = [e for e in train if e["s_ok"]]
    sxx = sum(e["pp"] ** 2 for e in T); syy = sum(e["ps"] ** 2 for e in T); sxy = sum(e["pp"] * e["ps"] for e in T)
    sxz = sum(e["pp"] * e["sal"] for e in T); syz = sum(e["ps"] * e["sal"] for e in T)
    det = sxx * syy - sxy ** 2
    a = (sxz * syy - syz * sxy) / det; b = (syz * sxx - sxz * sxy) / det
    res = sorted(e["sal"] - (a * e["pp"] + b * e["ps"]) for e in T)
    return a, b, res[round(0.2 * (len(res) - 1))], res[round(0.8 * (len(res) - 1))]
def prova2(test, m, par1):
    a, b, r20, r80 = m; err, dentro, big = [], 0, []
    for e in test:
        if e["s_ok"]:
            c = a * e["pp"] + b * e["ps"]; lo, hi = c + r20, c + r80
        else:
            c = par1["c"] * e["pp"]; lo, hi = par1["b"] * e["pp"], par1["a"] * e["pp"]
        err.append(abs(e["sal"] - c)); dentro += lo - 0.03 <= e["sal"] <= hi + 0.03
        if e["sal"] > 0.6: big.append(e["sal"] - c)
    return st.median(err), dentro / len(test), big
A = [e for e in E if e["anno"] == "A"]; B = [e for e in E if e["anno"] == "B"]
print("\nregola due stazioni (Scaffaiolo affidabile) + solo Pratignano altrimenti:")
for nome, tr, te in (("tara A prova B", A, B), ("tara B prova A", B, A)):
    m = fit2(tr); e_, d_, big = prova2(te, m, tara(tr, "prat"))
    e1, d1 = prova(te, "prat", tara(tr, "prat"))
    print(f"  {nome}: a={m[0]:.4f} b={m[1]:.4f} | errore mediano {e_:.3f} m (solo Prat {e1:.3f}) | dentro forbice {d_:.0%} (solo Prat {d1:.0%})"
          f" | errore sulle piene >0.6 m: {', '.join(f'{x:+.2f}' for x in big)}")
m = fit2(E); print(f"  tarata su tutto: salita = {m[0]:.4f} x Prat + {m[1]:.4f} x Scaff, residui p20 {m[2]:+.3f} p80 {m[3]:+.3f}")
for e in sorted(E, key=lambda e: -e["sal"])[:6]:
    if e["s_ok"]:
        c = m[0] * e["pp"] + m[1] * e["ps"]
        print(f"    {e['t']:%d/%m/%y} reale {e['sal']:+.2f}  stima {c+m[2]:+.2f}..{c+m[3]:+.2f}")
def k_scaf(train):
    k = sorted(e["sal"] / e["ps"] for e in train if e["s_ok"] and e["ps"] > 0)
    return k[round(0.8 * (len(k) - 1))]
def prova3(test, par, ks):
    dentro, sopra, sotto, big = 0, [], 0, []
    for e in test:
        lo = par["b"] * e["pp"]; hi = max(par["a"] * e["pp"], ks * e["ps"] if e["s_ok"] else 0)
        ok = lo - 0.03 <= e["sal"] <= hi + 0.03; dentro += ok
        if e["sal"] > hi + 0.03: sotto += 1
        if e["sal"] > 0.6: big.append(f"{e['sal']:+.2f} in [{lo:+.2f},{hi:+.2f}]")
        sopra.append(hi - e["sal"])
    return dentro / len(test), sotto, st.median(sopra), big
print("\nregola: basso/centrale Pratignano, alto = max(Prat alto, Scaff alto):")
for nome, tr, te in (("tara A prova B", A, B), ("tara B prova A", B, A), ("tutto", E, E)):
    par = tara(tr, "prat"); ks = k_scaf(tr); d, sotto, marg, big = prova3(te, par, ks)
    d1 = prova(te, "prat", par)[1]
    print(f"  {nome}: k_scaf_alto {ks:.4f} | dentro forbice {d:.0%} (solo Prat {d1:.0%}) | salite oltre il limite alto: {sotto}"
          f" | margine mediano sopra il reale {marg:+.2f} m\n     piene >0.6 m: " + "; ".join(big))
