"""Anuncio automático a partir de la ficha, sin inventar nada.

El LLM escribe; el código comprueba cada cifra, cada promesa y cada punto destacado.
"""

import json

from pydantic import BaseModel

from copiloto import llm
from copiloto.texto import cifras_sin_respaldo, normalizar
from copiloto.vehiculo import Vehiculo
from copiloto.verificacion import promesas_sin_respaldo, revisar_texto

SYSTEM = """Eres el redactor de anuncios de un concesionario de coches de ocasión en España.
Recibes la ficha de un coche en JSON y escribes su anuncio.
Reglas:
- Usa SOLO datos de la ficha. No calcules cifras nuevas (ni edad del coche, ni ahorros).
- No prometas nada que no esté en la ficha: garantía, libro de revisiones, propietarios, ITV.
- Si las notas mencionan un defecto, cuéntalo con naturalidad: la transparencia da confianza.
- texto_corto: máximo 300 caracteres, para portales de anuncios.
- texto_ingles: el mismo anuncio en inglés.
- destacados: de 3 a 6 puntos fuertes. En cada uno, «campo» es el nombre exacto del campo
  de la ficha del que sale y, si sale de «extras» o de «notas», «cita» es el texto copiado
  literalmente de ahí.
- Tono profesional y cercano. Sin exclamaciones ni mayúsculas para llamar la atención."""


class Destacado(BaseModel):
    texto: str
    campo: str
    cita: str = ""


class Anuncio(BaseModel):
    titulo: str
    texto_web: str
    texto_corto: str
    texto_ingles: str
    destacados: list[Destacado]


def destacado_valido(d: Destacado, v: Vehiculo) -> bool:
    """Un destacado vale si su campo tiene dato en la ficha (y su cita existe, si la necesita)
    y si no hace una promesa que la ficha no respalda («Un solo dueño» con 2 propietarios)."""
    if promesas_sin_respaldo(d.texto, v):
        return False
    if d.campo == "notas":
        return bool(d.cita.strip()) and normalizar(d.cita) in normalizar(v.notas)
    if d.campo == "extras":
        return any(normalizar(d.cita) in normalizar(e) for e in v.extras if d.cita.strip())
    if d.campo not in Vehiculo.model_fields or d.campo == "dias_en_stock":
        return False
    return getattr(v, d.campo) not in (None, "", [], False)


def verificar_anuncio(a: Anuncio, v: Vehiculo) -> dict:
    avisos = {
        "titulo": revisar_texto(a.titulo, v),
        "texto_web": revisar_texto(a.texto_web, v),
        "texto_corto": revisar_texto(a.texto_corto, v),
        # En inglés solo se comprueban las cifras (las palabras clave están en español).
        "texto_ingles": [
            f"La cifra {c:g} no aparece en la ficha"
            for c in cifras_sin_respaldo(a.texto_ingles, v.cifras_de_la_ficha())
        ],
    }
    if len(a.texto_corto) > 300:
        avisos["texto_corto"].append(f"Tiene {len(a.texto_corto)} caracteres (máximo 300)")
    validos = [d for d in a.destacados if destacado_valido(d, v)]
    descartados = [d.texto for d in a.destacados if not destacado_valido(d, v)]
    return {
        "anuncio": {**a.model_dump(), "destacados": [d.texto for d in validos]},
        "avisos": {k: x for k, x in avisos.items() if x},
        "destacados_descartados": descartados,
        "listo_para_publicar": not any(avisos.values()),
    }


def generar_anuncio(v: Vehiculo, modelo: str = llm.HAIKU) -> tuple[dict, llm.Llamada]:
    ficha = json.dumps(v.para_el_llm(), ensure_ascii=False)
    anuncio, llamada = llm.parse(
        "anuncio", modelo, SYSTEM, f"<ficha>\n{ficha}\n</ficha>", Anuncio, max_tokens=2500
    )
    return verificar_anuncio(anuncio, v), llamada
