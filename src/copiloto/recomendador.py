"""Recomendador de stock: el cliente cuenta lo que necesita y se eligen los 3 mejores coches.

1. LLM: lo que dice el cliente -> necesidades estructuradas (con citas verificadas).
2. Código: filtra el stock y puntúa cada coche con reglas explicables.
3. LLM: redacta el mensaje para el cliente, y el código revisa que no invente cifras.
"""

import json
from typing import Literal

from pydantic import BaseModel

from copiloto import llm
from copiloto.coste_anual import Perfil, coste_anual
from copiloto.texto import cifras, cifras_sin_respaldo, quitar_datos_personales
from copiloto.vehiculo import Cambio, Vehiculo
from copiloto.verificacion import Cita, anular_sin_cita

SYSTEM_NECESIDADES = """Eres el asistente de un vendedor de coches de ocasión en España.
Lees lo que cuenta un cliente y rellenas sus necesidades.
Reglas:
- Solo lo que diga el cliente. Lo que no diga se queda en null.
- Por cada campo que rellenes, añade una cita copiada literalmente del texto del cliente.
- presupuesto_max y km_anuales en números enteros (25.000 € -> 25000; «20 mil km» -> 20000).
- uso: «ciudad», «carretera» o «mixto».
- carroceria: compacto, berlina, familiar, suv o monovolumen, solo si la pide."""

SYSTEM_MENSAJE = """Eres un vendedor de coches de ocasión en España.
Recibes en JSON las necesidades de un cliente y los coches recomendados con sus razones.
Escribe un mensaje breve para el cliente (máximo 8 frases) presentando las opciones.
Usa SOLO las cifras del JSON. No inventes datos. Tono cercano y claro, sin tecnicismos."""


class Necesidades(BaseModel):
    presupuesto_max: int | None = None
    km_anuales: int | None = None
    uso: Literal["ciudad", "carretera", "mixto"] | None = None
    plazas_min: int | None = None
    cambio: Cambio | None = None
    carga_en_casa: bool | None = None
    zona_bajas_emisiones: bool | None = None
    carroceria: str | None = None
    citas: list[Cita] = []


CAMPOS_NECESIDADES = [c for c in Necesidades.model_fields if c != "citas"]


class Mensaje(BaseModel):
    texto: str


def extraer_necesidades(texto: str, modelo: str = llm.HAIKU):
    texto = quitar_datos_personales(texto[:3000])
    n, llamada = llm.parse("necesidades", modelo, SYSTEM_NECESIDADES, texto, Necesidades)
    datos, descartados = anular_sin_cita(n, CAMPOS_NECESIDADES, texto)
    return Necesidades.model_validate(datos), descartados, llamada


def candidatos(stock: list[Vehiculo], n: Necesidades) -> list[Vehiculo]:
    """Filtros duros: lo que el cliente no aceptaría nunca."""
    lista = []
    for v in stock:
        if n.presupuesto_max and v.precio > n.presupuesto_max * 1.05:  # 5 % de margen
            continue
        if n.plazas_min and v.plazas < n.plazas_min:
            continue
        if n.cambio and v.cambio != n.cambio:
            continue
        if n.carroceria and v.carroceria and v.carroceria != n.carroceria.lower():
            continue
        lista.append(v)
    return lista


def puntuar(candidatos: list[Vehiculo], n: Necesidades, perfil: Perfil) -> list[dict]:
    """Puntos por reglas sencillas. Cada punto lleva su razón, para poder explicarlo."""
    costes = {v.id: coste_anual(v, perfil).total for v in candidatos}
    if not costes:
        return []
    barato, caro = min(costes.values()), max(costes.values())
    resultado = []
    for v in candidatos:
        puntos, razones = 0.0, []
        coste = costes[v.id]
        # Coste anual: hasta 3 puntos al más barato de mantener.
        puntos += 3 * (caro - coste) / (caro - barato) if caro > barato else 1.5
        razones.append(f"Coste estimado de uso: {coste:,.0f} € al año".replace(",", "."))
        if n.presupuesto_max and v.precio <= n.presupuesto_max:
            puntos += 2
            razones.append("Dentro del presupuesto")
        elif n.presupuesto_max:
            razones.append("Ligeramente por encima del presupuesto")
        if n.zona_bajas_emisiones:
            extra = {"0": 2, "ECO": 1.5, "C": 0}.get(v.etiqueta_dgt, -2)
            puntos += extra
            if extra > 0:
                razones.append(f"Etiqueta {v.etiqueta_dgt}: entra en zonas de bajas emisiones")
        if v.combustible == "electrico" and n.carga_en_casa is False:
            puntos -= 2
            razones.append("Ojo: sin cargador en casa, cargar en la calle sale más caro")
        autonomia = v.autonomia_electrica_km or 0
        if n.uso == "carretera" and v.combustible == "electrico" and autonomia < 350:
            puntos -= 1
            razones.append(f"Autonomía de {v.autonomia_electrica_km} km: justa para viajes largos")
        if n.uso == "ciudad" and v.combustible in ("electrico", "hibrido", "hibrido_enchufable"):
            puntos += 1
            razones.append("Motor eficiente en ciudad")
        if n.uso == "carretera" and v.combustible in ("diesel", "hibrido"):
            puntos += 1
            razones.append("Motor que gasta poco en carretera")
        puntos += max(0, (v.anio - 2015)) / 10  # algo más nuevo, algo mejor
        resultado.append(
            {
                "id": v.id,
                "nombre": v.nombre(),
                "anio": v.anio,
                "km": v.km,
                "precio": v.precio,
                "combustible": v.combustible,
                "etiqueta_dgt": v.etiqueta_dgt,
                "coste_anual": round(coste),
                "puntos": round(puntos, 2),
                "razones": razones,
            }
        )
    return sorted(resultado, key=lambda r: r["puntos"], reverse=True)


def recomendar(texto_cliente: str, stock: list[Vehiculo], perfil_base: Perfil, top: int = 3):
    """Devuelve (resultado, llamadas)."""
    n, descartados, ll1 = extraer_necesidades(texto_cliente)
    perfil = Perfil(
        km_anuales=n.km_anuales or perfil_base.km_anuales,
        carga_en_casa=n.carga_en_casa if n.carga_en_casa is not None else False,
        precio_gasolina=perfil_base.precio_gasolina,
        precio_diesel=perfil_base.precio_diesel,
        precio_kwh_casa=perfil_base.precio_kwh_casa,
        precio_kwh_publico=perfil_base.precio_kwh_publico,
    )
    elegidos = puntuar(candidatos(stock, n), n, perfil)[:top]
    resultado = {
        "necesidades": n.model_dump(exclude={"citas"}),
        "datos_descartados_sin_cita": descartados,
        "recomendaciones": elegidos,
        "mensaje_cliente": None,
        "avisos": [],
    }
    if not elegidos:
        return resultado, [ll1]

    datos = {"necesidades": resultado["necesidades"], "coches": elegidos}
    m, ll2 = llm.parse(
        "mensaje_recomendacion",
        llm.HAIKU,
        SYSTEM_MENSAJE,
        json.dumps(datos, ensure_ascii=False),
        Mensaje,
    )
    permitidas = cifras(json.dumps(datos, ensure_ascii=False)) | cifras(texto_cliente)
    resultado["mensaje_cliente"] = m.texto
    resultado["avisos"] = [
        f"La cifra {c:g} no está en los datos" for c in cifras_sin_respaldo(m.texto, permitidas)
    ]
    return resultado, [ll1, ll2]
