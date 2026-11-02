"""Los datos sintéticos del seed no pueden salir por la API en AWS.

El 2026-11-02 se comprobó contra producción que los 72 avisos de ejemplo
(descripción: "Aviso de ejemplo (dato sintético)...") se servían por la API
pública mezclados con los 4817 reales, y que además entraban en el cálculo de
las medianas de mercado. Estos tests fijan las dos mitades del arreglo.
"""

from __future__ import annotations

import pytest

from app.repositories.memory.seed import seed_all
from app.repositories.memory.store import InMemoryStore


@pytest.fixture
def store_limpio(monkeypatch: pytest.MonkeyPatch) -> InMemoryStore:
    """seed_all es idempotente contra el store global ya sembrado por el
    import de app.api.deps, así que se le pone uno vacío delante."""
    nuevo = InMemoryStore()
    monkeypatch.setattr("app.repositories.memory.seed.store", nuevo)
    return nuevo


def test_modo_aws_no_siembra_avisos_ni_historico(store_limpio: InMemoryStore) -> None:
    seed_all(datos_sinteticos=False)
    assert store_limpio.listings == {}
    assert store_limpio.market_history_seed == []


def test_modo_aws_igual_siembra_zonas_y_catalogos(store_limpio: InMemoryStore) -> None:
    # Las zonas son el fallback de GoldZonesRepository y los catálogos no
    # tienen otra fuente: sin ellos la API responde 500, no "sin datos".
    seed_all(datos_sinteticos=False)
    assert store_limpio.zones
    assert store_limpio.amenities
    assert store_limpio.garantias


def test_modo_local_sigue_sembrando(store_limpio: InMemoryStore) -> None:
    seed_all()
    assert store_limpio.listings
    assert store_limpio.market_history_seed
