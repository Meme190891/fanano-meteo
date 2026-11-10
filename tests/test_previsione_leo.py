"""Test della stima indicativa del livello del Leo (oggi / domani / dopodomani)."""

import copy
from datetime import timedelta

import pytest

from fanano import compute
from fanano.config import load_config
from conftest import NOW

PREV = load_config()["previsione_leo"]


@pytest.fixture
def cfgp(cfg):
    c = copy.deepcopy(cfg)
    c["previsione_leo"] = dict(PREV)
    return c


def prev_pioggia(stato, valori):
    oggi = NOW.astimezone(compute.ROME).date()
    stato["previsione"]["giorni"] = [{"data": (oggi + timedelta(days=i)).isoformat(), "prec_min": a, "prec_max": b}
                                     for i, (a, b) in enumerate(valori)]


def test_senza_pioggia_il_livello_scende_verso_la_base(stato, cfgp):
    prev_pioggia(stato, [(0, 0), (0, 0), (0, 0)])
    for p in stato["serie"]["pioggia_pratignano"]:
        p[1] = 0.0
    lp = compute.previsione_leo(stato, cfgp, NOW)
    l_now = stato["serie"]["livello_leo"][-1][1]
    assert lp[0]["basso"] == lp[0]["alto"] == round(l_now, 2)
    assert lp[2]["alto"] <= lp[1]["alto"] <= lp[0]["alto"]


def test_pioggia_appena_caduta_alza_oggi(stato, cfgp):
    prev_pioggia(stato, [(0, 0), (0, 0), (0, 0)])
    base = compute.previsione_leo(stato, cfgp, NOW)[0]["alto"]
    for p in stato["serie"]["pioggia_pratignano"][-6:]:
        p[1] = 5.0                                           # 30 mm nelle ultime 6 ore
    lp = compute.previsione_leo(stato, cfgp, NOW)
    assert lp[0]["alto"] > base + 0.1
    assert lp[0]["pioggia_osservata_mm"] >= 30


def test_pioggia_prevista_domani(stato, cfgp):
    prev_pioggia(stato, [(0, 0), (40, 60), (0, 0)])
    lp = compute.previsione_leo(stato, cfgp, NOW)
    assert lp[1]["alto"] - lp[1]["basso"] > 0.1           # forbice min-max della previsione
    assert lp[1]["alto"] > lp[0]["alto"] + 0.2
    assert lp[2]["alto"] < lp[1]["alto"]                  # dopodomani torna a scendere


def test_widget_e_dati_mancanti(stato, cfgp, cfg):
    w = compute.costruisci_widget(stato, cfgp, NOW)
    assert w["leo_prev_oggi"].endswith(" m") and w["leo_prev_domani"] != "n.d."
    stato["serie"]["livello_leo"] = []
    assert compute.previsione_leo(stato, cfgp, NOW) is None
    assert compute.costruisci_widget(stato, cfgp, NOW)["leo_prev_oggi"] == "n.d."
    assert compute.previsione_leo(stato, cfg, NOW) is None   # configurazione senza sezione previsione_leo


def test_fmt_range_m():
    assert compute.fmt_range_m(-0.16, -0.09) == "-0.16/-0.09 m"
    assert compute.fmt_range_m(-0.45, -0.45) == "-0.45 m"
