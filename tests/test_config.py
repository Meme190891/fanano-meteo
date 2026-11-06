"""Controlli di struttura sul config.yaml reale (quello che usa il workflow)."""

import re

from fanano.config import load_config


def test_config_reale_valido():
    cfg = load_config()
    for sezione in ("arpae", "variabili", "zona_allerta", "previsione", "torrenti", "pluviometri", "regole",
                    "colori", "pubblicazione"):
        assert sezione in cfg, f"manca la sezione '{sezione}'"
    assert cfg["previsione"]["zona"] in ("rilievi", "pianura")
    chiavi_p = [p["chiave"] for p in cfg["pluviometri"]]
    chiavi_t = [t["chiave"] for t in cfg["torrenti"]]
    assert cfg["torrenti"] and cfg["pluviometri"]
    assert len(set(chiavi_p + chiavi_t)) == len(chiavi_p) + len(chiavi_t), "chiavi duplicate"
    for elem in cfg["torrenti"] + cfg["pluviometri"]:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", elem["chiave"]), f"chiave non valida: {elem['chiave']}"
        assert isinstance(elem["id"], str) and elem["id"].isdigit(), f"id deve essere una stringa di cifre: {elem}"
        assert elem.get("nome")
    for t in cfg["torrenti"]:
        for p in t.get("pluviometri", []):
            assert p in chiavi_p, f"{t['chiave']}: pluviometro '{p}' non definito"
    for nome in ("verde", "giallo", "arancio", "rosso", "grigio"):
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", cfg["colori"][nome])
    assert cfg["pubblicazione"]["base_url"].startswith("https://")
