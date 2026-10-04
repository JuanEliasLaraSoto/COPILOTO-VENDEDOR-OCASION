from pydantic import BaseModel

from copiloto.verificacion import Cita, anular_sin_cita, promesas_sin_respaldo, revisar_texto


class Danos(BaseModel):  # un esquema pequeño solo para el test
    neumaticos_cambiar: bool | None = None
    piezas_chapa: int | None = None
    falta_llave: bool | None = None
    citas: list[Cita] = []


def test_anular_sin_cita():
    d = Danos(
        neumaticos_cambiar=True,
        piezas_chapa=2,
        falta_llave=False,  # inventado: no hay cita
        citas=[
            Cita(campo="neumaticos_cambiar", texto="ruedas a 2 mm"),
            Cita(campo="piezas_chapa", texto="arañazo que no está en las notas"),
        ],
    )
    datos, descartados = anular_sin_cita(
        d, ["neumaticos_cambiar", "piezas_chapa", "falta_llave"], "Ruedas a 2 mm, olor a tabaco"
    )
    assert datos["neumaticos_cambiar"] is True
    assert datos["piezas_chapa"] is None and datos["falta_llave"] is None
    assert sorted(descartados) == ["falta_llave", "piezas_chapa"]


def test_promesas(stock):
    leon = stock["VO-008"]  # sin libro de revisiones, 2 propietarios, 12 meses de garantía
    assert promesas_sin_respaldo("Con 12 meses de garantía.", leon) == []
    assert promesas_sin_respaldo("Se entrega sin libro de revisiones.", leon) == []
    assert promesas_sin_respaldo("Con libro de revisiones al día.", leon)
    assert promesas_sin_respaldo("Único propietario.", leon)


def test_revisar_texto_pilla_cifras_inventadas(stock):
    avisos = revisar_texto(
        "Seat León de 2018 con 118.000 km. Consumo de 3,9 L/100 km.", stock["VO-008"]
    )
    assert avisos == ["La cifra 3.9 no aparece en la ficha"]
