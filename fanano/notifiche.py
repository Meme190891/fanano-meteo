"""Notifiche Telegram su eventi prestabiliti (vedi README, "Notifiche").

Eventi (soglie in config.yaml, sezione `notifiche`), ognuno con un messaggio di inizio e uno di fine:
  * leo_salita: il Leo sale di almeno `leo_salita_m` rispetto a `tendenza_ore` ore prima;
    finisce quando la salita scende sotto `leo_fine_salita_m`;
  * pioggia:    in un'ora cadono almeno `pioggia_oraria_mm` a uno dei pluviometri;
    finisce dopo `pioggia_fine_ore` ore senza ore oltre soglia;
  * allerta:    allerta gialla, arancione o rossa per la zona, oggi o domani (avviso a ogni nuovo
    colore per un giorno); finisce quando oggi e domani sono verdi;
  * guasto:     nessun dato osservato nuovo da `guasto_ore` ore; finisce quando i dati tornano.

Lo stato delle notifiche vive in state.json (chiave "notifiche"). Tutti i messaggi di un'esecuzione
partono in un solo invio: se l'invio fallisce lo stato non avanza e si riprova all'esecuzione dopo.
Il token del bot e l'id della chat arrivano solo dalle variabili d'ambiente (segreti di GitHub).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import requests

from fanano import compute
from fanano.compute import ALLERTA, ROME, _dt, serie_da_stato

ORDINE_ALLERTA = {"green": 0, "yellow": 1, "orange": 2, "red": 3}


def _ora(t: datetime) -> str:
    return t.astimezone(ROME).strftime("%H:%M")


def _giorno(d: str, oggi) -> str:
    g = datetime.fromisoformat(d).date()
    if g == oggi:
        return "oggi"
    if g == oggi + timedelta(days=1):
        return "domani"
    return g.strftime("%d/%m")


def _m(x: float) -> str:
    return f"{x:.2f} m".replace("-", "−")


# --------------------------------------------------------------------------- singoli eventi

def _leo(st: dict, cfg: dict, prec: dict | None, msgs: list[str]) -> dict | None:
    nc, reg = cfg["notifiche"], cfg["regole"]
    pc = cfg.get("previsione_leo") or {}
    chiave = pc.get("torrente", cfg["torrenti"][0]["chiave"])
    nome = next(t["nome_breve"] for t in cfg["torrenti"] if t["chiave"] == chiave)
    serie = serie_da_stato(st["serie"].get(f"livello_{chiave}"))
    if not serie:
        return prec
    _, _, delta = compute.tendenza(serie, reg["tendenza_ore"], reg["tendenza_soglia_m"],
                                   reg["tendenza_tolleranza_min"])
    t, v = serie[-1]
    if delta is None:
        return prec
    if prec is None:
        if delta >= nc["leo_salita_m"] - 1e-9:
            msgs.append(f"🌊 {nome} in crescita: {_m(v)} alle {_ora(t)}, "
                        f"+{delta * 100:.0f} cm nelle ultime {reg['tendenza_ore']} ore.")
            return {"inizio": t.isoformat(), "partenza": round(v - delta, 3), "max": v, "ora_max": t.isoformat()}
        return None
    att = dict(prec)
    if v > att["max"]:
        att["max"], att["ora_max"] = v, t.isoformat()
    if delta <= nc["leo_fine_salita_m"] + 1e-9:
        msgs.append(f"✅ {nome}: ha smesso di salire. Ora {_m(v)} alle {_ora(t)}; massimo {_m(att['max'])} "
                    f"alle {_ora(_dt(att['ora_max']))} (era {_m(att['partenza'])} all'inizio della salita).")
        return None
    return att


def _pioggia(st: dict, cfg: dict, now: datetime, prec: dict | None, msgs: list[str]) -> dict | None:
    nc = cfg["notifiche"]
    soglia = nc["pioggia_oraria_mm"]
    da = now - timedelta(hours=nc["pioggia_fine_ore"])
    forti = []                                   # (stazione, ora, mm) nelle ultime ore
    for p in cfg["pluviometri"]:
        for t, v in serie_da_stato(st["serie"].get(f"pioggia_{p['chiave']}")):
            if t > da and v >= soglia - 1e-9:
                forti.append((p, t, v))
    if prec is None:
        if not forti:
            return None
        p, t, v = max(forti, key=lambda x: (x[1], x[2]))
        altre = sorted({f"{q['nome_breve']} {w:.1f} mm" for q, s, w in forti if q is not p and s == t})
        msgs.append(f"🌧️ Pioggia forte a {p['nome_breve']}: {v:.1f} mm nell'ora fino alle {_ora(t)}"
                    + (f" (anche {', '.join(altre)})" if altre else "") + ".")
        inizio = min(s for _, s, _ in forti) - timedelta(hours=1)
        return {"inizio": inizio.isoformat()}
    if forti:
        return prec
    inizio = _dt(prec["inizio"])
    totali = []
    for p in cfg["pluviometri"]:
        tot = sum(v for t, v in serie_da_stato(st["serie"].get(f"pioggia_{p['chiave']}")) if t > inizio)
        totali.append(f"{p['nome_breve']} {tot:.1f} mm")
    msgs.append(f"✅ Pioggia forte terminata (nessuna ora oltre {soglia:g} mm da {nc['pioggia_fine_ore']} ore). "
                f"Caduti dalle {_ora(inizio)}: {', '.join(totali)}.")
    return None


def _allerte_attive(st: dict, cfg: dict, now: datetime) -> dict[str, dict]:
    """{data: {"colore", "eventi"}} per oggi e domani con allerta non verde."""
    oggi = now.astimezone(ROME).date()
    eventi = cfg["notifiche"].get("allerta_eventi")
    out = {}
    for d in (oggi, oggi + timedelta(days=1)):
        a = st.get("allerte", {}).get(d.isoformat())
        if not a:
            continue
        colori = {ev: c for ev, c in (a.get("colori") or {}).items()
                  if c in ORDINE_ALLERTA and (not eventi or ev in eventi)}
        lv = max(ORDINE_ALLERTA[c] for c in colori.values()) if colori else 0
        if lv:
            col = next(c for c, n in ORDINE_ALLERTA.items() if n == lv)
            out[d.isoformat()] = {"colore": col,
                                  "eventi": sorted(ev.replace("_", " ") for ev, c in colori.items() if c == col)}
    return out


def _allerta(st: dict, cfg: dict, now: datetime, prec: dict | None, msgs: list[str]) -> dict | None:
    zona = cfg["zona_allerta"]
    oggi = now.astimezone(ROME).date()
    attive = _allerte_attive(st, cfg, now)
    annunciate = dict((prec or {}).get("annunciate", {}))
    nuove = [(d, a) for d, a in sorted(attive.items()) if annunciate.get(d) != a["colore"]]
    for d, a in nuove:
        cambio = d in annunciate
        msgs.append(f"{'⚠️' if a['colore'] == 'yellow' else '🚨'} Allerta {ALLERTA[a['colore']][0]} zona {zona} "
                    f"{_giorno(d, oggi)}{' (cambiata)' if cambio else ''}: {', '.join(a['eventi'])}.")
        annunciate[d] = a["colore"]
    if attive:
        return {"annunciate": {d: c for d, c in annunciate.items() if d >= oggi.isoformat()}}
    if prec is not None:
        msgs.append(f"✅ Allerta zona {zona} terminata: oggi e domani nessuna allerta.")
    return None


def _guasto(st: dict, cfg: dict, now: datetime, prec: dict | None, msgs: list[str]) -> dict | None:
    ultimi = [serie_da_stato(v)[-1][0] for k, v in st["serie"].items()
              if k.startswith(("livello_", "pioggia_")) and v]
    ultimo = max(ultimi) if ultimi else None
    fermo = ultimo is None or now - ultimo > timedelta(hours=cfg["notifiche"]["guasto_ore"])
    if fermo and prec is None:
        quando = f"dalle {_ora(ultimo)} del {ultimo.astimezone(ROME):%d/%m}" if ultimo else "da tempo"
        msgs.append(f"🔧 Dati Arpae non aggiornati {quando}: widget e notifiche non sono affidabili.")
        return {"inizio": now.isoformat()}
    if not fermo and prec is not None:
        msgs.append(f"✅ Dati Arpae di nuovo aggiornati (ultimo dato alle {_ora(ultimo)}).")
        return None
    return prec


# --------------------------------------------------------------------------- valutazione complessiva

def valuta(st: dict, cfg: dict, now: datetime) -> tuple[list[str], dict]:
    """(messaggi da inviare, nuovo stato notifiche). Non modifica `st`."""
    prec = (st.get("notifiche") or {}).get("attivi", {})
    msgs: list[str] = []
    attivi = {}
    guasto = _guasto(st, cfg, now, prec.get("guasto"), msgs)
    attivi["guasto"] = guasto
    if guasto is None:            # con i dati fermi non si dichiara finito nessun evento
        attivi["leo_salita"] = _leo(st, cfg, prec.get("leo_salita"), msgs)
        attivi["pioggia"] = _pioggia(st, cfg, now, prec.get("pioggia"), msgs)
    else:
        attivi["leo_salita"], attivi["pioggia"] = prec.get("leo_salita"), prec.get("pioggia")
    attivi["allerta"] = _allerta(st, cfg, now, prec.get("allerta"), msgs)
    return msgs, {"attivi": {k: v for k, v in attivi.items() if v is not None}, "aggiornato": now.isoformat()}


def riepilogo_iniziale(st: dict, cfg: dict, now: datetime) -> tuple[str, dict]:
    """Primo messaggio (bot appena collegato): conferma e situazione, senza ripetere gli eventi in corso."""
    msgs, nuovo = valuta({**st, "notifiche": None}, cfg, now)
    testo = "✅ Notifiche meteo Fanano attive."
    if msgs:
        testo += "\nIn corso adesso:\n" + "\n".join(msgs)
    else:
        testo += " Al momento nessun evento in corso."
    return testo, nuovo


def componi(msgs: list[str], cfg: dict) -> str:
    base = cfg["pubblicazione"]["base_url"].rstrip("/")
    return "\n\n".join(msgs) + f"\n\nGrafici: {base}/index.html"


# --------------------------------------------------------------------------- Telegram

def invia_telegram(testo: str, token: str, chat_id: str, timeout: float = 20) -> None:
    """Un messaggio alla chat. In caso di errore solleva RuntimeError senza mai mostrare il token."""
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          data={"chat_id": chat_id, "text": testo, "disable_web_page_preview": "true"},
                          timeout=timeout)
    except requests.RequestException as exc:
        raise RuntimeError(f"Telegram non raggiungibile ({type(exc).__name__})") from None
    if r.status_code != 200:
        try:
            descr = r.json().get("description", "")
        except ValueError:
            descr = ""
        raise RuntimeError(f"Telegram HTTP {r.status_code} {descr}".strip())


def mittente_da_ambiente():
    """Funzione di invio se TELEGRAM_TOKEN e TELEGRAM_CHAT_ID sono impostati, altrimenti None."""
    token, chat = os.environ.get("TELEGRAM_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        return None
    return lambda testo: invia_telegram(testo, token, chat)


def gestisci(st: dict, cfg: dict, now: datetime, invia, prova: bool = False) -> list[str]:
    """Valuta gli eventi, invia e aggiorna st["notifiche"] solo se l'invio riesce. Ritorna gli errori.

    Senza `invia` (segreti non impostati) non fa nulla: lo stato resta vuoto, cosi' quando il bot viene
    collegato parte il riepilogo iniziale invece di una raffica di eventi gia' in corso.
    """
    if invia is None or not cfg.get("notifiche", {}).get("attive", True):
        return []
    if not st.get("notifiche"):
        testo, nuovo = riepilogo_iniziale(st, cfg, now)
        msgs = [testo]
    else:
        msgs, nuovo = valuta(st, cfg, now)
    if prova:
        msgs = ["🔔 Messaggio di prova dal sistema meteo Fanano: le notifiche funzionano."] + msgs
    if msgs:
        try:
            invia(componi(msgs, cfg))
        except RuntimeError as exc:
            return [f"notifiche: {exc}"]
    st["notifiche"] = nuovo
    return []
