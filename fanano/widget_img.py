"""Il widget intero disegnato come immagine (widget.png / widget_dark.png, 1200x600).

In KWGT basta un solo elemento Immagine che carica questo PNG da URL: niente formule da comporre.
Il riquadro ha angoli arrotondati e fondo trasparente fuori dagli angoli.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from matplotlib import font_manager
from PIL import Image, ImageDraw, ImageFont

from fanano.compute import serie_da_stato

W, H = 1200, 600
SCALA = 2           # disegno a 2x e riduco: bordi e testo piu' puliti
RAGGIO = 56
MARGINE_X, MARGINE_Y = 52, 40

TEMI = {
    "scuro": {"fondo": (24, 24, 23, 235), "ink": (240, 239, 236, 255), "ink2": (195, 194, 183, 255),
              "muted": (163, 162, 155, 255), "riga": (255, 255, 255, 28), "barre": (57, 135, 229, 255),
              "griglia": (255, 255, 255, 40)},
    "chiaro": {"fondo": (252, 252, 251, 240), "ink": (11, 11, 11, 255), "ink2": (82, 81, 78, 255),
               "muted": (111, 110, 105, 255), "riga": (0, 0, 0, 22), "barre": (42, 120, 214, 255),
               "griglia": (0, 0, 0, 45)},
}
ORE_GRAFICO = 24
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


def _pioggia_oraria(stato: dict | None, chiave: str, now: datetime) -> list[float | None]:
    """Ultime ORE_GRAFICO ore di pioggia (mm/h), dalla piu' vecchia alla piu' recente; None = dato mancante."""
    ore: list[float | None] = [None] * ORE_GRAFICO
    if not stato:
        return ore
    fine = now.replace(minute=0, second=0, microsecond=0)
    for t, v in serie_da_stato(stato.get("serie", {}).get(f"pioggia_{chiave}")):
        i = ORE_GRAFICO - 1 - int(round((fine - t).total_seconds() / 3600))
        if 0 <= i < ORE_GRAFICO:
            ore[i] = v
    return ore


def _grafico_pioggia(t: "_Tela", x0, y_base, larg, alt, valori, ytop, titolo, c):
    """Barre orarie con titolo sopra e asse in basso; il valore massimo e' scritto sopra la sua barra."""
    t.testo(x0, y_base - alt - 12, titolo, 26, c["ink2"], max_w=larg)
    t.d.line((x0 * SCALA, y_base * SCALA, (x0 + larg) * SCALA, y_base * SCALA), fill=c["griglia"], width=2 * SCALA)
    passo = larg / ORE_GRAFICO
    barra = max(2.0, passo - 4)
    for i, v in enumerate(valori):
        if not v:
            continue
        h = max(2.0, alt * min(v, ytop) / ytop)
        bx = x0 + i * passo + (passo - barra) / 2
        t.d.rounded_rectangle((bx * SCALA, (y_base - h) * SCALA, (bx + barra) * SCALA, y_base * SCALA),
                              radius=min(4, barra / 2) * SCALA, fill=c["barre"])
    validi = [v for v in valori if v is not None]
    if validi and max(validi) > 0:
        i_max = max(range(ORE_GRAFICO), key=lambda i: valori[i] or 0)
        v_max = valori[i_max]
        h = alt * min(v_max, ytop) / ytop
        x_lab = min(max(x0 + i_max * passo + passo / 2, x0 + 20), x0 + larg - 20)
        t.testo(x_lab, y_base - h - 6, f"{v_max:g}", 22, c["ink"], ancora="ms")
    elif not validi:
        t.testo(x0 + larg / 2, y_base - alt / 2 + 8, "nessun dato", 24, c["muted"], ancora="ms")
    else:
        t.testo(x0 + larg / 2, y_base - alt / 2 + 8, "nessuna pioggia", 24, c["muted"], ancora="ms")


def disegna(widget: dict, cfg: dict, tema: str, path: Path, stato: dict | None = None,
            now: datetime | None = None) -> Path:
    w = widget
    t = _Tela(tema)
    c = t.c
    destra = W - MARGINE_X
    larg = W - 2 * MARGINE_X
    now = now or datetime.now(timezone.utc)

    # riga 1: stato complessivo + ora
    y = MARGINE_Y + 44
    ora = w["aggiornato"][-5:]
    w_ora = t.larghezza(ora, _font("normal", 38))
    t.pallino(MARGINE_X + 14, y - 14, 14, _hex(w["stato_colore"]))
    t.testo(MARGINE_X + 42, y, w["stato"], 42, c["ink"], "bold", max_w=larg - 42 - w_ora - 24)
    t.testo(destra, y, ora, 38, c["ink2"], ancora="rs")
    t.linea(y + 20)

    # righe torrenti: nome | livello | freccia | pallino + stato soglia
    y += 76
    for tor in cfg["torrenti"]:
        k = tor["chiave"]
        nome = tor.get("nome_breve", tor["nome"])
        t.testo(MARGINE_X, y, nome, 42, c["ink"], "bold", max_w=250)
        livello = w[f"{k}_livello"].replace("-", "−")
        t.testo(MARGINE_X + 480, y, livello, 42, c["ink"], ancora="rs")
        t.testo(MARGINE_X + 525, y, w[f"{k}_freccia"], 42, c["ink"], ancora="ms")
        t.pallino(MARGINE_X + 592, y - 14, 14, _hex(w[f"{k}_colore"]))
        stato_s = w[f"{k}_soglia"] + (" · vecchio" if w[f"{k}_vecchio"] else "")
        t.testo(MARGINE_X + 620, y, stato_s, 36, c["ink2"], max_w=destra - (MARGINE_X + 620))
        y += 58
    t.linea(y - 36)

    # due grafici affiancati: pioggia oraria ultime 24 h, stessa scala
    pluv = cfg["pluviometri"][:2]
    serie = [_pioggia_oraria(stato, p["chiave"], now) for p in pluv]
    massimo = max([v for s in serie for v in s if v is not None] + [0])
    ytop = max(2.0, massimo * 1.25)
    gap = 40
    larg_g = (larg - gap * (len(pluv) - 1)) / max(1, len(pluv))
    y_base = y + 126
    for j, (p, valori) in enumerate(zip(pluv, serie)):
        k = p["chiave"]
        titolo = f"{p.get('nome_breve', p['nome'])} · 24h {w.get(k + '_24h', 'n.d.')} mm"
        _grafico_pioggia(t, MARGINE_X + j * (larg_g + gap), y_base, larg_g, 96, valori, ytop, titolo, c)
    t.testo(MARGINE_X, y_base + 26, "pioggia ora per ora, ultime 24 h", 22, c["muted"])
    t.testo(destra, y_base + 26, "adesso", 22, c["muted"], ancora="rs")

    # previsione e allerta
    y = y_base + 74
    t.testo(MARGINE_X, y, w["riga_previsione"], 34, c["ink"], max_w=larg)
    y += 46
    t.pallino(MARGINE_X + 11, y - 11, 11, _hex(w["allerta_oggi_colore"]))
    t.testo(MARGINE_X + 32, y, w["riga_allerta"], 30, c["ink2"], max_w=larg - 32)

    # piede: aggiornamento (rosso se dati vecchi) e invito al tocco
    y = H - MARGINE_Y + 12
    colore_piede = ROSSO if w.get("dato_vecchio") else c["muted"]
    t.testo(MARGINE_X, y, w["riga_aggiornamento"], 24, colore_piede, max_w=larg - 240)
    t.testo(destra, y, "tocca per i grafici", 24, c["muted"], ancora="rs")
    return t.salva(path)


def genera(widget: dict, cfg: dict, out: Path, stato: dict | None = None,
           now: datetime | None = None) -> list[Path]:
    return [disegna(widget, cfg, "chiaro", out / "widget.png", stato, now),
            disegna(widget, cfg, "scuro", out / "widget_dark.png", stato, now)]
