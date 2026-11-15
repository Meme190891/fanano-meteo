"""Fonte di riserva per la pioggia: API REST di arpae.it quando il portale Allerta non ha dati."""

import json
import shutil
from datetime import timedelta

from fanano import arpae, compute, main
from conftest import FIX, NOW


def _rest():
    return json.loads((FIX / "riserva_pioggia_scaffaiolo.json").read_text(encoding="utf-8"))


def test_parse_rest_solo_orari_pieni_in_utc():
    serie = arpae.parse_rest_pioggia(_rest())
    assert serie and all(t.minute == 0 and t.utcoffset() == timedelta(0) for t, _ in serie)
    assert arpae.parse_rest_pioggia({}) == [] and arpae.parse_rest_pioggia({"_items": [{"dati": None}]}) == []


def test_rest_coincide_con_portale_allerta():
    """Stessa stazione, stesse misure: dove ci sono entrambe le fonti i valori sono identici."""
    allerta = dict(arpae.parse_serie(json.loads((FIX / "pioggia_scaffaiolo.json").read_text())))
    rest = dict(arpae.parse_rest_pioggia(_rest()))
    comuni = set(allerta) & set(rest)
    assert len(comuni) > 20
    assert all(allerta[t] == rest[t] for t in comuni)


def test_url_rest(cfg):
    assert arpae.url_rest_pioggia(cfg, "12461") == \
        'https://apps.arpae.it/REST/meteo_osservati/?where={"_id":"12461"}&max_results=1'


def test_riserva_usata_se_portale_vuoto(cfg, tmp_path):
    cartella = tmp_path / "risposte"
    shutil.copytree(FIX, cartella)
    (cartella / "pioggia_scaffaiolo.json").write_text("[]")
    raccolta = main.raccogli_da_cartella(cartella, cfg, NOW)
    assert raccolta["pioggia_scaffaiolo"] == arpae.parse_rest_pioggia(_rest())
    assert isinstance(raccolta["riserva_pioggia_scaffaiolo"], list)
    assert "riserva_pioggia_pratignano" not in raccolta          # Pratignano ha dati: nessuna richiesta in piu'
    stato, errori = compute.aggiorna_stato(None, raccolta, NOW, cfg)
    assert not any("scaffaiolo" in e for e in errori)
    assert stato["serie"]["pioggia_scaffaiolo"]


def test_riserva_riempie_serie_vecchia_senza_sovrascrivere(cfg, tmp_path):
    """Portale fermo da 4 ore: i valori del portale restano, la REST aggiunge le ore mancanti."""
    principale = arpae.parse_serie(json.loads((FIX / "pioggia_scaffaiolo.json").read_text()))
    taglio = principale[-1][0] - timedelta(hours=4)
    vecchia = [p for p in principale if p[0] <= taglio]
    raccolta = {"pioggia_scaffaiolo": vecchia}
    scarica = lambda nome, url: (FIX / f"{nome}.json").read_bytes()
    main.integra_riserva(raccolta, cfg, NOW, scarica)
    unita = dict(raccolta["pioggia_scaffaiolo"])
    assert max(unita) > taglio
    assert all(unita[t] == v for t, v in vecchia)


def test_riserva_fallita_non_rompe_nulla(cfg, tmp_path):
    raccolta = {"pioggia_scaffaiolo": ValueError("serie vuota")}

    def giu(nome, url):
        raise OSError("rete giu'")
    main.integra_riserva(raccolta, cfg, NOW, giu)
    assert isinstance(raccolta["pioggia_scaffaiolo"], ValueError)
    assert isinstance(raccolta["riserva_pioggia_scaffaiolo"], OSError)
    _, errori = compute.aggiorna_stato(None, raccolta, NOW, cfg)
    assert errori == ["pioggia_scaffaiolo: ValueError", "riserva_pioggia_scaffaiolo: OSError"]


def test_riserva_non_chiamata_se_dati_freschi(cfg):
    principale = arpae.parse_serie(json.loads((FIX / "pioggia_scaffaiolo.json").read_text()))
    raccolta = {"pioggia_scaffaiolo": principale}

    def vietata(nome, url):
        raise AssertionError("non doveva scaricare")
    main.integra_riserva(raccolta, cfg, NOW, vietata)
    assert raccolta == {"pioggia_scaffaiolo": principale}
