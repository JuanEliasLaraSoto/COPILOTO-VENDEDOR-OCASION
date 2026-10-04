from copiloto import recomendador
from copiloto.coste_anual import Perfil
from copiloto.recomendador import Mensaje, Necesidades, candidatos, puntuar
from copiloto.verificacion import Cita

CLIENTE = "Somos 7 en casa, buscamos algo de hasta 20.000 euros y no tenemos garaje."


def test_filtros(stock):
    n = Necesidades(presupuesto_max=20_000, plazas_min=7)
    assert [v.id for v in candidatos(list(stock.values()), n)] == ["VO-024"]


def test_zona_bajas_emisiones_premia_etiqueta(stock):
    n = Necesidades(zona_bajas_emisiones=True, carga_en_casa=True)
    coches = [stock["VO-008"], stock["VO-005"]]  # diésel C y híbrido ECO
    assert puntuar(coches, n, Perfil())[0]["id"] == "VO-005"


def test_recomendar(llm_falso, stock):
    n = Necesidades(
        presupuesto_max=20_000,
        plazas_min=7,
        carga_en_casa=False,
        citas=[
            Cita(campo="presupuesto_max", texto="hasta 20.000 euros"),
            Cita(campo="plazas_min", texto="Somos 7 en casa"),
            Cita(campo="carga_en_casa", texto="no tenemos garaje"),
        ],
    )
    llm_falso({Necesidades: n, Mensaje: Mensaje(texto="Te propongo la Berlingo de 7 plazas.")})
    r, llamadas = recomendador.recomendar(CLIENTE, list(stock.values()), Perfil())
    assert [c["id"] for c in r["recomendaciones"]] == ["VO-024"]
    assert r["necesidades"]["carga_en_casa"] is False
    assert r["avisos"] == [] and len(llamadas) == 2
