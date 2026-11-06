"""Il widget intero disegnato come immagine (widget.png / widget_dark.png, 1200x600).

In KWGT basta un solo elemento Immagine che carica questo PNG da URL: niente formule da comporre.
Il riquadro ha angoli arrotondati e fondo trasparente fuori dagli angoli.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from matplotlib import font_manager
from PIL import Image, ImageDraw, ImageFont

from fanano.arpae import ROME
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
    def __init__(self, tema: str, w: int = W, h: int = H):
        self.c = TEMI[tema]
        self.w, self.h = w, h
        self.img = Image.new("RGBA", (w * SCALA, h * SCALA), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)
        self.d.rounded_rectangle((0, 0, w * SCALA - 1, h * SCALA - 1), radius=RAGGIO * SCALA, fill=self.c["fondo"])

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
        self.d.line((MARGINE_X * SCALA, y * SCALA, (self.w - MARGINE_X) * SCALA, y * SCALA), fill=self.c["riga"],
                    width=2 * SCALA)

    def salva(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.img.resize((self.w, self.h), Image.LANCZOS).save(path, optimize=True)
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
            disegna(widget, cfg, "scuro", out / "widget_dark.png", stato, now),
            disegna43(widget, cfg, "chiaro", out / "widget43.png", stato, now),
            disegna43(widget, cfg, "scuro", out / "widget43_dark.png", stato, now)]


# --------------------------------------------------------------------------- versione 4x3 (1200x900)

W43, H43 = 1200, 900
GIORNI_BREVI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]


def _grafico_pioggia_grande(t: "_Tela", x0, y_base, larg, alt, valori, ytop, passo_griglia, titolo, now, c):
    """Barre orarie (ultime 24 h) con griglia in mm, ore sotto l'asse e massimo etichettato."""
    t.testo(x0, y_base - alt - 18, titolo, 30, c["ink"], "bold", max_w=larg)
    # griglia orizzontale con etichetta in mm
    v = passo_griglia
    while v < ytop:
        yg = y_base - alt * v / ytop
        t.d.line((x0 * SCALA, yg * SCALA, (x0 + larg) * SCALA, yg * SCALA), fill=c["riga"], width=2 * SCALA)
        t.testo(x0 + larg, yg - 6, f"{v:g} mm", 22, c["muted"], ancora="rs")
        v += passo_griglia
    t.d.line((x0 * SCALA, y_base * SCALA, (x0 + larg) * SCALA, y_base * SCALA), fill=c["griglia"], width=2 * SCALA)
    passo = larg / ORE_GRAFICO
    barra = max(2.0, passo - 5)
    fine = now.astimezone(ROME).replace(minute=0, second=0, microsecond=0)
    for i, val in enumerate(valori):
        cx = x0 + i * passo + passo / 2
        ora_barra = fine - timedelta(hours=ORE_GRAFICO - 1 - i)     # fine dell'ora rappresentata
        if ora_barra.hour % 6 == 0:
            t.d.line((cx * SCALA, y_base * SCALA, cx * SCALA, (y_base + 8) * SCALA), fill=c["griglia"],
                     width=2 * SCALA)
            t.testo(cx, y_base + 34, f"{ora_barra.hour:02d}", 24, c["muted"], ancora="ms")
        if not val:
            continue
        h = max(3.0, alt * min(val, ytop) / ytop)
        bx = cx - barra / 2
        t.d.rounded_rectangle((bx * SCALA, (y_base - h) * SCALA, (bx + barra) * SCALA, y_base * SCALA),
                              radius=min(5, barra / 2) * SCALA, fill=c["barre"])
    validi = [x for x in valori if x is not None]
    if validi and max(validi) > 0:
        i_max = max(range(ORE_GRAFICO), key=lambda i: valori[i] or 0)
        h = alt * min(valori[i_max], ytop) / ytop
        x_lab = min(max(x0 + i_max * passo + passo / 2, x0 + 22), x0 + larg - 22)
        t.testo(x_lab, y_base - h - 8, f"{valori[i_max]:g}", 26, c["ink"], "bold", ancora="ms")
    else:
        t.testo(x0 + larg / 2, y_base - alt / 2 + 8, "nessun dato" if not validi else "nessuna pioggia", 28,
                c["muted"], ancora="ms")


def _giorni_previsione(stato: dict | None, now: datetime) -> list[tuple[str, float | None, float | None]]:
    """[(etichetta, min, max)] per oggi, domani, dopodomani dalla previsione salvata nello stato."""
    oggi = now.astimezone(ROME).date()
    per_data = {g.get("data"): g for g in ((stato or {}).get("previsione") or {}).get("giorni", []) if g.get("data")}
    out = []
    for i in range(3):
        d = oggi + timedelta(days=i)
        g = per_data.get(d.isoformat())
        etichetta = ("oggi", "domani")[i] if i < 2 else f"{GIORNI_BREVI[d.weekday()]} {d.day}"
        out.append((etichetta, g.get("prec_min") if g else None, g.get("prec_max") if g else None))
    return out


def _fmt_mm(a: float | None, b: float | None) -> str:
    if b is None:
        return "n.d."
    a = b if a is None else a
    f = lambda x: f"{x:g}"
    return f(b) if a == b else f"{f(a)}-{f(b)}"


def _grafico_previsione(t: "_Tela", x0, y_base, larg, alt, giorni, c):
    """Tre colonne: altezza = massimo previsto, parte piena = minimo, numero sopra, giorno sotto."""
    massimo = max([g[2] for g in giorni if g[2] is not None] + [0])
    ytop = max(10.0, massimo * 1.3)
    t.d.line((x0 * SCALA, y_base * SCALA, (x0 + larg) * SCALA, y_base * SCALA), fill=c["griglia"], width=2 * SCALA)
    slot = larg / len(giorni)
    barra = min(90.0, slot * 0.55)
    # colore pieno a meta' tra il blu e lo sfondo (la trasparenza mostrerebbe cio' che sta dietro al widget)
    chiaro = tuple(round(b * 0.45 + f * 0.55) for b, f in zip(c["barre"][:3], c["fondo"][:3])) + (255,)
    for i, (etichetta, pmin, pmax) in enumerate(giorni):
        cx = x0 + i * slot + slot / 2
        t.testo(cx, y_base + 34, etichetta, 26, c["ink2"], ancora="ms")
        if pmax is None:
            t.testo(cx, y_base - 12, "n.d.", 26, c["muted"], ancora="ms")
            continue
        h_max = alt * min(pmax, ytop) / ytop
        h_min = alt * min(pmin or 0, ytop) / ytop
        bx0, bx1 = (cx - barra / 2) * SCALA, (cx + barra / 2) * SCALA
        if h_max > 0:
            t.d.rounded_rectangle((bx0, (y_base - max(h_max, 3)) * SCALA, bx1, y_base * SCALA),
                                  radius=6 * SCALA, fill=chiaro)
        if h_min > 0:
            t.d.rounded_rectangle((bx0, (y_base - max(h_min, 3)) * SCALA, bx1, y_base * SCALA),
                                  radius=6 * SCALA, fill=c["barre"])
        t.testo(cx, y_base - max(h_max, 0) - 10, _fmt_mm(pmin, pmax) + " mm", 28, c["ink"], "bold", ancora="ms")
    if all(g[2] == 0 for g in giorni):
        t.testo(x0 + larg / 2, y_base - alt / 2 - 10, "nessuna pioggia prevista", 28, c["muted"], ancora="ms")


def disegna43(widget: dict, cfg: dict, tema: str, path: Path, stato: dict | None = None,
              now: datetime | None = None) -> Path:
    """Widget 4x3: pioggia osservata in primo piano, torrenti e previsione (a grafico) sotto."""
    w = widget
    t = _Tela(tema, W43, H43)
    c = t.c
    destra = W43 - MARGINE_X
    larg = W43 - 2 * MARGINE_X
    now = now or datetime.now(timezone.utc)

    # intestazione: stato, ora, allerta
    y = MARGINE_Y + 44
    ora = w["aggiornato"][-5:]
    w_ora = t.larghezza(ora, _font("normal", 38))
    t.pallino(MARGINE_X + 14, y - 14, 14, _hex(w["stato_colore"]))
    t.testo(MARGINE_X + 42, y, w["stato"], 42, c["ink"], "bold", max_w=larg - 42 - w_ora - 24)
    t.testo(destra, y, ora, 38, c["ink2"], ancora="rs")
    y += 44
    t.pallino(MARGINE_X + 11, y - 10, 10, _hex(w["allerta_oggi_colore"]))
    t.testo(MARGINE_X + 32, y, w["riga_allerta"], 28, c["ink2"], max_w=larg - 32)
    t.linea(y + 20)

    # pioggia osservata: due grafici grandi, stessa scala
    pluv = cfg["pluviometri"][:2]
    serie = [_pioggia_oraria(stato, p["chiave"], now) for p in pluv]
    massimo = max([v for s in serie for v in s if v is not None] + [0])
    passo_g = next(p for p in (0.5, 1, 2, 5, 10, 20, 50) if p >= max(2.0, massimo * 1.3) / 4)
    ytop = max(2.0, massimo * 1.3)
    gap = 44
    larg_g = (larg - gap) / 2
    y_base = y + 20 + 300
    for j, (p, valori) in enumerate(zip(pluv, serie)):
        k = p["chiave"]
        titolo = (f"{p.get('nome_breve', p['nome'])}  ·  1h {w.get(k + '_1h', 'n.d.')}  ·  "
                  f"24h {w.get(k + '_24h', 'n.d.')} mm")
        _grafico_pioggia_grande(t, MARGINE_X + j * (larg_g + gap), y_base, larg_g, 230, valori, ytop, passo_g,
                                titolo, now, c)
    t.testo(MARGINE_X, y_base + 66, "pioggia caduta ora per ora, ultime 24 ore", 24, c["muted"])
    t.linea(y_base + 86)

    # in basso a sinistra: torrenti; in basso a destra: previsione a grafico
    y0 = y_base + 86
    x_dx = MARGINE_X + 560
    yt = y0 + 70
    for tor in cfg["torrenti"]:
        k = tor["chiave"]
        t.testo(MARGINE_X, yt, tor.get("nome_breve", tor["nome"]), 38, c["ink"], "bold", max_w=170)
        t.testo(MARGINE_X + 330, yt, w[f"{k}_livello"].replace("-", "−"), 38, c["ink"], ancora="rs")
        t.testo(MARGINE_X + 366, yt, w[f"{k}_freccia"], 38, c["ink"], ancora="ms")
        t.pallino(MARGINE_X + 412, yt - 12, 12, _hex(w[f"{k}_colore"]))
        t.testo(MARGINE_X + 434, yt, w[f"{k}_soglia"] + (" !" if w[f"{k}_vecchio"] else ""), 26, c["ink2"],
                max_w=x_dx - MARGINE_X - 434 - 16)
        yt += 62
    t.testo(MARGINE_X, yt - 8, "livello attuale · tendenza 3 h", 22, c["muted"])

    t.testo(x_dx, y0 + 38, f"Pioggia prevista ({w.get('prev_zona', 'rilievi')})", 26, c["ink2"], "bold",
            max_w=destra - x_dx)
    _grafico_previsione(t, x_dx, H43 - MARGINE_Y - 74, destra - x_dx, 110, _giorni_previsione(stato, now), c)

    # piede
    y = H43 - MARGINE_Y + 12
    colore_piede = ROSSO if w.get("dato_vecchio") else c["muted"]
    t.testo(MARGINE_X, y, w["riga_aggiornamento"], 24, colore_piede, max_w=larg - 240)
    t.testo(destra, y, "tocca per i grafici", 24, c["muted"], ancora="rs")
    return t.salva(path)
