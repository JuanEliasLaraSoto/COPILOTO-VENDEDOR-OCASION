"""Respuestas a los mensajes de los clientes, solo con lo que dice la ficha.

Si el cliente pregunta algo que la ficha no sabe, la respuesta no se lo inventa:
dice que lo consulta y le apunta al vendedor qué tiene que averiguar.
"""

import json

from pydantic import BaseModel

from copiloto import llm
from copiloto.texto import cifras, quitar_datos_personales
from copiloto.vehiculo import Vehiculo
from copiloto.verificacion import revisar_texto

SYSTEM = """Eres el asistente de un vendedor de coches de ocasión en España.
Recibes la ficha de un coche y el mensaje de un cliente interesado. Redactas la respuesta.
Reglas:
- Usa SOLO datos de la ficha. Si el cliente pregunta algo que no está en la ficha,
  no lo supongas: di que lo consultas y añádelo a «pendiente» (en pocas palabras).
- No ofrezcas descuentos, financiación concreta ni reservas: eso lo decide el vendedor.
- Si la ficha menciona un defecto relacionado con la pregunta, dilo con honestidad.
- campos_usados: nombres exactos de los campos de la ficha que has usado.
- Respuesta breve (máximo 6 frases), cercana y profesional, en español, sin firma."""

MAX_MENSAJE = 2000


class Respuesta(BaseModel):
    texto: str
    campos_usados: list[str]
    pendiente: list[str]


def elegir_modelo(mensaje: str) -> str:
    """Router: mensajes largos o con muchas preguntas van al modelo potente."""
    if len(mensaje) > 500 or mensaje.count("?") >= 3:
        return llm.SONNET
    return llm.HAIKU


def responder(v: Vehiculo, mensaje: str, modelo: str | None = None):
    """Devuelve (resultado verificado, llamada)."""
    mensaje = quitar_datos_personales(mensaje[:MAX_MENSAJE])
    modelo = modelo or elegir_modelo(mensaje)
    ficha = json.dumps(v.para_el_llm(), ensure_ascii=False)
    contenido = f"<ficha>\n{ficha}\n</ficha>\n<mensaje_cliente>\n{mensaje}\n</mensaje_cliente>"
    r, llamada = llm.parse("respuesta", modelo, SYSTEM, contenido, Respuesta)
    campos = [c for c in r.campos_usados if c in Vehiculo.model_fields and c != "dias_en_stock"]
    avisos = revisar_texto(r.texto, v, otras_cifras=cifras(mensaje))  # puede repetir sus cifras
    return {
        "respuesta": r.texto,
        "campos_usados": campos,
        "pendiente_de_consultar": r.pendiente,
        "avisos": avisos,
        "listo_para_enviar": not avisos,
    }, llamada
