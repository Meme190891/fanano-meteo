"""Comportamento quando Arpae non risponde: JSON sempre valido, ultimo dato valido, flag 'vecchio'."""

import json
from datetime import timedelta

import requests

from fanano import arpae, compute, main
from conftest import FIX, NOW


def tutte_fallite(cfg, msg="timeout"):
    return {nome: requests.ConnectionError(msg) for nome in arpae.endpoint_urls(cfg, NOW)}


def test_fonti_tutte_fallite_mantiene_ultimo_dato(stato, cfg):
    dopo = NOW + timedelta(minutes=30)
    st2, errori = compute.aggiorna_stato(stato, tutte_fallite(cfg), dopo, cfg)
    assert len(errori) == 8 and errori[0] == "livelli: ConnectionError"
    assert st2["serie"] == stato["serie"] and st2["previsione"] == stato["previsione"]
    assert st2["fonti"]["livelli"]["ultimo_ok"] == NOW.isoformat()
    assert st2["fonti"]["livelli"]["errore"] == "ConnectionError: timeout"
    w = compute.costruisci_widget(st2, cfg, dopo, errori)
    json.dumps(w)
    assert w["leo_livello"] == "-0.45 m" and w["pratignano_24h"] == "3.6" and w["prev_oggi"] == "4-5 mm"
    assert w["leo_vecchio"] is False                       # dato delle 10:00Z, ancora entro 2h
    assert w["errori"].startswith("livelli: ConnectionError; livello_leo: ConnectionError")
    # tre ore dopo, sempre senza risposte: stessi valori ma segnalati come vecchi
    later = NOW + timedelta(hours=3)
    st3, _ = compute.aggiorna_stato(st2, tutte_fallite(cfg), later, cfg)
    w3 = compute.costruisci_widget(st3, cfg, later)
    assert w3["leo_livello"] == "-0.45 m" and w3["leo_vecchio"] is True and w3["dato_vecchio"] is True


def test_una_sola_fonte_fallita(stato, cfg):
    raccolta = main.raccogli_da_cartella(FIX, cfg, NOW)
    raccolta["previsione"] = ValueError("tabelle di previsione non trovate")
    st2, errori = compute.aggiorna_stato(stato, raccolta, NOW + timedelta(minutes=30), cfg)
    assert errori == ["previsione: ValueError"]
    w = compute.costruisci_widget(st2, cfg, NOW + timedelta(minutes=30), errori)
    assert w["prev_oggi"] == "4-5 mm" and w["prev_vecchio"] is False
    assert w["errori"] == "previsione: ValueError"


def test_primo_avvio_senza_dati(cfg):
    st, errori = compute.aggiorna_stato(None, tutte_fallite(cfg), NOW, cfg)
    w = compute.costruisci_widget(st, cfg, NOW, errori)
    json.dumps(w)
    assert w["leo_livello"] == "n.d." and w["leo_tendenza"] == "n.d." and w["leo_colore"] == "#9E9E9E"
    assert w["pratignano_24h"] == "n.d." and w["prev_24h"] == "n.d." and w["allerta_oggi"] == "n.d."
    assert (w["stato"], w["stato_livello"]) == ("Dati non aggiornati", -1)
    assert w["disclaimer"] == "Dati Arpae in tempo reale, non validati"


def test_storico_completa_le_72h(stato, cfg):
    # 11 ore piu' vecchie della finestra Arpae, come se arrivassero da esecuzioni precedenti
    inizio_fix = compute.serie_da_stato(stato["serie"]["pioggia_pratignano"])[0][0]
    vecchie = [(inizio_fix - timedelta(hours=h), 0.5) for h in range(1, 12)]
    precedente = compute.stato_vuoto()
    precedente["serie"]["pioggia_pratignano"] = compute.serie_a_stato(vecchie)
    raccolta = main.raccogli_da_cartella(FIX, cfg, NOW)
    st, _ = compute.aggiorna_stato(precedente, raccolta, NOW, cfg)
    assert len(st["serie"]["pioggia_pratignano"]) == 72
    w = compute.costruisci_widget(st, cfg, NOW)
    assert w["pratignano_72h"] == "13.1" and w["pratignano_72h_parziale"] is False   # 7.6 + 11 x 0.5
    assert w["scaffaiolo_72h_parziale"] is True


def test_storico_potato_oltre_96h(stato, cfg):
    molto_dopo = NOW + timedelta(hours=90)
    st, _ = compute.aggiorna_stato(stato, {}, molto_dopo, cfg)
    serie = compute.serie_da_stato(st["serie"]["livello_leo"])
    assert serie and serie[0][0] >= molto_dopo - timedelta(hours=96)


def test_rete_giu_end_to_end(tmp_path, cfg, monkeypatch):
    """Due esecuzioni complete: la prima con dati, la seconda con Arpae irraggiungibile."""
    main.esegui(cfg, tmp_path, tmp_path / "state.json", main.raccogli_da_cartella(FIX, cfg, NOW), NOW)

    def giu(*a, **k):
        raise requests.ConnectionError("Connection reset by peer")
    monkeypatch.setattr(arpae, "fetch", giu)
    dopo = NOW + timedelta(minutes=30)
    raccolta = main.raccogli_online(cfg, dopo)
    assert all(isinstance(v, requests.ConnectionError) for v in raccolta.values())
    w = main.esegui(cfg, tmp_path, tmp_path / "state.json", raccolta, dopo)
    letto = json.loads((tmp_path / "widget.json").read_text(encoding="utf-8"))
    assert letto == w
    assert letto["leo_livello"] == "-0.45 m" and letto["errori"] and letto["stato"] == "Tutto regolare"
    assert json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))["fonti"]["livelli"]["errore"]


def test_stato_corrotto_o_assente(tmp_path, cfg):
    p = tmp_path / "state.json"
    p.write_text("{non json", encoding="utf-8")
    assert main.leggi_stato(p) is None
    assert main.leggi_stato(tmp_path / "manca.json") is None
    w = main.esegui(cfg, tmp_path, p, main.raccogli_da_cartella(FIX, cfg, NOW), NOW)
    assert w["leo_livello"] == "-0.45 m"


def test_parsing_fallito_diventa_errore_di_fonte(tmp_path, cfg):
    cartella = tmp_path / "risposte"
    cartella.mkdir()
    for f in FIX.iterdir():
        (cartella / f.name).write_bytes(f.read_bytes())
    (cartella / "livello_leo.json").write_text("<html>errore</html>", encoding="utf-8")
    (cartella / "previsione.html").write_text("<html>manutenzione</html>", encoding="utf-8")
    raccolta = main.raccogli_da_cartella(cartella, cfg, NOW)
    assert isinstance(raccolta["livello_leo"], ValueError) and isinstance(raccolta["previsione"], ValueError)
    st, errori = compute.aggiorna_stato(None, raccolta, NOW, cfg)
    assert sorted(errori) == ["livello_leo: JSONDecodeError", "previsione: ValueError"]
    w = compute.costruisci_widget(st, cfg, NOW, errori)
    assert w["leo_livello"] == "-0.45 m"                  # ripiega sul valore di get-sensor-values
    assert w["leo_tendenza"] == "n.d."
