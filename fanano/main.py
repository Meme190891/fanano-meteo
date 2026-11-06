"""Esecuzione completa: raccolta dati Arpae -> stato aggiornato -> widget.json.

    python -m fanano.main --out out/                     # online, una richiesta per endpoint
    python -m fanano.main --out out/ --da-cartella DIR   # offline, da risposte salvate (stessi nomi di --save)

Lo stato precedente viene letto da --stato (default: <out>/state.json) e riscritto aggiornato:
se una fonte fallisce si conserva il suo ultimo dato valido (vedi compute.aggiorna_stato).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests

from fanano import arpae, compute
from fanano.config import load_config

UTC = timezone.utc


def interpreta(nome: str, contenuto: bytes, cfg: dict, now: datetime):
    """Contenuto grezzo di un endpoint -> valore parsato. Solleva eccezione se inutilizzabile."""
    if nome == "previsione":
        return arpae.parse_previsione(contenuto.decode("utf-8", errors="replace"), cfg["previsione"]["zona"],
                                      oggi=now.astimezone(arpae.ROME).date())
    data = json.loads(contenuto)
    if nome == "livelli":
        ids = {t["id"] for t in cfg["torrenti"]}
        out = arpae.parse_livelli(data, ids)
        if not out:
            raise ValueError("nessuna stazione configurata nella risposta")
        return out
    if nome.startswith(("livello_", "pioggia_")):
        serie = arpae.parse_serie(data)
        if not serie:
            raise ValueError("serie vuota")
        return serie
    if nome.startswith("allerta_"):
        return arpae.parse_allerta(data, cfg["zona_allerta"], cfg["arpae"]["base_url"])
    raise KeyError(nome)


def raccogli_online(cfg: dict, now: datetime) -> dict:
    """Una richiesta per endpoint; ogni fonte e' indipendente (un errore non blocca le altre)."""
    session = arpae.make_session(cfg)
    timeout = cfg["arpae"].get("timeout_s", 20)
    raccolta = {}
    for nome, url in arpae.endpoint_urls(cfg, now).items():
        try:
            resp = arpae.fetch(session, url, timeout=timeout)
            raccolta[nome] = interpreta(nome, resp.content, cfg, now)
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            raccolta[nome] = exc
    return raccolta


def raccogli_da_cartella(cartella: Path, cfg: dict, now: datetime) -> dict:
    """Come raccogli_online ma dai file salvati con `python -m fanano.arpae --save`. File mancante = errore."""
    raccolta = {}
    for nome in arpae.endpoint_urls(cfg, now):
        f = cartella / (f"{nome}.html" if nome == "previsione" else f"{nome}.json")
        try:
            raccolta[nome] = interpreta(nome, f.read_bytes(), cfg, now)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raccolta[nome] = exc
    return raccolta


def leggi_stato(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def scrivi_json(path: Path, obj) -> None:
    """Scrittura atomica: il file finale e' sempre un JSON completo."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def esegui(cfg: dict, out: Path, stato_path: Path, raccolta: dict, now: datetime, grafici: bool = True) -> dict:
    stato, errori = compute.aggiorna_stato(leggi_stato(stato_path), raccolta, now, cfg)
    widget = compute.costruisci_widget(stato, cfg, now, errori)
    if grafici:
        try:
            from fanano import render
            render.genera_tutto(stato, cfg, widget, now, out)
        except Exception as exc:  # noqa: BLE001 - un grafico rotto non deve bloccare widget.json
            widget["errori"] = "; ".join(x for x in (widget["errori"], f"grafici: {type(exc).__name__}: {exc}") if x)
    scrivi_json(out / "state.json", stato)
    scrivi_json(out / "widget.json", widget)
    return widget


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("out"), help="cartella di output (default: out/)")
    ap.add_argument("--stato", type=Path, help="state.json precedente (default: <out>/state.json)")
    ap.add_argument("--da-cartella", type=Path, help="usa risposte salvate invece della rete")
    ap.add_argument("--now", help="istante ISO da usare come 'adesso' (solo per prove offline)")
    ap.add_argument("--config", type=Path, help="config.yaml alternativo")
    ap.add_argument("--senza-grafici", action="store_true", help="non generare PNG e index.html")
    args = ap.parse_args(argv)

    cfg = load_config(args.config) if args.config else load_config()
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    raccolta = (raccogli_da_cartella(args.da_cartella, cfg, now) if args.da_cartella
                else raccogli_online(cfg, now))
    widget = esegui(cfg, args.out, args.stato or args.out / "state.json", raccolta, now,
                    grafici=not args.senza_grafici)
    print(json.dumps(widget, ensure_ascii=False, indent=1))
    if widget["errori"]:
        print(f"\nFonti fallite (mantenuto l'ultimo dato valido): {widget['errori']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
