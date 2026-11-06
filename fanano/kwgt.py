"""Preset KWGT importabile (Fanano_meteo.kwgt) con un solo elemento: l'immagine widget.png.

Il formato .kwgt non e' documentato ufficialmente. Questa struttura ricalca preset reali
esportati da KWGT 3.7x (preset_info.version 13):
  * zip con preset.json come prima voce, piu' preset_thumb_portrait.jpg e preset_thumb_landscape.jpg
    (immagini WebP, come nei preset reali);
  * preset.json = preset_info (prima chiave) + preset_root (RootLayerModule);
  * proprieta' calcolate da formula in internal_formulas, con flag 10 in internal_toggles;
  * tocco: azione LAUNCH_ACTIVITY con un intent Android, come nei preset reali; qui un intent
    VIEW sulla pagina https dei grafici.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image

NOME_FILE = "Fanano_meteo.kwgt"
SET = 10


def formula_immagine(base_url: str) -> str:
    """URL dell'immagine: variante scura col tema scuro del telefono, parametro che cambia ogni 30'.

    Formula unica tra $...$ (come nei preset reali) con concatenazione "+" documentata da Kustom.
    Il parametro t cambia alle :15 e :45, dopo le pubblicazioni delle :07 e :37: KWGT riscarica
    l'immagine quando cambia l'URL.
    """
    return (f'$"{base_url.rstrip("/")}/widget" + if(si(darkmode) = 1, "_dark", "") + ".png?t=" + '
            'mu(floor, (df(S) - 900) / 1800)$')


def intent_pagina(base_url: str) -> str:
    """Intent Android che apre la pagina index.html nel browser."""
    u = urlparse(base_url.rstrip("/") + "/index.html")
    return (f"intent://{u.netloc}{u.path}#Intent;scheme={u.scheme};action=android.intent.action.VIEW;"
            "S.org.kustom.intent.label=Fanano%20meteo;end")


def preset_json(cfg: dict) -> dict:
    base = cfg["pubblicazione"]["base_url"]
    tocco = {"type": "SINGLE_TAP", "action": "LAUNCH_ACTIVITY", "intent": intent_pagina(base)}
    immagine = {
        "internal_type": "BitmapModule",
        "internal_title": "Fanano meteo",
        "internal_toggles": {"bitmap_bitmap": SET, "bitmap_width": SET},
        "internal_formulas": {
            "bitmap_bitmap": formula_immagine(base),
            # tutta la larghezza, ma senza uscire in altezza (l'immagine e' 2:1)
            "bitmap_width": "$mu(min, si(rwidth), si(rheight) * 2)$",
        },
        "bitmap_width": 300.0,
        "internal_events": [tocco],
    }
    return {
        "preset_info": {
            "version": 13,
            "title": "Fanano meteo",
            "description": "Torrenti Leo e Panaro, pioggia e allerta a Fanano (dati Arpae, non validati)",
            "author": "fanano-meteo",
            "email": "",
            "width": 918,
            "height": 542,
            "features": "",
            "release": 377435216,
            "locked": False,
            "pflags": 0,
        },
        "preset_root": {
            "internal_type": "RootLayerModule",
            "internal_events": [tocco],
            "viewgroup_items": [immagine],
        },
    }


def _miniatura(png: Path, size: tuple[int, int]) -> bytes:
    img = Image.open(png).convert("RGBA")
    img.thumbnail(size, Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=85)
    return buf.getvalue()


def costruisci(cfg: dict, anteprima_png: Path) -> bytes:
    """Contenuto del file .kwgt (zip)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("preset.json", json.dumps(preset_json(cfg), ensure_ascii=False))
        z.writestr("preset_thumb_portrait.jpg", _miniatura(anteprima_png, (1024, 1024)))
        z.writestr("preset_thumb_landscape.jpg", _miniatura(anteprima_png, (1024, 1024)))
    return buf.getvalue()


def genera(cfg: dict, out: Path, anteprima_png: Path) -> Path:
    path = out / NOME_FILE
    path.write_bytes(costruisci(cfg, anteprima_png))
    return path
