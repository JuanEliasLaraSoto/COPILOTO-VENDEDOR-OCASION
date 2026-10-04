import pytest
from fastapi.testclient import TestClient

from copiloto import api
from copiloto.anuncio import Anuncio, Destacado
from copiloto.coste_anual import Perfil

cliente = TestClient(api.app)


@pytest.fixture(autouse=True)
def sin_red(monkeypatch, modelo_precio):
    """Modelo de precio de prueba, precios de energía fijos y contador de límite a cero."""
    monkeypatch.setattr(api, "modelo_precio", lambda: modelo_precio)
    monkeypatch.setattr(
        api, "perfil_con_precios_reales", lambda km, casa, prov, manuales=None: Perfil(km, casa)
    )
    api._peticiones.clear()


def test_stock_y_precio():
    assert len(cliente.get("/stock").json()) == 24
    r = cliente.get("/precio/VO-007").json()
    assert r["rango_min"] < r["rango_max"]
    assert cliente.get("/precio/VO-999").status_code == 404


def test_coste_anual():
    r = cliente.post("/coste-anual", json={"ids": ["VO-004", "VO-003"], "km_anuales": 20_000})
    assert r.status_code == 200 and len(r.json()["coches"]) == 2


def test_financiacion():
    r = cliente.post("/financiacion", json={"precio": 20_000, "entrada": 4_000, "meses": 60})
    assert r.json()["cuota"] == pytest.approx(324.35, abs=0.01)
    malo = {"precio": 20_000, "entrada": 25_000}
    assert cliente.post("/financiacion", json=malo).status_code == 422


def test_tasacion_sin_notas_no_usa_el_llm():
    coche = {
        "marca": "seat",
        "modelo": "leon",
        "anio": 2019,
        "km": 90_000,
        "combustible": "gasolina",
        "cambio": "automatico",
    }
    r = cliente.post("/tasacion", json={"coche": coche}).json()
    assert r["puesta_a_punto"] == 0 and r["uso"]["modelos"] == []


def test_anuncio_y_limite(llm_falso, monkeypatch):
    llm_falso(
        {
            Anuncio: Anuncio(
                titulo="Seat León",
                texto_web="Seat León.",
                texto_corto="León.",
                texto_ingles="Seat Leon.",
                destacados=[Destacado(texto="Gasolina", campo="combustible")],
            )
        }
    )
    monkeypatch.setattr(api, "LIMITE_POR_HORA", 2)
    codigos = [cliente.post("/anuncio", json={"id": "VO-007"}).status_code for _ in range(3)]
    assert codigos == [200, 200, 429]


def test_si_la_ia_falla_se_explica(monkeypatch):
    def falla(*a, **k):
        raise api.llm.ErrorLLM("ClientError: 404 modelo no encontrado")

    monkeypatch.setattr(api.llm, "parse", falla)
    r = cliente.post("/anuncio", json={"id": "VO-023"})
    assert r.status_code == 502 and "404 modelo no encontrado" in r.json()["detail"]
