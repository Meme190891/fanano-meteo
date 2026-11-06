"""Elaborazione: storico, cumulate, tendenza, soglie, stato complessivo, dati vecchi, fallback.

Tutte funzioni pure (nessun accesso alla rete): ricevono lo stato precedente, i risultati
della raccolta e l'istante corrente, e restituiscono il nuovo stato e il contenuto di widget.json.

Lo *stato* (state.json) e' un dizionario JSON con:
  serie:     {nome_serie: [[iso_utc, valore], ...]}    storico delle ultime `storico_ore`
  idrometri: {id: {...Idrometro..., "ora": iso}}         ultimo valore e soglie validi
  allerte:   {data_inizio: {...Allerta...}}              documenti di allertamento ricevuti
  previsione:{"giorni": [...], "ora": iso}               ultima previsione valida
  fonti:     {endpoint: {"ultimo_ok", "ultimo_tentativo", "errore"}}
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta, timezone

from fanano.arpae import ROME, Serie

UTC = timezone.utc
VERSIONE_STATO = 1

# colore Arpae -> (nome italiano, livello 0..3)
ALLERTA = {"green": ("verde", 0), "yellow": ("gialla", 1), "orange": ("arancione", 2), "red": ("rossa", 3)}
LIVELLO_COLORE = {0: "verde", 1: "giallo", 2: "arancio", 3: "rosso", -1: "grigio"}


# --------------------------------------------------------------------------- serializzazione

def jsonable(obj):
    """Dataclass/datetime/date -> strutture JSON (datetime in ISO con fuso)."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: jsonable(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    return obj


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def serie_da_stato(lst) -> Serie:
    return sorted((datetime.fromisoformat(t), float(v)) for t, v in (lst or []))


def serie_a_stato(serie: Serie) -> list:
    return [[t.astimezone(UTC).isoformat(), v] for t, v in serie]


def unisci_serie(vecchia: Serie, nuova: Serie, da: datetime) -> Serie:
    """Unione per timestamp (il dato nuovo vince), solo punti con t >= da."""
    punti = {t: v for t, v in vecchia}
    punti.update({t: v for t, v in nuova})
    return sorted((t, v) for t, v in punti.items() if t >= da)


# --------------------------------------------------------------------------- formattazione

def fmt_num(x: float | None, dec: int = 1) -> str:
    return "n.d." if x is None else f"{x:.{dec}f}"


def fmt_ora(t: datetime | None, now: datetime) -> str:
    """'11:00' se e' oggi (ora italiana), altrimenti '05/11 23:00'."""
    if t is None:
        return "n.d."
    lt, ln = t.astimezone(ROME), now.astimezone(ROME)
    return lt.strftime("%H:%M") if lt.date() == ln.date() else lt.strftime("%d/%m %H:%M")


def fmt_range_mm(pmin: float | None, pmax: float | None) -> str:
    if pmin is None and pmax is None:
        return "n.d."
    pmin = pmin if pmin is not None else pmax
    pmax = pmax if pmax is not None else pmin
    a, b = (fmt_num(v, 0) if float(v).is_integer() else fmt_num(v) for v in (pmin, pmax))
    return f"{a} mm" if a == b else f"{a}-{b} mm"


def accorcia(testo: str, n: int) -> str:
    testo = " ".join((testo or "").split())
    if len(testo) <= n:
        return testo
    taglio = testo[: n - 1].rsplit(" ", 1)[0].rstrip(",;:")
    return taglio + "…"


# --------------------------------------------------------------------------- calcoli

def cumulata(serie_oraria: Serie, ore: int) -> tuple[float | None, bool]:
    """Somma dei valori orari nelle ultime `ore` ore fino all'ultimo dato.

    Ogni valore e' la pioggia dell'ora che *termina* al suo timestamp.
    Ritorna (mm, completa): completa=False se nello storico mancano ore.
    """
    if not serie_oraria:
        return None, False
    fine = serie_oraria[-1][0]
    inizio = fine - timedelta(hours=ore)
    valori = [v for t, v in serie_oraria if inizio < t <= fine]
    return round(sum(valori), 1), len(valori) >= ore


def tendenza(serie: Serie, ore: float = 3, soglia_m: float = 0.05, tolleranza_min: float = 20
             ) -> tuple[str, str, float | None]:
    """(etichetta, freccia, delta_m) confrontando l'ultimo livello con quello di `ore` ore prima."""
    if not serie:
        return "n.d.", "?", None
    t_ult, v_ult = serie[-1]
    obiettivo = t_ult - timedelta(hours=ore)
    candidati = [(abs((t - obiettivo).total_seconds()), v) for t, v in serie
                 if abs((t - obiettivo).total_seconds()) <= tolleranza_min * 60]
    if not candidati:
        return "n.d.", "?", None
    v_rif = min(candidati)[1]
    delta = round(v_ult - v_rif, 3)
    if delta >= soglia_m - 1e-9:
        return "su", "↑", delta
    if delta <= -soglia_m + 1e-9:
        return "giù", "↓", delta
    return "stabile", "→", delta


def stato_soglie(valore: float | None, s1: float | None, s2: float | None, s3: float | None
                 ) -> tuple[int | None, str]:
    """(livello 0..3 o None, etichetta). Soglie None = non definite."""
    if valore is None:
        return None, "n.d."
    if s1 is None and s2 is None and s3 is None:
        return None, "senza soglie"
    for idx, s in ((3, s3), (2, s2), (1, s1)):
        if s is not None and valore >= s:
            return idx, f"soglia {idx}"
    return 0, "normale"


def _vecchio(t: datetime | None, now: datetime, ore: float) -> bool:
    return t is None or (now - t) > timedelta(hours=ore)


# --------------------------------------------------------------------------- aggiornamento stato (fallback)

def stato_vuoto() -> dict:
    return {"versione": VERSIONE_STATO, "aggiornato": None, "serie": {}, "idrometri": {},
            "allerte": {}, "previsione": None, "fonti": {}}


def aggiorna_stato(stato: dict | None, raccolta: dict, now: datetime, cfg: dict) -> tuple[dict, list[str]]:
    """Integra i risultati della raccolta nello stato precedente.

    `raccolta`: {endpoint: valore_parsato} oppure {endpoint: Exception} se la fonte e' fallita.
    Una fonte fallita non cancella nulla: resta l'ultimo dato valido con il suo timestamp.
    Ritorna (nuovo_stato, errori_di_questa_esecuzione).
    """
    st = stato_vuoto()
    if stato and stato.get("versione") == VERSIONE_STATO:
        st.update({k: stato.get(k, st[k]) for k in st})
    errori: list[str] = []
    da = now - timedelta(hours=cfg["regole"]["storico_ore"])
    now_iso = now.astimezone(UTC).isoformat()

    for nome, ris in raccolta.items():
        fonte = dict(st["fonti"].get(nome) or {})
        fonte["ultimo_tentativo"] = now_iso
        if isinstance(ris, Exception):
            fonte["errore"] = f"{type(ris).__name__}: {ris}"[:200]
            errori.append(f"{nome}: {type(ris).__name__}")
            st["fonti"][nome] = fonte
            continue
        fonte["errore"] = None
        fonte["ultimo_ok"] = now_iso
        st["fonti"][nome] = fonte

        if nome == "livelli":
            for sid, idro in ris.items():
                d = jsonable(idro)
                d["ora"] = now_iso
                st["idrometri"][sid] = d
        elif nome.startswith(("livello_", "pioggia_")):
            vecchia = serie_da_stato(st["serie"].get(nome))
            st["serie"][nome] = serie_a_stato(unisci_serie(vecchia, ris, da))
        elif nome.startswith("allerta_"):
            if ris is not None and ris.inizio is not None:
                st["allerte"][ris.inizio.date().isoformat()] = jsonable(ris)
        elif nome == "previsione":
            st["previsione"] = {"giorni": jsonable(ris), "ora": now_iso}

    # potatura: serie oltre lo storico, allerte terminate da piu' di 2 giorni
    for nome, lst in list(st["serie"].items()):
        st["serie"][nome] = serie_a_stato([p for p in serie_da_stato(lst) if p[0] >= da])
    limite = now - timedelta(days=2)
    st["allerte"] = {k: a for k, a in st["allerte"].items() if (_dt(a.get("fine")) or now) >= limite}
    st["aggiornato"] = now_iso
    return st, errori


# --------------------------------------------------------------------------- widget.json

def _allerta_valida(allerte: dict, now: datetime) -> tuple[dict | None, bool]:
    """Documento valido adesso; altrimenti il piu' recente con flag vecchio=True."""
    docs = sorted(allerte.values(), key=lambda a: a.get("inizio") or "")
    for a in docs:
        i, f = _dt(a.get("inizio")), _dt(a.get("fine"))
        if i and f and i <= now < f:
            return a, False
    return (docs[-1], True) if docs else (None, True)


def _max_allerta(colori: dict, eventi: list[str] | None = None) -> tuple[int, str, list[str]]:
    """(livello 0..3, nome colore, eventi non verdi) sugli eventi indicati (tutti se None)."""
    livello, nomi = 0, []
    for ev, col in colori.items():
        if eventi is not None and ev not in eventi:
            continue
        nome, lv = ALLERTA.get(col, ("", 0))
        if lv > 0:
            nomi.append(f"{ev.replace('_', ' ')} {nome}")
        livello = max(livello, lv)
    return livello, [k for k, (_, v) in ALLERTA.items() if v == livello][0], nomi


def costruisci_widget(st: dict, cfg: dict, now: datetime, errori: list[str] | None = None) -> dict:
    """Contenuto di widget.json: chiavi piatte, valori gia' formattati (vedi README)."""
    reg, col = cfg["regole"], cfg["colori"]
    pub = cfg["pubblicazione"]
    base = pub["base_url"].rstrip("/")
    oggi = now.astimezone(ROME).date()
    w: dict = {
        "aggiornato": now.astimezone(ROME).strftime("%d/%m %H:%M"),
        "aggiornato_iso": now.astimezone(ROME).isoformat(timespec="seconds"),
    }
    vecchi: dict[str, bool] = {}
    # candidati per lo stato complessivo: (livello 1..3, regola, messaggio); regola = ordine nel README
    allarmi: list[tuple[int, int, str]] = []

    # ---- torrenti
    in_crescita = []
    for t in cfg["torrenti"]:
        k = t["chiave"]
        serie = serie_da_stato(st["serie"].get(f"livello_{k}"))
        idro = st["idrometri"].get(t["id"], {})
        t_ult, v_ult = (serie[-1] if serie else (_dt(idro.get("ora")), idro.get("valore")))
        idx, etichetta = stato_soglie(v_ult, idro.get("soglia1"), idro.get("soglia2"), idro.get("soglia3"))
        tend, freccia, delta = tendenza(serie, reg["tendenza_ore"], reg["tendenza_soglia_m"],
                                        reg["tendenza_tolleranza_min"])
        vecchio = _vecchio(t_ult, now, reg["dato_vecchio_ore"])
        vecchi[k] = vecchio
        soglie = [idro.get(f"soglia{i}") for i in (1, 2, 3)]
        w.update({
            f"{k}_nome": t["nome"],
            f"{k}_livello": f"{v_ult:.2f} m" if v_ult is not None else "n.d.",
            f"{k}_tendenza": tend,
            f"{k}_freccia": freccia,
            f"{k}_delta3h": f"{delta:+.2f} m" if delta is not None else "n.d.",
            f"{k}_soglia": etichetta,
            f"{k}_colore": col[LIVELLO_COLORE[idx if idx is not None else -1]],
            f"{k}_soglie": " / ".join(fmt_num(s, 1) if s is not None else "-" for s in soglie) + " m",
            f"{k}_ora": fmt_ora(t_ult, now),
            f"{k}_vecchio": vecchio,
            f"{k}_grafico": f"{base}/{k}.png",
        })
        breve = t.get("nome_breve", t["nome"])
        if idx:
            allarmi.append((idx, 1, f"{breve} sopra soglia {idx}"))
        if tend == "su":
            in_crescita.append(breve)
    w["nota_torrenti"] = cfg.get("nota_torrenti", "")

    # ---- pioggia osservata
    pioggia_24h_max: tuple[float, str] | None = None
    for p in cfg["pluviometri"]:
        k = p["chiave"]
        serie = serie_da_stato(st["serie"].get(f"pioggia_{k}"))
        t_ult = serie[-1][0] if serie else None
        vecchio = _vecchio(t_ult, now, reg["dato_vecchio_ore"])
        vecchi[k] = vecchio
        w[f"{k}_nome"] = p["nome"]
        for ore in (1, 6, 24, 72):
            mm, completa = cumulata(serie, ore)
            w[f"{k}_{ore}h"] = (f"{mm:.1f}" + ("" if completa else "*")) if mm is not None else "n.d."
            if ore == 72:
                w[f"{k}_72h_parziale"] = not completa
            if ore == 24 and mm is not None and (pioggia_24h_max is None or mm > pioggia_24h_max[0]):
                pioggia_24h_max = (mm, p.get("nome_breve", p["nome"]))
        w[f"{k}_ora"] = fmt_ora(t_ult, now)
        w[f"{k}_vecchio"] = vecchio

    # ---- previsione (giorni di calendario, colonna configurata)
    prev = st.get("previsione") or {}
    per_data = {g["data"]: g for g in prev.get("giorni", []) if g.get("data")}
    giorni = [per_data.get((oggi + timedelta(days=i)).isoformat()) for i in range(3)]
    for nome_g, g in zip(("oggi", "domani", "dopodomani"), giorni):
        w[f"prev_{nome_g}"] = fmt_range_mm(g["prec_min"], g["prec_max"]) if g else "n.d."
    ora_locale = now.astimezone(ROME).hour
    idx24 = 0 if ora_locale < reg["previsione_cambio_ora"] else 1
    g24 = giorni[idx24]
    w["prev_24h"] = w["prev_oggi" if idx24 == 0 else "prev_domani"]
    w["prev_24h_etichetta"] = "oggi" if idx24 == 0 else "domani"
    disp = [g for g in giorni if g and g.get("prec_max") is not None]
    if disp:
        tot = fmt_range_mm(sum(g["prec_min"] or 0 for g in disp), sum(g["prec_max"] for g in disp))
        w["prev_72h"] = tot + ("" if len(disp) == 3 else "*")
    else:
        w["prev_72h"] = "n.d."
    w["prev_testo"] = accorcia(g24["sintesi"], reg["testo_previsione_max"]) if g24 else "n.d."
    w["prev_zona"] = f"{cfg['previsione']['provincia']} {cfg['previsione']['zona']}"
    prev_ora = _dt(prev.get("ora"))
    w["prev_aggiornata"] = fmt_ora(prev_ora, now)
    w["prev_vecchio"] = giorni[0] is None or _vecchio(prev_ora, now, reg["previsione_vecchia_ore"])
    vecchi["previsione"] = w["prev_vecchio"]
    for nome_g, g in zip(("oggi", "domani"), giorni[:2]):
        if g and g.get("prec_max") is not None and g["prec_max"] >= reg["pioggia_prevista_mm"]:
            allarmi.append((1, 5, f"Pioggia abbondante prevista {nome_g} "
                                  f"({fmt_range_mm(g['prec_min'], g['prec_max'])})"))
            break

    # ---- allerta della zona
    zona = cfg["zona_allerta"]
    a, a_vecchia = _allerta_valida(st.get("allerte", {}), now)
    w["allerta_zona"] = zona
    if a:
        lv, colore, non_verdi = _max_allerta(a.get("colori", {}))
        lv_ril, colore_ril, _ = _max_allerta(a.get("colori", {}), reg["eventi_allerta"])
        w["allerta_oggi"] = ALLERTA[colore][0]
        w["allerta_oggi_colore"] = col[LIVELLO_COLORE[lv]]
        w["allerta_oggi_eventi"] = ", ".join(non_verdi)
        w["allerta_titolo"] = a.get("titolo", "")
        w["allerta_link"] = a.get("link") or ""
        w["allerta_emessa"] = fmt_ora(_dt(a.get("emissione")), now)
        if lv_ril and not a_vecchia:
            allarmi.append((lv_ril, 2, f"Allerta {ALLERTA[colore_ril][0]} zona {zona}"))
    else:
        w.update({"allerta_oggi": "n.d.", "allerta_oggi_colore": col["grigio"], "allerta_oggi_eventi": "",
                  "allerta_titolo": "", "allerta_link": "", "allerta_emessa": "n.d."})
    w["allerta_vecchio"] = a_vecchia
    vecchi["allerta"] = a_vecchia
    domani_doc = st.get("allerte", {}).get((oggi + timedelta(days=1)).isoformat())
    if domani_doc:
        lv_d, colore_d, _ = _max_allerta(domani_doc.get("colori", {}))
        w["allerta_domani"] = ALLERTA[colore_d][0]
        w["allerta_domani_colore"] = col[LIVELLO_COLORE[lv_d]]
    else:
        w["allerta_domani"] = "non ancora emessa"
        w["allerta_domani_colore"] = col["grigio"]

    # ---- stato complessivo (prima regola vera vince, vedi README)
    if in_crescita:
        allarmi.append((1, 3, f"{' e '.join(in_crescita)} in crescita"))
    if pioggia_24h_max and pioggia_24h_max[0] >= reg["pioggia_osservata_24h_mm"]:
        allarmi.append((1, 4, f"Pioggia abbondante ultime 24h ({pioggia_24h_max[1]} {pioggia_24h_max[0]:.0f} mm)"))
    allarmi.sort(key=lambda a: (-a[0], a[1]))
    if allarmi:
        livello = allarmi[0][0]
        testo = f"{'ALLARME' if livello == 3 else 'Attenzione'}: {allarmi[0][2]}"
    elif all(vecchi.values()):
        livello, testo = -1, "Dati non aggiornati"
    else:
        livello, testo = 0, "Tutto regolare"
    if livello >= 0 and any(vecchi.values()) and not all(vecchi.values()):
        testo += " · alcuni dati vecchi"
    w["stato"] = testo
    w["stato_dettaglio"] = "; ".join(m for _, _, m in allarmi)
    w["stato_livello"] = livello
    w["stato_colore"] = col[LIVELLO_COLORE[livello]]
    w["dato_vecchio"] = any(vecchi.values())

    # ---- righe gia' composte per il widget (una formula KWGT per riga)
    for t in cfg["torrenti"]:
        k = t["chiave"]
        w[f"riga_{k}"] = (f"{t.get('nome_breve', t['nome'])} {w[f'{k}_livello']} {w[f'{k}_freccia']}"
                          + (" !" if w[f"{k}_vecchio"] else ""))
    w["riga_pioggia"] = "1h/24h mm: " + " · ".join(
        f"{p.get('sigla', p.get('nome_breve', p['nome']))} {w[p['chiave'] + '_1h']}/{w[p['chiave'] + '_24h']}"
        for p in cfg["pluviometri"])
    w["riga_previsione"] = (f"Prev. oggi {w['prev_oggi'].replace(' mm', '')} · dom. "
                            f"{w['prev_domani'].replace(' mm', '')} · 3gg {w['prev_72h']}")
    w["riga_allerta"] = f"Allerta {zona}: oggi {w['allerta_oggi']} · domani {w['allerta_domani']}"
    w["riga_aggiornamento"] = (f"Agg. {now.astimezone(ROME):%H:%M}"
                               + (" · DATI VECCHI" if w["dato_vecchio"] else "") + " · Arpae, non validati")

    # ---- metadati
    w["errori"] = "; ".join(errori or [])
    w["pagina"] = f"{base}/index.html"
    w["disclaimer"] = pub["disclaimer"]
    w["fonte"] = pub["fonte"]
    in_testa = ["aggiornato", "aggiornato_iso", "stato", "stato_dettaglio", "stato_livello", "stato_colore",
                "dato_vecchio", "errori"]
    return {**{k: w[k] for k in in_testa}, **{k: v for k, v in w.items() if k not in in_testa}}

