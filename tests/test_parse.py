"""Test dei parser sulle risposte Arpae reali salvate in tests/fixtures (06/11/2026 ~11:40 ora italiana).

Per aggiornare le fixture: python -m fanano.arpae --save tests/fixtures
(poi aggiornare i valori attesi qui sotto).
"""

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from fanano import arpae
from fanano.config import load_config

FIX = Path(__file__).parent / "fixtures"
ROME = arpae.ROME


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ livelli + soglie

def test_parse_livelli_stazioni_configurate():
    out = arpae.parse_livelli(load("livelli.json"), {"5503", "5434"})
    assert set(out) == {"5503", "5434"}
    leo = out["5503"]
    assert leo.nome == "Fanano"
    assert leo.valore == -0.45
    assert (leo.soglia1, leo.soglia2, leo.soglia3) == (1.0, 1.3, 2.0)
    assert (leo.lat, leo.lon) == (44.20386, 10.79909)
    panaro = out["5434"]
    assert panaro.nome == "Ponte Val di Sasso"
    assert (panaro.soglia1, panaro.soglia2, panaro.soglia3) == (2.0, 2.8, 4.0)


def test_parse_livelli_tutte_le_stazioni_e_casi_limite():
    out = arpae.parse_livelli(load("livelli.json"))
    assert len(out) == 268
    assert out["14029"].valore is None            # Ongina Po: dato mancante
    s = out["3053"]                                # Matellica: soglia1 = 0 -> non definita
    assert s.soglia1 is None and s.soglia2 == 3.5 and s.soglia3 == 5.5


def test_parse_livelli_ignora_elemento_time():
    # la variante "no-time" dell'endpoint inizia con {"time": ...}
    data = [{"time": "-3600000"}, {"idstazione": "5503", "nomestaz": "Fanano", "lat": "4420386",
                                   "lon": "1079909", "value": None, "soglia1": 1, "soglia2": 1.3, "soglia3": 2}]
    out = arpae.parse_livelli(data)
    assert list(out) == ["5503"] and out["5503"].valore is None


# ------------------------------------------------------------------ serie temporali

def test_parse_serie_livello_leo():
    serie = arpae.parse_serie(load("livello_leo.json"))
    assert len(serie) == 241
    assert serie[0][0] == datetime(2026, 11, 3, 22, 0, tzinfo=timezone.utc)
    assert serie[-1] == (datetime(2026, 11, 6, 10, 0, tzinfo=timezone.utc), -0.45)
    passi = {b[0] - a[0] for a, b in zip(serie, serie[1:])}
    assert passi == {timedelta(minutes=15)}


def test_parse_serie_pioggia_oraria():
    prat = arpae.parse_serie(load("pioggia_pratignano.json"))
    scaf = arpae.parse_serie(load("pioggia_scaffaiolo.json"))
    assert len(prat) == len(scaf) == 61
    assert [v for _, v in prat[-3:]] == [1.0, 1.8, 0.2]
    assert [v for _, v in scaf[-3:]] == [1.4, 1.6, 0.6]
    assert {b[0] - a[0] for a, b in zip(prat, prat[1:])} == {timedelta(hours=1)}


def test_parse_serie_scarta_nulli_duplicati_e_ordina():
    data = [{"t": 3600000, "v": 2.0}, {"t": 0, "v": 1.0}, {"t": 7200000, "v": None},
            {"t": 3600000, "v": 2.5}, {"v": 9}, "spazzatura"]
    serie = arpae.parse_serie(data)
    assert serie == [(datetime(1970, 1, 1, 0, tzinfo=timezone.utc), 1.0),
                     (datetime(1970, 1, 1, 1, tzinfo=timezone.utc), 2.5)]
    assert arpae.parse_serie([]) == [] and arpae.parse_serie(None) == []


# ------------------------------------------------------------------ allerta

def test_parse_allerta_oggi():
    a = arpae.parse_allerta(load("allerta_oggi.json"), "E1", "https://allertameteo.regione.emilia-romagna.it")
    assert a.titolo.startswith("Bollettino di vigilanza 178/2026")
    assert a.emissione == datetime(2026, 11, 5, 11, 38, 18, tzinfo=ROME)
    assert a.inizio == datetime(2026, 11, 6, 0, 0, tzinfo=ROME)
    assert a.fine == datetime(2026, 11, 7, 0, 0, tzinfo=ROME)
    assert a.link == "https://allertameteo.regione.emilia-romagna.it/documents/20181/4928835/bollettino178_2026.pdf"
    assert a.colori["idraulica"] == "green" and a.colori["temporali"] == "green"
    assert "mareggiate" not in a.colori        # null = non applicabile alla zona
    assert "fenomeni significativi" in a.descrizione


def test_parse_allerta_domani_e_non_emessa():
    a = arpae.parse_allerta(load("allerta_domani.json"), "E1")
    assert a.titolo.startswith("Bollettino di vigilanza 179/2026")
    assert a.inizio == datetime(2026, 11, 7, 0, 0, tzinfo=ROME)
    assert arpae.parse_allerta(load("allerta_non_emessa.json"), "E1") is None   # risposta reale: {}
    assert arpae.parse_allerta([], "E1") is None


@pytest.mark.parametrize("s, atteso", [
    ("Nov 5, 2026 11:38:18 AM", datetime(2026, 11, 5, 11, 38, 18, tzinfo=ROME)),
    ("Nov 6, 2026 12:00:00 AM", datetime(2026, 11, 6, 0, 0, 0, tzinfo=ROME)),
    ("Nov 6, 2026 12:30:00 PM", datetime(2026, 11, 6, 12, 30, 0, tzinfo=ROME)),
    ("gen 8, 2022 11:46:05 AM", datetime(2022, 1, 8, 11, 46, 5, tzinfo=ROME)),   # esempio guida sviluppatori
    ("dic 31, 2025 11:59:59 PM", datetime(2025, 12, 31, 23, 59, 59, tzinfo=ROME)),
    ("", None), (None, None), ("data strana", None),
])
def test_parse_data_allerta(s, atteso):
    assert arpae.parse_data_allerta(s) == atteso


# ------------------------------------------------------------------ previsione provinciale

def test_parse_previsione_modena_rilievi():
    html = (FIX / "previsione.html").read_text(encoding="utf-8")
    giorni = arpae.parse_previsione(html, "rilievi", oggi=date(2026, 11, 6))
    assert [g.giorno for g in giorni] == ["venerdì", "sabato", "domenica"]
    assert [g.data for g in giorni] == [date(2026, 11, 6), date(2026, 11, 7), date(2026, 11, 8)]
    assert [(g.prec_min, g.prec_max) for g in giorni] == [(4, 5), (0, 0), (0, 0)]
    assert [g.prec_testo for g in giorni] == ["4/5", "0", "0"]
    assert giorni[1].altre_colonne == {"pianura": "10/15"}
    assert (giorni[0].tmin, giorni[0].tmax, giorni[0].vento_max) == (7, 9, 16)
    assert giorni[0].sintesi.startswith("Al mattino molto nuvoloso con piogge deboli intermittenti;")
    assert "pioviggini;" in giorni[0].sintesi          # spazio prima del ';' rimosso
    assert "Temperature massime" in giorni[0].testo and "Temperature massime" not in giorni[0].sintesi


def test_parse_previsione_colonna_pianura():
    html = (FIX / "previsione.html").read_text(encoding="utf-8")
    giorni = arpae.parse_previsione(html, "pianura", oggi=date(2026, 11, 6))
    assert [(g.prec_min, g.prec_max) for g in giorni] == [(4, 5), (10, 15), (0, 0)]
    assert giorni[0].tmax == 11


def test_parse_previsione_data_se_pagina_di_ieri():
    # se la pagina non e' ancora aggiornata il primo giorno e' ieri: la data lo deve dire
    html = (FIX / "previsione.html").read_text(encoding="utf-8")
    giorni = arpae.parse_previsione(html, "rilievi", oggi=date(2026, 11, 7))
    assert giorni[0].data == date(2026, 11, 6)


def test_parse_previsione_html_inatteso():
    with pytest.raises(ValueError):
        arpae.parse_previsione("<html><body>manutenzione</body></html>")


@pytest.mark.parametrize("cella, atteso", [
    ("4/5", (4, 5)), ("0", (0, 0)), ("10/15", (10, 15)), ("1,5/3", (1.5, 3)), ("", (None, None)), ("n.d.", (None, None)),
])
def test_parse_prec(cella, atteso):
    assert arpae.parse_prec(cella) == atteso


# ------------------------------------------------------------------ URL

def test_endpoint_urls():
    cfg = load_config()
    now = datetime(2026, 11, 6, 10, 41, tzinfo=timezone.utc)
    urls = arpae.endpoint_urls(cfg, now)
    assert len(urls) == 8                                  # 1 livelli + 2 + 2 serie + 2 allerta + 1 previsione
    # 10:41Z -> slot corrente 10:30Z -> slot precedente 10:00Z
    assert urls["livelli"].endswith("variabile=254,0,0/1,-,-,-/B13215&time=1793959200000")
    assert "stazione=5503&variabile=254,0,0/1,-,-,-/B13215" in urls["livello_leo"]
    assert "stazione=12461&variabile=1,0,3600/1,-,-,-/B13011" in urls["pioggia_scaffaiolo"]
    assert urls["allerta_oggi"].endswith("/o/get-stato-allerta")
    assert urls["allerta_domani"].endswith("/o/get-stato-allerta?data=2026-11-07%2012:00")
    assert urls["previsione"].endswith("_AllertaPrevisioniTerritorioPortlet_prov=MO")
