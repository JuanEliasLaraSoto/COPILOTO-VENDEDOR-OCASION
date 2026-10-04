"""Tasación del coche que el cliente entrega como parte del pago.

1. El LLM lee las notas del vendedor y saca los daños, cada uno con su cita literal.
2. El código calcula: valor de mercado (ML) − puesta a punto − margen − gastos = oferta.
"""

from pydantic import BaseModel

from copiloto import llm
from copiloto.precio import ModeloPrecio
from copiloto.texto import quitar_datos_personales
from copiloto.valoracion import precio_recomendado
from copiloto.vehiculo import CocheCliente
from copiloto.verificacion import Cita, anular_sin_cita

SYSTEM = """Eres un perito de un concesionario de coches de ocasión en España.
Lees las notas que toma el vendedor al revisar el coche de un cliente y rellenas los daños.
Reglas:
- Solo lo que digan las notas. Lo que no se mencione se queda en null.
- Por cada campo que rellenes, añade una cita copiada literalmente de las notas.
- piezas_chapa: número de piezas de carrocería con golpes, rayones o abolladuras.
- otros: averías o problemas que no encajan en los demás campos, en pocas palabras."""


class Danos(BaseModel):
    neumaticos_cambiar: bool | None = None
    piezas_chapa: int | None = None
    itv_caducada: bool | None = None
    revision_pendiente: bool | None = None
    falta_llave: bool | None = None
    limpieza_interior: bool | None = None  # olores, manchas, tapicería
    otros: list[str] = []
    citas: list[Cita] = []


CAMPOS_DANOS = [
    "neumaticos_cambiar",
    "piezas_chapa",
    "itv_caducada",
    "revision_pendiente",
    "falta_llave",
    "limpieza_interior",
    "otros",
]

# Coste orientativo de poner el coche a punto (€). Cada concesionario pondrá los suyos.
COSTES = {
    "neumaticos_cambiar": 400,
    "piezas_chapa": 250,  # por pieza
    "itv_caducada": 150,  # inspección + pequeñas reparaciones
    "revision_pendiente": 300,
    "falta_llave": 250,
    "limpieza_interior": 150,
    "otros": 300,  # por cada problema, a revisar en taller
}
MARGEN = 0.12  # margen bruto que busca el concesionario sobre el precio de venta
GASTOS_FIJOS = 350  # transferencia, garantía y preparación


def extraer_danos(notas: str, modelo: str = llm.HAIKU):
    """Notas libres del vendedor -> daños verificados. Devuelve (danos, descartados, llamada)."""
    notas = quitar_datos_personales(notas[:3000])
    danos, llamada = llm.parse("danos", modelo, SYSTEM, f"<notas>\n{notas}\n</notas>", Danos)
    datos, descartados = anular_sin_cita(danos, CAMPOS_DANOS, notas)
    datos["otros"] = datos["otros"] or []
    return Danos.model_validate(datos), descartados, llamada


def coste_puesta_a_punto(d: Danos) -> tuple[int, list[str]]:
    """Suma los costes de cada daño. Devuelve (total, desglose legible)."""
    partidas = []
    if d.neumaticos_cambiar:
        partidas.append(("Neumáticos", COSTES["neumaticos_cambiar"]))
    if d.piezas_chapa:
        coste_chapa = d.piezas_chapa * COSTES["piezas_chapa"]
        partidas.append((f"Chapa y pintura ({d.piezas_chapa} piezas)", coste_chapa))
    if d.itv_caducada:
        partidas.append(("Pasar la ITV", COSTES["itv_caducada"]))
    if d.revision_pendiente:
        partidas.append(("Revisión de mantenimiento", COSTES["revision_pendiente"]))
    if d.falta_llave:
        partidas.append(("Segunda llave", COSTES["falta_llave"]))
    if d.limpieza_interior:
        partidas.append(("Limpieza de interior", COSTES["limpieza_interior"]))
    for otro in d.otros:
        partidas.append((f"Revisar: {otro}", COSTES["otros"]))
    total = sum(c for _, c in partidas)
    return total, [f"{nombre}: {coste} €" for nombre, coste in partidas]


def tasar(modelo_precio: ModeloPrecio, v: CocheCliente, d: Danos) -> dict:
    """Oferta al cliente = precio de venta previsto − puesta a punto − margen − gastos.

    Da una horquilla: empezar por la oferta inicial (precio prudente, el bajo del rango)
    y no pasar de la máxima (precio central).
    """
    val = precio_recomendado(modelo_precio, v)
    coste, desglose = coste_puesta_a_punto(d)

    def oferta(precio_venta: float) -> int:
        return max(0, round((precio_venta * (1 - MARGEN) - coste - GASTOS_FIJOS) / 50) * 50)

    return {
        "precio_venta_estimado": val["precio_estimado"],
        "rango_mercado": [val["rango_min"], val["rango_max"]],
        "puesta_a_punto": coste,
        "desglose": desglose,
        "margen_pct": MARGEN * 100,
        "gastos_fijos": GASTOS_FIJOS,
        "oferta_inicial": oferta(val["rango_min"]),
        "oferta_maxima": oferta(val["precio_estimado"]),
    }
