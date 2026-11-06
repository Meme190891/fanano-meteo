"""Test di grafici PNG e index.html."""

import json
import struct
from datetime import timedelta

from fanano import compute, main, render
from conftest import FIX, NOW


def dimensioni_png(path):
    with open(path, "rb") as fh:
        testa = fh.read(24)
    assert testa[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", testa[16:24])


def test_genera_tutto(stato, cfg, tmp_path):
    w = compute.costruisci_widget(stato, cfg, NOW)
    files = render.genera_tutto(stato, cfg, w, NOW, tmp_path)
    nomi = sorted(f.name for f in files)
    assert nomi == ["index.html", "leo.png", "leo_dark.png", "panaro.png", "panaro_dark.png"]
    for f in files:
        if f.suffix == ".png":
            assert dimensioni_png(f) == (render.W, render.H)
            assert f.stat().st_size > 20_000


def test_index_contenuti(stato, cfg):
    w = compute.costruisci_widget(stato, cfg, NOW)
    pagina = render.pagina_index(stato, cfg, w, NOW)
    assert pagina.startswith("<!doctype html>") and 'lang="it"' in pagina
    for atteso in ("Tutto regolare", "−0.45 m", "0.77 m", "7.6*", "4-5 mm", "Bollettino di vigilanza 178/2026",
                   "Dati Arpae in tempo reale, non validati", "CC BY-NC-SA 4.0", 'media="(prefers-color-scheme: dark)"',
                   "leo_dark.png?v=202611061042", "Ospitale e Fellicarolo"):
        assert atteso in pagina, atteso
    # tabella oraria delle ultime 24h (equivalente testuale dei grafici)
    assert pagina.count("<tr><td>06/11 11:00</td>") == 1


def test_index_escape(stato, cfg):
    w = compute.costruisci_widget(stato, cfg, NOW)
    w["allerta_titolo"] = '<script>alert("x")</script>'
    w["allerta_link"] = 'javascript:"><img src=x>'
    pagina = render.pagina_index(stato, cfg, w, NOW)
    assert "<script>alert" not in pagina and "&lt;script&gt;" in pagina
    assert '"><img src=x>' not in pagina and "javascript:" not in pagina


def test_grafici_senza_dati(cfg, tmp_path):
    st = compute.stato_vuoto()
    w = compute.costruisci_widget(st, cfg, NOW)
    files = render.genera_tutto(st, cfg, w, NOW, tmp_path)
    assert all(f.exists() for f in files)
    assert "Dati non aggiornati" in (tmp_path / "index.html").read_text(encoding="utf-8")


def test_grafico_piena_con_buco(stato, cfg, tmp_path):
    serie = stato["serie"]["livello_leo"]
    for i, p in enumerate(serie[-48:]):
        p[1] = round(-0.45 + 2.0 * (i / 47) ** 2, 2)
    del serie[-30:-22]
    later = NOW + timedelta(hours=3)
    w = compute.costruisci_widget(stato, cfg, later)
    assert w["leo_soglia"] == "soglia 2" and w["leo_vecchio"] is True
    f = render.grafico_torrente(stato, cfg, w, "leo", "scuro", later, tmp_path / "leo_dark.png")
    assert dimensioni_png(f) == (render.W, render.H)


def test_errore_grafici_non_blocca_widget(cfg, tmp_path, monkeypatch):
    def rotto(*a, **k):
        raise RuntimeError("font mancante")
    monkeypatch.setattr(render, "genera_tutto", rotto)
    w = main.esegui(cfg, tmp_path, tmp_path / "state.json", main.raccogli_da_cartella(FIX, cfg, NOW), NOW)
    assert w["errori"] == "grafici: RuntimeError: font mancante"
    assert json.loads((tmp_path / "widget.json").read_text(encoding="utf-8"))["leo_livello"] == "-0.45 m"
