import pytest

from copiloto.coste_anual import (
    CosteAnual,
    Perfil,
    anios_para_compensar,
    comparar,
    coste_anual,
    coste_energia,
)


def test_electrico_gasta_menos_en_energia_que_gasolina(stock):
    perfil = Perfil(km_anuales=15_000, carga_en_casa=True)
    electrico = coste_energia(stock["VO-004"], perfil)[0]
    gasolina = coste_energia(stock["VO-003"], perfil)[0]
    assert electrico < gasolina / 2


def test_cuenta_de_energia_gasolina(stock):
    perfil = Perfil(km_anuales=10_000, precio_gasolina=1.50)
    euros, _ = coste_energia(stock["VO-001"], perfil)  # 6,1 L/100 km WLTP
    assert euros == pytest.approx(10_000 / 100 * 6.1 * 1.15 * 1.50)


def test_sin_garaje_el_electrico_sale_mas_caro(stock):
    con = coste_anual(stock["VO-004"], Perfil(carga_en_casa=True)).energia
    sin = coste_anual(stock["VO-004"], Perfil(carga_en_casa=False)).energia
    assert sin > 2 * con


def test_anios_para_compensar():
    caro = CosteAnual("a", "A", "electrico", 30_000, 400, 250, 500, 30)
    barato = CosteAnual("b", "B", "gasolina", 24_000, 1_400, 450, 500, 110)
    assert anios_para_compensar(caro, barato) == pytest.approx(6000 / (2460 - 1180), abs=0.05)
    assert anios_para_compensar(barato, caro) is None  # el barato de comprar gasta más


def test_comparar_ordena_por_coste_anual(stock):
    r = comparar([stock["VO-001"], stock["VO-004"], stock["VO-005"]], Perfil())
    totales = [c["total_anual"] for c in r["coches"]]
    assert totales == sorted(totales)
    assert r["referencia"] == stock["VO-005"].nombre()  # el más barato de comprar


def test_precios_escritos_por_el_vendedor_mandan(monkeypatch):
    from copiloto import carburantes, electricidad
    from copiloto.coste_anual import perfil_con_precios_reales

    monkeypatch.setattr(carburantes, "precio_actual", lambda prov, comb: (1.55, "respaldo"))
    monkeypatch.setattr(electricidad, "precio_kwh_casa", lambda: (0.13, "api"))
    p = perfil_con_precios_reales(15_000, True, "Malaga", {"precio_gasolina": 1.99})
    assert (p.precio_gasolina, p.precio_diesel, p.precio_kwh_casa) == (1.99, 1.55, 0.13)
    assert p.origen["precio_gasolina"] == "escrito por el vendedor"
    assert "RESERVA" in p.origen["precio_diesel"]
    assert "hoy" in p.origen["precio_kwh_casa"]
