"""Test di widget.png, del preset Fanano_meteo.kwgt e della pagina kwgt.html."""

import io
import json
import zipfile

from PIL import Image

from fanano import compute, kwgt, render, widget_img
from conftest import NOW


def test_widget_png_chiaro_e_scuro(stato, cfg, tmp_path):
    w = compute.costruisci_widget(stato, cfg, NOW)
    files = widget_img.genera(w, cfg, tmp_path)
    assert [f.name for f in files] == ["widget.png", "widget_dark.png"]
    for f in files:
        im = Image.open(f)
        assert im.size == (1200, 600) and im.mode == "RGBA"
        assert im.getpixel((0, 0))[3] == 0          # angolo trasparente (riquadro arrotondato)
        assert im.getpixel((600, 300))[3] > 200     # centro opaco


def test_widget_png_testi_lunghi_e_dati_vecchi(stato, cfg, tmp_path):
    w = compute.costruisci_widget(stato, cfg, NOW)
    w.update(stato="Attenzione: Pioggia abbondante prevista domani (20-35 mm)", dato_vecchio=True,
             riga_aggiornamento="Agg. 12:10 · DATI VECCHI · Arpae, non validati")
    f = widget_img.disegna(w, cfg, "scuro", tmp_path / "w.png")
    assert Image.open(f).size == (1200, 600)


def test_preset_struttura(cfg, tmp_path):
    png = tmp_path / "widget.png"
    Image.new("RGBA", (1200, 600), (20, 20, 20, 255)).save(png)
    dati = kwgt.costruisci(cfg, png)
    z = zipfile.ZipFile(io.BytesIO(dati))
    assert z.namelist() == ["preset.json", "preset_thumb_portrait.jpg", "preset_thumb_landscape.jpg"]
    assert Image.open(io.BytesIO(z.read("preset_thumb_portrait.jpg"))).format == "WEBP"
    preset = json.loads(z.read("preset.json"))
    assert list(preset) == ["preset_info", "preset_root"]          # preset_info deve essere la prima chiave
    assert preset["preset_info"]["version"] == 13
    root = preset["preset_root"]
    assert root["internal_type"] == "RootLayerModule"
    (img,) = root["viewgroup_items"]
    assert img["internal_type"] == "BitmapModule"
    assert img["internal_toggles"] == {"bitmap_bitmap": 10, "bitmap_width": 10}
    formula = img["internal_formulas"]["bitmap_bitmap"]
    assert formula.startswith('$"https://meme190891.github.io/fanano-meteo/widget"') and formula.endswith("$")
    assert 'if(si(darkmode) = 1, "_dark", "")' in formula and "mu(floor, (df(S) - 900) / 1800)" in formula
    for ev in (root["internal_events"][0], img["internal_events"][0]):
        assert ev["action"] == "LAUNCH_ACTIVITY" and ev["type"] == "SINGLE_TAP"
        assert ev["intent"].startswith("intent://meme190891.github.io/fanano-meteo/index.html#Intent;scheme=https;")
        assert "action=android.intent.action.VIEW" in ev["intent"] and ev["intent"].endswith(";end")


def test_genera_tutto_include_widget_e_preset(stato, cfg, tmp_path):
    w = compute.costruisci_widget(stato, cfg, NOW)
    nomi = {f.name for f in render.genera_tutto(stato, cfg, w, NOW, tmp_path)}
    assert {"widget.png", "widget_dark.png", "Fanano_meteo.kwgt", "kwgt.html", "index.html"} <= nomi
    pagina = (tmp_path / "kwgt.html").read_text(encoding="utf-8")
    assert 'href="Fanano_meteo.kwgt" download' in pagina
    assert "&quot;https://meme190891.github.io/fanano-meteo/widget&quot;" in pagina    # formula escapata
    assert "$mu(min, si(rwidth), si(rheight) * 2)$" in pagina
    assert 'href="kwgt.html"' in (tmp_path / "index.html").read_text(encoding="utf-8")


def test_widget_png_con_grafici_pioggia(stato, cfg, tmp_path):
    w = compute.costruisci_widget(stato, cfg, NOW)
    ore = widget_img._pioggia_oraria(stato, "pratignano", NOW)
    assert len(ore) == 24 and ore[-1] == 0.2 and ore[-2] == 1.8 and ore[-3] == 1.0
    vuoto = widget_img._pioggia_oraria(None, "pratignano", NOW)
    assert vuoto == [None] * 24
    for st in (stato, None):                     # con dati e senza (nessun dato): niente eccezioni
        f = widget_img.disegna(w, cfg, "chiaro", tmp_path / "g.png", st, NOW)
        assert Image.open(f).size == (1200, 600)
