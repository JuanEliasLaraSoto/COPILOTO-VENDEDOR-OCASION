import pytest

from copiloto.financiacion import cuota_mensual, simular


def test_cuota_sistema_frances():
    assert cuota_mensual(16_000, 7.99, 60) == pytest.approx(324.35, abs=0.01)


def test_sin_intereses():
    f = simular(20_000, 4_000, 60, 0)
    assert f.cuota == pytest.approx(266.67, abs=0.01) and f.intereses == 0 and f.tae == 0


def test_la_comision_sube_la_tae():
    sin = simular(20_000, 4_000, 60, 7.99)
    con = simular(20_000, 4_000, 60, 7.99, comision_apertura_pct=2)
    assert sin.tae == pytest.approx(8.29, abs=0.02)  # TAE de un TIN del 7,99 % mensual
    assert con.tae > sin.tae


def test_datos_imposibles():
    with pytest.raises(ValueError):
        simular(10_000, 12_000, 60, 5)
