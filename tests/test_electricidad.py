import httpx

from copiloto import electricidad

RESPUESTA_REE = {
    "included": [
        {"attributes": {"title": "Precio mercado spot", "values": [{"value": 50.0}]}},
        {
            "attributes": {
                "title": "PVPC",
                "values": [{"value": 100.0}, {"value": 140.0}, {"value": 180.0}],
            }
        },
    ]
}


def test_pvpc_medio_en_euros_por_kwh():
    assert electricidad.pvpc_medio(RESPUESTA_REE) == 0.14  # mediana 140 €/MWh


def test_respaldo_si_falla_la_api(monkeypatch):
    def falla(dia):
        raise httpx.ConnectError("sin red")

    monkeypatch.setattr(electricidad, "descargar_precios", falla)
    electricidad._CACHE.clear()
    assert electricidad.precio_kwh_casa() == (electricidad.PRECIO_CASA_RESPALDO, "respaldo")
