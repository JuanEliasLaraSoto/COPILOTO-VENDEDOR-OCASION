"""Acceso al LLM: cliente, modelos, coste por llamada y registro (logs).

Funciona con dos proveedores. Se elige en el archivo .env:
    PROVEEDOR=claude   (por defecto)  -> necesita ANTHROPIC_API_KEY
    PROVEEDOR=gemini                  -> necesita GEMINI_API_KEY (plan gratuito de Google)
El resto del proyecto no sabe cuál se usa: siempre llama a parse().
"""

import base64
import json
import logging
import os
import time
from dataclasses import asdict, dataclass

from dotenv import load_dotenv

load_dotenv()  # lee las claves y el PROVEEDOR del archivo .env

PROVEEDOR = os.getenv("PROVEEDOR", "claude").strip().lower()

# El resto del código pide «el modelo rápido» (HAIKU) o «el modelo listo» (SONNET).
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-5-5"

# Con Gemini, cada papel se cumple con un modelo de Google. Se pueden cambiar en el .env.
GEMINI = {
    HAIKU: os.getenv("GEMINI_MODELO_RAPIDO", "gemini-3.5-flash-lite"),
    SONNET: os.getenv("GEMINI_MODELO_LISTO", "gemini-3.8-flash"),
}

# Dólares por millón de tokens (entrada, salida). Revisa la página de precios de Claude.
# Los modelos de Gemini no aparecen: en el plan gratuito cuestan 0.
PRECIOS = {HAIKU: (1.0, 5.0), SONNET: (2.0, 10.0)}

log = logging.getLogger("copiloto.llm")
_cliente = None
_cliente_gemini = None


def cliente():
    """Cliente de Claude (se crea la primera vez que se usa)."""
    global _cliente
    if _cliente is None:
        from anthropic import Anthropic

        _cliente = Anthropic()  # usa la variable de entorno ANTHROPIC_API_KEY
    return _cliente


def cliente_gemini():
    """Cliente de Gemini (se crea la primera vez que se usa)."""
    global _cliente_gemini
    if _cliente_gemini is None:
        from google import genai

        _cliente_gemini = genai.Client()  # usa la variable de entorno GEMINI_API_KEY
    return _cliente_gemini


class ErrorLLM(Exception):
    """La IA no ha respondido bien (clave, límite, modelo, respuesta cortada...)."""


@dataclass
class Llamada:
    tarea: str
    modelo: str
    tokens_entrada: int
    tokens_salida: int
    segundos: float

    @property
    def coste_usd(self) -> float:
        pe, ps = PRECIOS.get(self.modelo, (0.0, 0.0))
        return (self.tokens_entrada * pe + self.tokens_salida * ps) / 1_000_000

    def resumen(self) -> dict:
        """Lo que se enseña en la web: modelo, segundos y coste."""
        return {"modelo": self.modelo, "segundos": self.segundos, "coste_usd": self.coste_usd}


def _contenido_gemini(contenido: list | str) -> list | str:
    """Traduce el contenido del formato de Claude al de Gemini (texto e imágenes)."""
    if isinstance(contenido, str):
        return contenido
    from google.genai import types

    partes = []
    for bloque in contenido:
        if bloque["type"] == "text":
            partes.append(types.Part.from_text(text=bloque["text"]))
        elif bloque["type"] == "image":
            fuente = bloque["source"]
            datos = base64.standard_b64decode(fuente["data"])
            partes.append(types.Part.from_bytes(data=datos, mime_type=fuente["media_type"]))
    return partes


def _parse_claude(modelo, system, contenido, formato, max_tokens):
    respuesta = cliente().messages.parse(
        model=modelo,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": contenido}],
        output_format=formato,
    )
    uso = respuesta.usage
    return respuesta.parsed_output, modelo, uso.input_tokens, uso.output_tokens


def _parse_gemini(modelo, system, contenido, formato, max_tokens):
    from google.genai import types

    nombre = GEMINI[modelo]
    respuesta = cliente_gemini().models.generate_content(
        model=nombre,
        contents=_contenido_gemini(contenido),
        config=types.GenerateContentConfig(
            system_instruction=system,
            # Los modelos Gemini «piensan» antes de responder y ese razonamiento gasta del
            # mismo límite de tokens: damos margen para que la respuesta no salga cortada.
            max_output_tokens=max_tokens + 6000,
            response_mime_type="application/json",  # que responda solo JSON...
            response_schema=formato,  # ...con la forma exacta de nuestro modelo Pydantic
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )
    if not respuesta.text:
        motivo = respuesta.candidates[0].finish_reason if respuesta.candidates else "desconocido"
        raise ErrorLLM(f"Gemini no ha devuelto texto (motivo: {motivo}).")
    # Validamos nosotros con Pydantic: si el JSON no encaja, salta un error claro.
    objeto = formato.model_validate_json(respuesta.text)
    uso = respuesta.usage_metadata
    salida = (uso.candidates_token_count or 0) + (uso.thoughts_token_count or 0)
    return objeto, nombre, uso.prompt_token_count or 0, salida


def parse(
    tarea: str, modelo: str, system: str, contenido: list | str, formato, max_tokens: int = 2000
):
    """Llama al modelo pidiendo una salida que cumpla el esquema `formato` (Pydantic).

    `modelo` es HAIKU (rápido) o SONNET (listo); con Gemini se traduce a su equivalente.
    Devuelve (objeto validado, Llamada con tokens, coste y tiempo).
    """
    inicio = time.perf_counter()
    llamar = _parse_gemini if PROVEEDOR == "gemini" else _parse_claude
    try:
        objeto, nombre, entrada, salida = llamar(modelo, system, contenido, formato, max_tokens)
    except ErrorLLM:
        raise
    except Exception as e:  # clave mal, sin saldo, límite por minuto, modelo que no existe...
        log.exception("Fallo al llamar a la IA")
        raise ErrorLLM(f"{type(e).__name__}: {str(e)[:300]}") from e
    llamada = Llamada(tarea, nombre, entrada, salida, round(time.perf_counter() - inicio, 2))
    log.info(json.dumps({**asdict(llamada), "coste_usd": round(llamada.coste_usd, 6)}))
    return objeto, llamada
