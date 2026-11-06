import copy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fanano import compute, main
from fanano.config import load_config

FIX = Path(__file__).parent / "fixtures"
CONFIG_TEST = Path(__file__).parent / "config_test.yaml"
UTC = timezone.utc
# istante in cui sono state salvate le fixture (06/11/2026 11:42 ora italiana)
NOW = datetime(2026, 11, 6, 10, 42, tzinfo=UTC)


@pytest.fixture(scope="session")
def cfg():
    return load_config(CONFIG_TEST)


@pytest.fixture(scope="session")
def _stato_fixture(cfg):
    raccolta = main.raccogli_da_cartella(FIX, cfg, NOW)
    st, errori = compute.aggiorna_stato(None, raccolta, NOW, cfg)
    assert errori == []
    return st


@pytest.fixture
def stato(_stato_fixture):
    """Stato costruito dalle risposte reali; copia modificabile per ogni test."""
    return copy.deepcopy(_stato_fixture)
