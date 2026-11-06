"""Accesso ai dati del portale Allerta Meteo Emilia-Romagna (Arpae).

Il modulo e' diviso in tre parti:
  * costruzione degli URL (uno per endpoint, vedi README);
  * download con timeout e un solo nuovo tentativo in caso di errore di rete o 5xx;
  * parser puri (nessun accesso alla rete), testati sulle risposte reali in tests/fixtures.

Uso da riga di comando (una richiesta per endpoint):
    python -m fanano.arpae                 # stampa i valori estratti
    python -m fanano.arpae --save DIR      # salva anche le risposte grezze in DIR
"""

from __future__ import annotations

import argparse
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from fanano.config import load_config

ROME = ZoneInfo("Europe/Rome")
UTC = timezone.utc


# --------------------------------------------------------------------------- strutture dati

@dataclass
class Idrometro:
    """Valore puntuale e soglie di un idrometro (endpoint get-sensor-values)."""
    id: str
    nome: str
    lat: float
    lon: float
    valore: float | None
    soglia1: float | None
    soglia2: float | None
    soglia3: float | None


Serie = list[tuple[datetime, float]]  # (istante UTC, valore), ordinata per tempo


@dataclass
class Allerta:
    """Documento di allertamento valido in un istante (servizio documentato get-stato-allerta)."""
    titolo: str
    emissione: datetime | None
    inizio: datetime | None
    fine: datetime | None
    link: str | None
    descrizione: str
    zona: str
    colori: dict[str, str]  # evento -> green/yellow/orange/red (solo eventi applicabili alla zona)


@dataclass
class GiornoPrevisione:
    """Previsione provinciale di un giorno, colonna scelta (rilievi o pianura)."""
    giorno: str                 # nome del giorno come appare sulla pagina, es. "venerdì"
    data: date | None           # data ricostruita dal nome del giorno
    testo: str                  # descrizione completa (tutti i paragrafi)
    sintesi: str                # primo paragrafo (stato del tempo)
    prec_min: float | None      # mm, minimo previsto nell'area
    prec_max: float | None      # mm, massimo previsto nell'area
    prec_testo: str             # cella originale, es. "4/5"
    tmin: float | None = None
    tmax: float | None = None
    vento_max: float | None = None
    altre_colonne: dict[str, str] = field(default_factory=dict)  # celle Prec delle altre zone


# --------------------------------------------------------------------------- URL

def _base(cfg: dict) -> str:
    return cfg["arpae"]["base_url"].rstrip("/")


def slot_ms(now: datetime | None = None) -> int:
    """Istante (ms) dello slot di 30' precedente quello corrente: il piu' recente sicuramente popolato."""
    ts = int((now or datetime.now(UTC)).timestamp())
    return ((ts // 1800) * 1800 - 1800) * 1000


def url_livelli(cfg: dict, now: datetime | None = None) -> str:
    return (f"{_base(cfg)}/o/api/allerta/get-sensor-values"
            f"?variabile={cfg['variabili']['livello']}&time={slot_ms(now)}")


def url_serie(cfg: dict, stazione: str, variabile: str) -> str:
    return f"{_base(cfg)}/o/api/allerta/get-time-series/?stazione={stazione}&variabile={variabile}"


def url_allerta(cfg: dict, quando: datetime | None = None) -> str:
    """Servizio documentato in /sviluppatori. Senza data = documento valido adesso."""
    url = f"{_base(cfg)}/o/get-stato-allerta"
    if quando is not None:
        url += "?data=" + quando.astimezone(ROME).strftime("%Y-%m-%d") + "%20" + quando.astimezone(ROME).strftime("%H:%M")
    return url


def url_previsione(cfg: dict) -> str:
    prov = cfg["previsione"]["provincia"]
    return (f"{_base(cfg)}/previsioni-regionali?p_p_id=AllertaPrevisioniTerritorioPortlet&p_p_lifecycle=0"
            f"&p_p_state=normal&p_p_mode=view&_AllertaPrevisioniTerritorioPortlet_prov={prov}")


def endpoint_urls(cfg: dict, now: datetime | None = None) -> dict[str, str]:
    """Tutti gli URL di produzione, una chiave per endpoint (ognuno chiamato una volta per esecuzione)."""
    now = now or datetime.now(UTC)
    domani_mezzogiorno = datetime.combine(now.astimezone(ROME).date() + timedelta(days=1),
                                          datetime.min.time().replace(hour=12), tzinfo=ROME)
    urls = {"livelli": url_livelli(cfg, now)}
    for t in cfg["torrenti"]:
        urls[f"livello_{t['chiave']}"] = url_serie(cfg, t["id"], cfg["variabili"]["livello"])
    for p in cfg["pluviometri"]:
        urls[f"pioggia_{p['chiave']}"] = url_serie(cfg, p["id"], cfg["variabili"]["pioggia_oraria"])
    urls["allerta_oggi"] = url_allerta(cfg)
    urls["allerta_domani"] = url_allerta(cfg, domani_mezzogiorno)
    urls["previsione"] = url_previsione(cfg)
    return urls


# --------------------------------------------------------------------------- download

def make_session(cfg: dict) -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = cfg["arpae"]["user_agent"]
    return s


def fetch(session: requests.Session, url: str, timeout: float = 20, retry_wait: float = 3) -> requests.Response:
    """GET con al massimo un nuovo tentativo, solo per errori di rete, timeout o HTTP 5xx."""
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code >= 500 and attempt == 0:
                last_exc = requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
                time.sleep(retry_wait)
                continue
            resp.raise_for_status()
            return resp
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            if attempt == 0:
                time.sleep(retry_wait)
    assert last_exc is not None
    raise last_exc


# --------------------------------------------------------------------------- parser

def _soglia(v) -> float | None:
    """Arpae usa 0 (o null) per 'soglia non definita'."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def parse_livelli(data: list, ids: set[str] | None = None) -> dict[str, Idrometro]:
    """Risposta di get-sensor-values (livello idrometrico) -> {id: Idrometro}."""
    out: dict[str, Idrometro] = {}
    for s in data:
        if not isinstance(s, dict) or "idstazione" not in s:
            continue  # il primo elemento puo' essere {"time": ...}
        sid = str(s["idstazione"])
        if ids is not None and sid not in ids:
            continue
        val = s.get("value")
        out[sid] = Idrometro(
            id=sid,
            nome=str(s.get("nomestaz", "")),
            lat=int(s["lat"]) / 1e5,
            lon=int(s["lon"]) / 1e5,
            valore=float(val) if val is not None else None,
            soglia1=_soglia(s.get("soglia1")),
            soglia2=_soglia(s.get("soglia2")),
            soglia3=_soglia(s.get("soglia3")),
        )
    return out


def parse_serie(data: list) -> Serie:
    """Risposta di get-time-series -> lista ordinata (istante UTC, valore), senza valori nulli o duplicati."""
    punti: dict[datetime, float] = {}
    for p in data or []:
        if not isinstance(p, dict) or p.get("v") is None or p.get("t") is None:
            continue
        t = datetime.fromtimestamp(int(p["t"]) / 1000, tz=UTC)
        punti[t] = float(p["v"])
    return sorted(punti.items())


_MESI = {
    # inglese (formato attuale del servizio) e italiano (esempio nella guida sviluppatori)
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "gen": 1, "mag": 5, "giu": 6, "lug": 7, "ago": 8, "set": 9, "ott": 10, "dic": 12,
}
_DATA_RE = re.compile(r"([A-Za-z]{3})\w*\.?\s+(\d{1,2}),\s*(\d{4}),?\s+(\d{1,2}):(\d{2}):(\d{2})\s*([AaPp][Mm])")


def parse_data_allerta(s: str | None) -> datetime | None:
    """'Nov 5, 2026 11:38:18 AM' o 'gen 8, 2022 11:46:05 AM' -> datetime Europe/Rome."""
    if not s:
        return None
    m = _DATA_RE.search(s)
    if not m:
        return None
    mese = _MESI.get(m.group(1).lower())
    if mese is None:
        return None
    ora = int(m.group(4)) % 12 + (12 if m.group(7).lower() == "pm" else 0)
    return datetime(int(m.group(3)), mese, int(m.group(2)), ora, int(m.group(5)), int(m.group(6)), tzinfo=ROME)


def parse_allerta(data, zona: str, base_url: str = "") -> Allerta | None:
    """Risposta di get-stato-allerta -> Allerta per la zona, o None se nessun documento."""
    if not data or not isinstance(data, dict) or not data.get("titolo"):
        return None
    zona_dati = data.get(zona) or {}
    colori = {k: v for k, v in zona_dati.items() if k != "nome" and isinstance(v, str) and v}
    link = data.get("link")
    if link and link.startswith("/"):
        link = base_url.rstrip("/") + link
    return Allerta(
        titolo=str(data["titolo"]).strip(),
        emissione=parse_data_allerta(data.get("dataEmissione")),
        inizio=parse_data_allerta(data.get("dataInizio")),
        fine=parse_data_allerta(data.get("dataFine")),
        link=link,
        descrizione=str(data.get("descrizionemeteo") or "").strip(),
        zona=zona,
        colori=colori,
    )


_GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]


def _num(s: str) -> float | None:
    m = re.search(r"-?\d+(?:[.,]\d+)?", s or "")
    return float(m.group(0).replace(",", ".")) if m else None


def parse_prec(cella: str) -> tuple[float | None, float | None]:
    """'4/5' -> (4, 5); '0' -> (0, 0); '10/15' -> (10, 15); testo senza numeri -> (None, None)."""
    nums = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", cella or "")]
    if not nums:
        return None, None
    return min(nums), max(nums)


def _data_da_giorno(nome: str, oggi: date) -> date | None:
    """Data piu' vicina a 'oggi' (da -3 a +3 giorni) con quel nome di giorno della settimana."""
    nome = nome.strip().lower()
    if nome not in _GIORNI:
        return None
    for delta in (0, -1, 1, -2, 2, -3, 3):
        d = oggi + timedelta(days=delta)
        if _GIORNI[d.weekday()] == nome:
            return d
    return None


def parse_previsione(html: str, zona: str = "rilievi", oggi: date | None = None) -> list[GiornoPrevisione]:
    """Pagina 'Previsioni regionali' per provincia -> un GiornoPrevisione per tab (oggi, domani, dopodomani)."""
    oggi = oggi or datetime.now(ROME).date()
    soup = BeautifulSoup(html, "html.parser")
    giorni: list[GiornoPrevisione] = []
    tabs = soup.select('a.nav-link[href^="#previsioni-tab-"]')
    nomi = {a["href"][1:]: a.get_text(strip=True) for a in tabs if "__" not in a["href"]}
    prima_data: date | None = None
    for i, (pane_id, nome) in enumerate(nomi.items()):
        pane = soup.find(id=pane_id)
        if pane is None:
            continue
        tabella = pane.select_one(".table--previsioni table")
        if tabella is None:
            continue
        contenitore = tabella.find_parent(class_="col-md-6") or pane
        paragrafi = [p.get_text(" ", strip=True) for p in contenitore.find_all("p")
                     if not p.find_parent(class_="table--previsioni")]
        paragrafi = [re.sub(r"\s+", " ", re.sub(r"\s+([;,.])", r"\1", p)) for p in paragrafi if p]

        intestazioni = [th.get_text(strip=True).lower() for th in tabella.select("thead th")]
        try:
            col = intestazioni.index(zona) - 1  # la prima colonna e' l'etichetta della riga
        except ValueError:
            raise ValueError(f"colonna '{zona}' non trovata nella tabella previsioni: {intestazioni}")
        colonne_zona = [h for h in intestazioni[1:] if h and h not in ("unità di misura",)]

        righe: dict[str, list[str]] = {}
        for tr in tabella.select("tbody tr"):
            etichetta = tr.find(["abbr", "acronym"])
            chiave = re.sub(r"\s+", " ", etichetta.get_text(" ", strip=True)).lower() if etichetta else ""
            celle = []
            for td in tr.find_all("td"):
                for span in td.find_all("span"):  # (media climatologica) tra parentesi
                    span.extract()
                celle.append(td.get_text(" ", strip=True))
            righe[chiave] = celle

        prec = righe.get("prec", [])
        prec_cella = prec[col] if len(prec) > col else ""
        pmin, pmax = parse_prec(prec_cella)
        altre = {z: prec[j] for j, z in enumerate(colonne_zona) if z != zona and j < len(prec)}

        def val(chiave: str) -> float | None:
            c = righe.get(chiave, [])
            return _num(c[col]) if len(c) > col else None

        d = _data_da_giorno(nome, oggi) if i == 0 else (prima_data + timedelta(days=i) if prima_data else None)
        if i == 0:
            prima_data = d
        giorni.append(GiornoPrevisione(
            giorno=nome, data=d, testo=" ".join(paragrafi), sintesi=paragrafi[0] if paragrafi else "",
            prec_min=pmin, prec_max=pmax, prec_testo=prec_cella,
            tmin=val("t min"), tmax=val("t max"), vento_max=val("v max"), altre_colonne=altre,
        ))
    if not giorni:
        raise ValueError("nessuna previsione trovata nella pagina (struttura HTML cambiata?)")
    return giorni


# --------------------------------------------------------------------------- CLI di verifica

def _fmt(t: datetime) -> str:
    return t.astimezone(ROME).strftime("%d/%m %H:%M")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Scarica e mostra i dati Arpae per Fanano (una richiesta per endpoint).")
    ap.add_argument("--save", type=Path, help="cartella dove salvare le risposte grezze")
    args = ap.parse_args(argv)
    cfg = load_config()
    session = make_session(cfg)
    timeout = cfg["arpae"].get("timeout_s", 20)
    base = _base(cfg)
    if args.save:
        args.save.mkdir(parents=True, exist_ok=True)

    for nome, url in endpoint_urls(cfg).items():
        resp = fetch(session, url, timeout=timeout)
        if args.save:
            ext = "html" if nome == "previsione" else "json"
            (args.save / f"{nome}.{ext}").write_bytes(resp.content)
        print(f"\n== {nome}  ({len(resp.content)} B)")
        if nome == "livelli":
            ids = {t["id"] for t in cfg["torrenti"]}
            for s in parse_livelli(resp.json(), ids).values():
                print(f"  {s.id} {s.nome}: {s.valore} m  soglie {s.soglia1}/{s.soglia2}/{s.soglia3}  ({s.lat}, {s.lon})")
        elif nome.startswith(("livello_", "pioggia_")):
            serie = parse_serie(resp.json())
            ult = serie[-6:]
            print(f"  {len(serie)} punti, {_fmt(serie[0][0])} -> {_fmt(serie[-1][0])}")
            print("  ultimi: " + ", ".join(f"{_fmt(t)[6:]}={v}" for t, v in ult))
        elif nome.startswith("allerta_"):
            a = parse_allerta(resp.json(), cfg["zona_allerta"], base)
            if a is None:
                print("  nessun documento emesso")
            else:
                print(f"  {a.titolo}\n  emesso {a.emissione}, valido {a.inizio} -> {a.fine}")
                print(f"  {a.zona}: {a.colori}\n  {a.descrizione[:160]}")
        elif nome == "previsione":
            for g in parse_previsione(resp.text, cfg["previsione"]["zona"]):
                print(f"  {g.giorno} {g.data}: Prec {cfg['previsione']['zona']} {g.prec_testo!r} -> "
                      f"{g.prec_min}-{g.prec_max} mm (altre: {g.altre_colonne}); Tmin {g.tmin} Tmax {g.tmax} "
                      f"Vmax {g.vento_max}\n    sintesi: {g.sintesi}")
    if args.save:
        print(f"\nRisposte salvate in {args.save}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
