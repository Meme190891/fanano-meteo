"""Grafici PNG per torrente (tema chiaro e scuro) e pagina index.html (destinazione del tocco sul widget).

Ogni PNG ha tre pannelli impilati sullo stesso asse del tempo (ultime 72 ore):
  1. livello idrometrico (linea) con le soglie Arpae (linee tratteggiate etichettate);
  2-3. pioggia oraria dei pluviometri associati (barre, stessa scala per confronto).
Niente doppio asse y: ogni grandezza ha il suo pannello e la sua scala.

Dimensioni pensate per lo schermo di un telefono: 1080 px di larghezza (360 dp a 3x).
"""

from __future__ import annotations

import html
import math
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator  # noqa: E402

from fanano.arpae import ROME  # noqa: E402
from fanano.compute import serie_da_stato  # noqa: E402

# Superfici e inchiostri (palette di riferimento della skill dataviz), serie = slot categorico 1 (blu)
TEMI = {
    "chiaro": {"surface": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#898781",
               "grid": "#e1e0d9", "axis": "#c3c2b7", "serie": "#2a78d6"},
    "scuro": {"surface": "#1a1a19", "ink": "#f0efec", "ink2": "#c3c2b7", "muted": "#898781",
              "grid": "#2c2c2a", "axis": "#383835", "serie": "#3987e5"},
}
SUFFISSO = {"chiaro": "", "scuro": "_dark"}

W, H, DPI = 1080, 1330, 100
FONT = "DejaVu Sans"
GIORNI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]


def pt(px: float) -> float:
    """Pixel dell'immagine -> punti tipografici (a DPI=100)."""
    return px * 72 / DPI


def _meno(testo: str) -> str:
    """Trattino -> segno meno tipografico davanti alle cifre (solo nei grafici, widget.json resta ASCII)."""
    import re
    return re.sub(r"-(?=\d)", "−", testo)


def _locale(t: datetime) -> datetime:
    """Datetime con fuso -> ora italiana senza fuso (matplotlib la disegna cosi' com'e')."""
    return t.astimezone(ROME).replace(tzinfo=None)


def _con_buchi(serie, passo_max: timedelta):
    """Serie -> (tempi, valori) con None dove mancano dati, cosi' la linea si interrompe."""
    xs, ys, prec = [], [], None
    for t, v in serie:
        if prec is not None and t - prec > passo_max:
            xs.append(_locale(prec + (t - prec) / 2))
            ys.append(math.nan)
        xs.append(_locale(t))
        ys.append(v)
        prec = t
    return xs, ys


def _stile_asse(ax, c: dict, ytick_px: int = 30) -> None:
    ax.set_facecolor(c["surface"])
    for lato in ("top", "right", "left"):
        ax.spines[lato].set_visible(False)
    ax.spines["bottom"].set_color(c["axis"])
    ax.spines["bottom"].set_linewidth(pt(2))
    ax.grid(axis="y", color=c["grid"], linewidth=pt(2), linestyle="-")
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0, labelsize=pt(ytick_px), labelcolor=c["muted"], pad=pt(10))
    ax.tick_params(axis="x", length=0, labelbottom=False)


def _tocca(fig, ax, candidato, testo: str, punti_px, margine: float = 8) -> bool:
    """True se il riquadro dell'etichetta (o il suo uscire dall'area dati) si sovrappone alla curva."""
    (x, y), (dx, dy), va = candidato
    t = ax.annotate(testo, (x, y), xytext=(dx, dy), textcoords="offset points", ha="right", va=va,
                    fontsize=pt(34), fontweight="bold")
    bb = t.get_window_extent(fig.canvas.get_renderer())
    t.remove()
    area = ax.get_window_extent()
    if bb.y1 > area.y1 or bb.y0 < area.y0:
        return True
    x0, x1, y0, y1 = bb.x0 - margine, bb.x1 + margine, bb.y0 - margine, bb.y1 + margine
    return any(x0 <= px <= x1 and y0 <= py <= y1 for px, py in punti_px)


def _scrivi(fig, x_px: float, y_top_px: float, testo: str, size_px: float, colore: str, bold: bool = False,
            max_px: float = W - 80, min_px: float = 28):
    """Testo posizionato in pixel dall'alto; se e' piu' largo di max_px riduce il corpo (non sotto min_px)."""
    t = fig.text(x_px / W, 1 - y_top_px / H, testo, fontsize=pt(size_px), color=colore,
                 fontweight="bold" if bold else "normal")
    r = fig.canvas.get_renderer()
    while t.get_window_extent(r).width > max_px and size_px > min_px:
        size_px -= 1
        t.set_fontsize(pt(size_px))
    return t


def grafico_torrente(st: dict, cfg: dict, widget: dict, chiave: str, tema: str, now: datetime, path: Path) -> Path:
    c = TEMI[tema]
    col = cfg["colori"]
    torrente = next(t for t in cfg["torrenti"] if t["chiave"] == chiave)
    idro = st.get("idrometri", {}).get(torrente["id"], {})
    soglie = [(i, idro.get(f"soglia{i}")) for i in (1, 2, 3)]
    colore_soglia = {1: col["giallo"], 2: col["arancio"], 3: col["rosso"]}
    fine = _locale(now)
    inizio = fine - timedelta(hours=72)

    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI, facecolor=c["surface"])
    plt.rcParams["font.family"] = FONT
    sx, dx = 112 / W, (W - 44) / W            # margini orizzontali dell'area dati

    def rett(top_px, bottom_px):
        return [sx, 1 - bottom_px / H, dx - sx, (bottom_px - top_px) / H]

    ax_l = fig.add_axes(rett(240, 780))
    pluv = [p for p in cfg["pluviometri"] if p["chiave"] in torrente.get("pluviometri", [])]
    ax_p = []
    top = 840
    for _ in pluv:
        ax_p.append(fig.add_axes(rett(top, top + 140), sharex=ax_l))
        top += 140 + 56

    # ---- intestazione (righe che si rimpiccioliscono fino a 28 px se non entrano)
    k = chiave
    _scrivi(fig, 40, 78, torrente["nome"], 50, c["ink"], bold=True)
    if widget[f"{k}_livello"] == "n.d.":
        riga2 = "Nessun dato di livello disponibile"
    else:
        riga2 = _meno(f"{widget[f'{k}_livello']}  {widget[f'{k}_freccia']} {widget[f'{k}_tendenza']}"
                      + (f" ({widget[f'{k}_delta3h']} in 3h)" if widget[f"{k}_delta3h"] != "n.d." else ""))
    if widget.get(f"{k}_vecchio"):
        riga2 += " · DATO VECCHIO"
    _scrivi(fig, 40, 136, riga2, 34, c["ink"])
    idx = {"soglia 1": 1, "soglia 2": 2, "soglia 3": 3}.get(widget[f"{k}_soglia"], 0)
    pallino = colore_soglia.get(idx, col["verde"] if widget[f"{k}_soglia"] == "normale" else col["grigio"])
    _scrivi(fig, 40, 190, "●", 34, pallino)
    riga3 = widget[f"{k}_soglia"].capitalize()
    if any(v is not None for _, v in soglie):
        riga3 += f" · soglie {widget[f'{k}_soglie']}"
    if widget[f"{k}_ora"] != "n.d.":
        riga3 += f" · dato {widget[f'{k}_ora']}"
    _scrivi(fig, 82, 190, riga3, 30, c["ink2"], max_px=W - 122)

    # ---- pannello livello (metri)
    _stile_asse(ax_l, c)
    serie = [(t, v) for t, v in serie_da_stato(st.get("serie", {}).get(f"livello_{chiave}"))
             if _locale(t) >= inizio]
    if serie:
        xs, ys = _con_buchi(serie, timedelta(minutes=45))
        valori = [v for _, v in serie]
        lo, hi = min(valori), max(valori)
        prossima = min((v for _, v in soglie if v is not None and v > hi), default=None)
        if prossima is not None:             # mostra sempre quanto manca alla prossima soglia
            hi = prossima
        if hi - lo < 0.5:                        # evita di ingigantire variazioni di pochi cm
            mid = (hi + lo) / 2
            lo, hi = mid - 0.25, mid + 0.25
        pad = (hi - lo) * 0.14
        ax_l.set_ylim(lo - pad, hi + pad)
        ax_l.plot(xs, ys, color=c["serie"], linewidth=pt(6), solid_capstyle="round", solid_joinstyle="round",
                  zorder=3)
        t_ult, v_ult = serie[-1]
        ax_l.scatter([_locale(t_ult)], [v_ult], s=pt(26) ** 2, color=c["serie"], edgecolors=c["surface"],
                     linewidths=pt(6), zorder=4)
        y0, y1 = ax_l.get_ylim()
        # etichetta del valore attuale: prima posizione candidata che non tocca la curva
        etichetta = _meno(f"{v_ult:.2f} m")
        # posizioni vicine al punto, sopra/sotto a sinistra, a distanza crescente; se nessuna e' libera
        # l'etichetta non si disegna (il valore e' gia' nell'intestazione)
        x_ult = _locale(t_ult)
        candidati = [((x_ult, v_ult), (-pt(26), pt(d) * segno), "bottom" if segno > 0 else "top")
                     for d in (10, 45, 80) for segno in (1, -1)]
        punti_px = ax_l.transData.transform([(mdates.date2num(x), y) for x, y in zip(xs, ys) if not math.isnan(y)])
        scelta = next((cand for cand in candidati if not _tocca(fig, ax_l, cand, etichetta, punti_px)), None)
        if scelta:
            xy, off, va = scelta
            ax_l.annotate(etichetta, xy, xytext=off, textcoords="offset points", ha="right", va=va,
                          fontsize=pt(34), fontweight="bold", color=c["ink"], zorder=5)
        for i, s in soglie:
            if s is None or not (y0 <= s <= y1):
                continue
            ax_l.axhline(s, color=colore_soglia[i], linewidth=pt(5), dashes=(4, 2.5), zorder=2)
            ax_l.annotate(f"Soglia {i} · {s:.1f} m", (0, s), xycoords=("axes fraction", "data"),
                          xytext=(pt(8), pt(8)), textcoords="offset points", fontsize=pt(30), color=c["ink2"],
                          va="bottom", ha="left", zorder=5)
        ax_l.yaxis.set_major_locator(MaxNLocator(nbins=5, steps=[1, 2, 2.5, 5, 10]))
        ax_l.yaxis.set_major_formatter(FuncFormatter(lambda v, _: _meno(f"{v:.1f}")))
    else:
        ax_l.set_ylim(0, 1)
        ax_l.set_yticks([])
        ax_l.grid(False)
        ax_l.text(0.5, 0.5, "Nessun dato di livello disponibile", transform=ax_l.transAxes, ha="center",
                  va="center", fontsize=pt(34), color=c["ink2"])

    # ---- pannelli pioggia (mm/ora, stessa scala per tutti)
    serie_p = {p["chiave"]: [(t, v) for t, v in serie_da_stato(st.get("serie", {}).get(f"pioggia_{p['chiave']}"))
                             if _locale(t) > inizio] for p in pluv}
    massimo = max([v for s in serie_p.values() for _, v in s] + [0])
    ytop = max(4.0, massimo * 1.3)
    for ax, p in zip(ax_p, pluv):
        _stile_asse(ax, c, ytick_px=28)
        s = serie_p[p["chiave"]]
        ax.set_ylim(0, ytop)
        passo = max(x for x in (0.5, 1, 2, 5, 10, 20, 50, 100) if x <= ytop * 0.6)
        ax.set_yticks([0, passo])
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        if s:
            xs = [_locale(t) - timedelta(minutes=30) for t, _ in s]
            ax.bar(xs, [v for _, v in s], width=40 / 1440, color=c["serie"], linewidth=0, zorder=3)
            t_max, v_max = max(s, key=lambda x: x[1])
            if v_max > 0:
                ax.annotate(f"{v_max:g}", (_locale(t_max) - timedelta(minutes=30), v_max), xytext=(0, pt(6)),
                            textcoords="offset points", ha="center", va="bottom", fontsize=pt(28),
                            color=c["ink"], zorder=5, annotation_clip=False)
        kp = p["chiave"]
        ax.text(0, 1, f"{p.get('nome_breve', p['nome'])} · pioggia oraria, mm · 24h {widget.get(f'{kp}_24h', 'n.d.')}"
                      f" · 72h {widget.get(f'{kp}_72h', 'n.d.')}",
                transform=ax.transAxes, ha="left", va="bottom", fontsize=pt(28), color=c["ink2"], zorder=6)

    # ---- asse del tempo: separatori a mezzanotte, nome del giorno a mezzogiorno
    ax_l.set_xlim(inizio, fine)
    mezzanotte = datetime.combine(inizio.date() + timedelta(days=1), datetime.min.time())
    giorni = []
    while mezzanotte < fine:
        giorni.append(mezzanotte)
        mezzanotte += timedelta(days=1)
    for ax in [ax_l, *ax_p]:
        for g in giorni:
            ax.axvline(g, color=c["grid"], linewidth=pt(2), zorder=1)
    ultimo = ax_p[-1] if ax_p else ax_l
    bordi = [inizio, *giorni, fine]
    centri = [a + (b - a) / 2 for a, b in zip(bordi, bordi[1:]) if b - a >= timedelta(hours=7)]
    ultimo.set_xticks(centri)
    ultimo.xaxis.set_major_formatter(FuncFormatter(
        lambda x, _: (lambda d: f"{GIORNI[d.weekday()]} {d.day}")(mdates.num2date(x))))
    ultimo.tick_params(axis="x", labelbottom=True, labelsize=pt(30), labelcolor=c["muted"], pad=pt(10))

    # ---- piede
    pub = cfg["pubblicazione"]
    fig.text(40 / W, 52 / H, f"{pub['disclaimer']} · aggiornato {widget['aggiornato']}",
             fontsize=pt(28), color=c["muted"])
    fig.text(40 / W, 14 / H, "Fonte: Allerta Meteo Emilia-Romagna (Arpae) · CC BY-NC-SA 4.0",
             fontsize=pt(28), color=c["muted"])

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, facecolor=c["surface"])
    plt.close(fig)
    return path


def genera_grafici(st: dict, cfg: dict, widget: dict, now: datetime, out: Path) -> list[Path]:
    files = []
    for t in cfg["torrenti"]:
        for tema in TEMI:
            files.append(grafico_torrente(st, cfg, widget, t["chiave"], tema, now,
                                          out / f"{t['chiave']}{SUFFISSO[tema]}.png"))
    return files


# --------------------------------------------------------------------------- index.html

CSS = """
:root{color-scheme:light;--surface:#fcfcfb;--page:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#6f6e69;
--rule:#e1e0d9;--link:#1c5cab}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--surface:#1a1a19;--page:#0d0d0d;--ink:#f0efec;
--ink2:#c3c2b7;--muted:#a3a29b;--rule:#2c2c2a;--link:#86b6ef}}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:16px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:760px;margin:0 auto;padding:16px}
h1{font-size:1.35rem;margin:.2rem 0 .1rem}
h2{font-size:1.05rem;margin:1.6rem 0 .5rem}
p{margin:.3rem 0}
.sub{color:var(--ink2);font-size:.9rem}
.card{background:var(--surface);border:1px solid var(--rule);border-radius:12px;padding:12px 14px;margin:12px 0}
.stato{display:flex;gap:10px;align-items:flex-start;font-weight:600;font-size:1.1rem}
.dot{display:inline-block;width:.8em;height:.8em;border-radius:50%;flex:none;margin-top:.3em}
.inline-dot{display:inline-block;width:.65em;height:.65em;border-radius:50%;margin-right:.35em;vertical-align:baseline}
img{display:block;width:100%;height:auto;border-radius:12px;border:1px solid var(--rule)}
table{border-collapse:collapse;width:100%;font-size:.92rem;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--rule);vertical-align:top}
th{color:var(--ink2);font-weight:600}
.scroll{overflow-x:auto}
details summary{cursor:pointer;color:var(--ink2);margin:.4rem 0}
a{color:var(--link)}
footer{color:var(--muted);font-size:.82rem;margin:2rem 0 1rem}
small{color:var(--ink2);font-size:.8rem}
.nw{white-space:nowrap}
.fig{display:block;margin:14px 0}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
"""


def _e(x) -> str:
    return html.escape(str(x))


def _dot(colore: str, cls: str = "inline-dot") -> str:
    return f'<span class="{cls}" style="background:{_e(colore)}" aria-hidden="true"></span>'


def pagina_index(st: dict, cfg: dict, widget: dict, now: datetime) -> str:
    w = widget
    versione = now.strftime("%Y%m%d%H%M")
    pub = cfg["pubblicazione"]
    base_arpae = cfg["arpae"]["base_url"].rstrip("/")
    righe_t, figure = [], []
    for t in cfg["torrenti"]:
        k = t["chiave"]
        righe_t.append(
            f"<tr><td>{_e(t['nome'])}<br><small>dato {_e(w[f'{k}_ora'])}"
            f"{' · vecchio' if w[f'{k}_vecchio'] else ''}</small></td>"
            f"<td class=\"nw\">{_e(w[f'{k}_livello'].replace('-', '−'))}</td>"
            f"<td class=\"nw\">{_e(w[f'{k}_freccia'])} {_e(w[f'{k}_tendenza'])}<br>"
            f"<small>{_e(w[f'{k}_delta3h'].replace('-', '−'))}</small></td>"
            f"<td class=\"nw\">{_dot(w[f'{k}_colore'])}{_e(w[f'{k}_soglia'])}</td></tr>")
        figure.append(
            f'<h2 class="sr">{_e(t["nome"])}</h2><picture class="fig">'
            f'<source srcset="{k}_dark.png?v={versione}" media="(prefers-color-scheme: dark)">'
            f'<img src="{k}.png?v={versione}" width="1080" height="1330" alt="Grafico {_e(t["nome"])}: livello '
            f'ultime 72 ore con soglie, e pioggia oraria a Lago Pratignano e Lago Scaffaiolo. Valori nelle tabelle.">'
            f'</picture>')
    righe_p = "".join(
        f"<tr><td>{_e(p['nome'])}</td>" + "".join(f"<td>{_e(w[f'{p['chiave']}_{h}h'])}</td>" for h in (1, 6, 24, 72))
        + f"<td>{_e(w[p['chiave'] + '_ora'])}{' · vecchio' if w[p['chiave'] + '_vecchio'] else ''}</td></tr>"
        for p in cfg["pluviometri"])

    # tabella oraria delle ultime 24h: equivalente testuale dei grafici
    colonne = [(f"livello_{t['chiave']}", t.get("nome_breve", t["nome"]) + " (m)") for t in cfg["torrenti"]]
    colonne += [(f"pioggia_{p['chiave']}", p.get("nome_breve", p["nome"]) + " (mm)") for p in cfg["pluviometri"]]
    dati = {nome: {t: v for t, v in serie_da_stato(st.get("serie", {}).get(nome))} for nome, _ in colonne}
    ore = sorted({t for t in dati[colonne[-1][0]]} | {t for t in dati[colonne[0][0]] if t.minute == 0})
    ore = [t for t in ore if t > now - timedelta(hours=24)][::-1]
    righe_o = "".join(
        f"<tr><td>{_e(t.astimezone(ROME).strftime('%d/%m %H:%M'))}</td>"
        + "".join(f"<td>{_e(dati[n].get(t, '–'))}</td>" for n, _ in colonne) + "</tr>" for t in ore)

    link = w.get("allerta_link") or ""
    allerta_link = f' · <a href="{_e(link)}">documento PDF</a>' if link.startswith(("https://", "http://")) else ""
    vecchio = " (non aggiornata)" if w["prev_vecchio"] else ""
    return f"""<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fanano meteo-idro</title>
<meta name="description" content="Livelli di Leo e Panaro, pioggia osservata e prevista a Fanano (dati Arpae)">
<style>{CSS}</style></head>
<body><main>
<h1>Fanano · torrenti e pioggia</h1>
<p class="sub">Aggiornato {_e(w['aggiornato'])} · {_e(pub['disclaimer'])}</p>
<div class="card"><div class="stato">{_dot(w['stato_colore'], 'dot')}<span>{_e(w['stato'])}</span></div>
{f'<p class="sub">{_e(w["stato_dettaglio"])}</p>' if w.get('stato_dettaglio') else ''}
{f'<p class="sub">Fonti non raggiunte in questo aggiornamento: {_e(w["errori"])}</p>' if w.get('errori') else ''}
</div>
{''.join(figure)}
<p class="sub">{_e(w['nota_torrenti'])}.</p>

<h2>Valori</h2>
<div class="card scroll"><table>
<thead><tr><th>Torrente</th><th>Livello</th><th>Tendenza 3h</th><th>Stato</th></tr></thead>
<tbody>{''.join(righe_t)}</tbody></table></div>
<div class="card scroll"><table>
<thead><tr><th>Pioggia (mm)</th><th>1h</th><th>6h</th><th>24h</th><th>72h</th><th>Dato</th></tr></thead>
<tbody>{righe_p}</tbody></table>
<p class="sub">* storico incompleto: valore calcolato sulle ore disponibili.</p></div>
<div class="card">
<p><strong>Previsione</strong> (Arpae, {_e(w['prev_zona'])}){_e(vecchio)}: oggi {_e(w['prev_oggi'])} · domani {_e(w['prev_domani'])}
· dopodomani {_e(w['prev_dopodomani'])} · 3 giorni {_e(w['prev_72h'])}</p>
<p class="sub">{_e(w['prev_testo'])}</p>
<p><strong>Allerta zona {_e(w['allerta_zona'])}</strong>: oggi {_dot(w['allerta_oggi_colore'])}{_e(w['allerta_oggi'])}
{f"({_e(w['allerta_oggi_eventi'])})" if w.get('allerta_oggi_eventi') else ''}
· domani {_dot(w['allerta_domani_colore'])}{_e(w['allerta_domani'])}</p>
<p class="sub">{_e(w['allerta_titolo'])}{allerta_link}</p>
</div>
<details><summary>Dati delle ultime 24 ore (tabella)</summary>
<div class="card scroll"><table>
<thead><tr><th>Ora</th>{''.join(f'<th>{_e(n)}</th>' for _, n in colonne)}</tr></thead>
<tbody>{righe_o}</tbody></table></div></details>

<h2>Link</h2>
<p><a href="{base_arpae}/livello-idrometrico">Mappa livelli idrometrici Arpae</a> ·
<a href="{base_arpae}/web/fanano/home">Allerte per il comune di Fanano</a> ·
<a href="{base_arpae}/previsioni-regionali">Previsioni regionali</a> ·
<a href="widget.json">widget.json</a></p>
<footer>{_e(pub['disclaimer'])}. Fonte: <a href="{base_arpae}/">Allerta Meteo Emilia-Romagna</a>
(Arpae Emilia-Romagna e Agenzia per la sicurezza territoriale e la protezione civile),
licenza <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/">CC BY-NC-SA 4.0</a>.
Elaborazione non ufficiale per uso personale: per decisioni di sicurezza fare riferimento ai canali ufficiali.</footer>
</main></body></html>
"""


def genera_tutto(st: dict, cfg: dict, widget: dict, now: datetime, out: Path) -> list[Path]:
    files = genera_grafici(st, cfg, widget, now, out)
    p = out / "index.html"
    p.write_text(pagina_index(st, cfg, widget, now), encoding="utf-8")
    return files + [p]
