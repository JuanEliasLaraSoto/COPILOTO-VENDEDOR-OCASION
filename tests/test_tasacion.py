from copiloto import tasacion
from copiloto.tasacion import Danos, coste_puesta_a_punto, tasar
from copiloto.vehiculo import CocheCliente
from copiloto.verificacion import Cita

NOTAS = "Neumáticos a 2 mm. Rayón en la aleta y en la puerta. Olor a tabaco. Tlf 612 345 678"


def test_extraer_danos_descarta_lo_inventado(llm_falso):
    falso = llm_falso(
        {
            Danos: Danos(
                neumaticos_cambiar=True,
                piezas_chapa=2,
                limpieza_interior=True,
                itv_caducada=True,  # inventado
                citas=[
                    Cita(campo="neumaticos_cambiar", texto="Neumáticos a 2 mm"),
                    Cita(campo="piezas_chapa", texto="Rayón en la aleta y en la puerta"),
                    Cita(campo="limpieza_interior", texto="olor a tabaco"),
                ],
            )
        }
    )
    d, descartados, _ = tasacion.extraer_danos(NOTAS)
    assert (d.neumaticos_cambiar, d.piezas_chapa, d.limpieza_interior) == (True, 2, True)
    assert d.itv_caducada is None and descartados == ["itv_caducada"]
    assert "612" not in falso.llamadas[0]["contenido"]  # el teléfono no sale del programa


def test_coste_puesta_a_punto():
    total, desglose = coste_puesta_a_punto(Danos(neumaticos_cambiar=True, piezas_chapa=2))
    assert total == 400 + 2 * 250 and len(desglose) == 2


def test_tasar(modelo_precio):
    coche = CocheCliente(
        marca="seat",
        modelo="leon",
        anio=2019,
        km=90_000,
        combustible="gasolina",
        cambio="automatico",
    )
    limpio = tasar(modelo_precio, coche, Danos())
    con_danos = tasar(modelo_precio, coche, Danos(neumaticos_cambiar=True))
    assert limpio["oferta_inicial"] <= limpio["oferta_maxima"] < limpio["precio_venta_estimado"]
    assert con_danos["oferta_maxima"] == limpio["oferta_maxima"] - 400
