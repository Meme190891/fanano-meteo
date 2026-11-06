"""Il widget intero disegnato come immagine (widget.png / widget_dark.png, 1200x600).

In KWGT basta un solo elemento Immagine che carica questo PNG da URL: niente formule da comporre.
Il riquadro ha angoli arrotondati e fondo trasparente fuori dagli angoli.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from matplotlib import font_manager
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 600
SCALA = 2           # disegno a 2x e riduco: bordi e testo piu' puliti
RAGGIO = 56
MARGINE_X, MARGINE_Y = 52, 40

TEMI = {
    "scuro": {"fondo": (24, 24, 23, 235), "ink": (240, 239, 236, 255), "ink2": (195, 194, 183, 255),
              "muted": (163, 162, 155, 255), "riga": (255, 255, 255, 28)},
    "chiaro": {"fondo": (252, 252, 251, 240), "ink": (11, 11, 11, 255), "ink2": (82, 81, 78, 255),
               "muted": (111, 110, 105, 255), "riga": (0, 0, 0, 22)},
}
ROSSO = (208, 59, 59, 255)


@lru_cache(maxsize=None)
def _font(peso: str, px: int) -> ImageFont.FreeTypeFont:
    prop = font_manager.FontProperties(family="DejaVu Sans", weight=peso)
    return ImageFont.truetype(font_manager.findfont(prop), px * SCALA)


def _hex(c: str) -> tuple[int, int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), 255


class _Tela:
    def __init__(self, tema: str):
        self.c = TEMI[tema]
        self.img = Image.new("RGBA", (W * SCALA, H * SCALA), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)
        self.d.rounded_rectangle((0, 0, W * SCALA - 1, H * SCALA - 1), radius=RAGGIO * SCALA, fill=self.c["fondo"])

    def larghezza(self, testo: str, font) -> float:
        return self.d.textlength(testo, font=font) / SCALA

    def testo(self, x, y, testo, px, colore, peso="normal", max_w=None, ancora="ls"):
        """Scrive con baseline in y; riduce il corpo se supera max_w (mai sotto il 70%)."""
        size = px
        font = _font(peso, size)
        while max_w and self.larghezza(testo, font) > max_w and size > px * 0.7:
            size -= 1
            font = _font(peso, size)
        self.d.text((x * SCALA, y * SCALA), testo, font=font, fill=colore, anchor=ancora)
        return self.larghezza(testo, font)

    def pallino(self, cx, cy, r, colore):
        self.d.ellipse(((cx - r) * SCALA, (cy - r) * SCALA, (cx + r) * SCALA, (cy + r) * SCALA), fill=colore)

    def linea(self, y):
        self.d.line((MARGINE_X * SCALA, y * SCALA, (W - MARGINE_X) * SCALA, y * SCALA), fill=self.c["riga"],
                    width=2 * SCALA)

    def salva(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.img.resize((W, H), Image.LANCZOS).save(path, optimize=True)
        return path


def disegna(widget: dict, cfg: dict, tema: str, path: Path) -> Path:
    w = widget
    t = _Tela(tema)
    c = t.c
    destra = W - MARGINE_X
    larg = W - 2 * MARGINE_X

    # riga 1: stato complessivo + ora
    y = MARGINE_Y + 50
    ora = w["aggiornato"][-5:]
    w_ora = t.larghezza(ora, _font("normal", 40))
    t.pallino(MARGINE_X + 15, y - 15, 15, _hex(w["stato_colore"]))
    t.testo(MARGINE_X + 46, y, w["stato"], 46, c["ink"], "bold", max_w=larg - 46 - w_ora - 24)
    t.testo(destra, y, ora, 40, c["ink2"], ancora="rs")
    t.linea(y + 26)

    # righe torrenti: nome | livello | freccia | pallino + stato soglia
    y += 98
    for tor in cfg["torrenti"]:
        k = tor["chiave"]
        nome = tor.get("nome_breve", tor["nome"])
        t.testo(MARGINE_X, y, nome, 46, c["ink"], "bold", max_w=250)
        livello = w[f"{k}_livello"].replace("-", "−")
        t.testo(MARGINE_X + 500, y, livello, 46, c["ink"], ancora="rs")
        t.testo(MARGINE_X + 545, y, w[f"{k}_freccia"], 46, c["ink"], ancora="ms")
        t.pallino(MARGINE_X + 615, y - 15, 15, _hex(w[f"{k}_colore"]))
        stato = w[f"{k}_soglia"] + (" · vecchio" if w[f"{k}_vecchio"] else "")
        t.testo(MARGINE_X + 645, y, stato, 40, c["ink2"], max_w=destra - (MARGINE_X + 645))
        y += 72

    # pioggia osservata e prevista
    t.linea(y - 46)
    y += 14
    t.testo(MARGINE_X, y, w["riga_pioggia"], 38, c["ink"], max_w=larg)
    y += 62
    t.testo(MARGINE_X, y, w["riga_previsione"], 38, c["ink"], max_w=larg)

    # allerta
    y += 62
    t.pallino(MARGINE_X + 12, y - 12, 12, _hex(w["allerta_oggi_colore"]))
    t.testo(MARGINE_X + 36, y, w["riga_allerta"], 34, c["ink2"], max_w=larg - 36)

    # piede: aggiornamento (rosso se dati vecchi) e invito al tocco
    y = H - MARGINE_Y + 2
    colore_piede = ROSSO if w.get("dato_vecchio") else c["muted"]
    t.testo(MARGINE_X, y, w["riga_aggiornamento"], 28, colore_piede, max_w=larg - 260)
    t.testo(destra, y, "tocca per i grafici", 28, c["muted"], ancora="rs")
    return t.salva(path)


def genera(widget: dict, cfg: dict, out: Path) -> list[Path]:
    return [disegna(widget, cfg, "chiaro", out / "widget.png"),
            disegna(widget, cfg, "scuro", out / "widget_dark.png")]
