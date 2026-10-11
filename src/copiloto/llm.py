"""Acceso al LLM: cliente, modelos, coste por llamada y registro (logs).

Funciona con dos proveedores. Se elige en el archivo .env:
    PROVEEDOR=claude   (por defecto)  -> necesita ANTHROPIC_API_KEY
    PROVEEDOR=gemini                  -> necesita GEMINI_API_KEY (plan gratuito de Google)
El resto del proyecto no sabe cuál se usa: siempre llama a parse().

Gestión de tokens, latencia y coste (también en el .env):
    PRESUPUESTO_DIARIO_USD=1.0   tope de gasto al día; al llegar, no se llama más (0 = sin tope)
    LLM_TIMEOUT_S=30             segundos máximos por llamada antes de darla por fallida
    LLM_REINTENTOS=2             reintentos ante errores pasajeros (límite por minuto, 5xx)
Cada llamada queda registrada y estadisticas() da el resumen (lo sirve GET /uso-ia).
"""

import base64
import json
import logging
import os
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import date

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

PRESUPUESTO_DIARIO_USD = float(os.getenv("PRESUPUESTO_DIARIO_USD", "0") or 0)
TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "30"))
REINTENTOS = int(os.getenv("LLM_REINTENTOS", "2"))

log = logging.getLogger("copiloto.llm")
_cliente = None
_cliente_gemini = None

# Registro en memoria: últimas llamadas, errores y gasto del día (se reinicia al cambiar de día).
_historial: deque = deque(maxlen=1000)
_errores: dict[str, int] = {}
_gasto = {"dia": date.today(), "usd": 0.0}
_cerrojo = threading.Lock()


def cliente():
    """Cliente de Claude (se crea la primera vez que se usa)."""
    global _cliente
    if _cliente is None:
        from anthropic import Anthropic

        # usa la variable de entorno ANTHROPIC_API_KEY
        _cliente = Anthropic(timeout=TIMEOUT_S, max_retries=REINTENTOS)
    return _cliente


def cliente_gemini():
    """Cliente de Gemini (se crea la primera vez que se usa)."""
    global _cliente_gemini
    if _cliente_gemini is None:
        from google import genai
        from google.genai import types

        opciones = types.HttpOptions(
            timeout=int(TIMEOUT_S * 1000),  # en milisegundos
            retry_options=types.HttpRetryOptions(attempts=REINTENTOS + 1),
        )
        _cliente_gemini = genai.Client(http_options=opciones)  # usa GEMINI_API_KEY
    return _cliente_gemini


class ErrorLLM(Exception):
    """La IA no ha respondido bien (clave, límite, modelo, respuesta cortada...)."""


class PresupuestoAgotado(ErrorLLM):
    """Se ha llegado a PRESUPUESTO_DIARIO_USD: no se hacen más llamadas hasta mañana."""


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


def gasto_hoy() -> float:
    """Dólares gastados hoy en llamadas a la IA."""
    with _cerrojo:
        if _gasto["dia"] != date.today():
            _gasto.update(dia=date.today(), usd=0.0)
        return _gasto["usd"]


def _registrar(llamada: "Llamada") -> None:
    gasto_hoy()  # por si ha cambiado el día
    with _cerrojo:
        _historial.append(llamada)
        _gasto["usd"] += llamada.coste_usd


def _percentil(valores: list[float], p: float) -> float:
    orden = sorted(valores)
    return orden[min(len(orden) - 1, int(p * len(orden)))]


def estadisticas() -> dict:
    """Tokens, latencia (media y p95) y coste de las últimas llamadas, por tarea y modelo."""
    with _cerrojo:
        llamadas, errores = list(_historial), dict(_errores)
    grupos: dict[tuple[str, str], list[Llamada]] = {}
    for ll in llamadas:
        grupos.setdefault((ll.tarea, ll.modelo), []).append(ll)
    por_tarea = []
    for (tarea, modelo), ll in sorted(grupos.items()):
        segundos = [x.segundos for x in ll]
        coste = sum(x.coste_usd for x in ll)
        por_tarea.append(
            {
                "tarea": tarea,
                "modelo": modelo,
                "llamadas": len(ll),
                "tokens_entrada": sum(x.tokens_entrada for x in ll),
                "tokens_salida": sum(x.tokens_salida for x in ll),
                "segundos_media": round(sum(segundos) / len(ll), 2),
                "segundos_p95": _percentil(segundos, 0.95),
                "coste_usd": round(coste, 6),
                "coste_medio_usd": round(coste / len(ll), 6),
            }
        )
    return {
        "proveedor": PROVEEDOR,
        "llamadas": len(llamadas),
        "errores": errores,
        "tokens_entrada": sum(x.tokens_entrada for x in llamadas),
        "tokens_salida": sum(x.tokens_salida for x in llamadas),
        "coste_usd": round(sum(x.coste_usd for x in llamadas), 6),
        "gasto_hoy_usd": round(gasto_hoy(), 6),
        "presupuesto_diario_usd": PRESUPUESTO_DIARIO_USD or None,
        "timeout_s": TIMEOUT_S,
        "por_tarea": por_tarea,
    }


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
    if PRESUPUESTO_DIARIO_USD and gasto_hoy() >= PRESUPUESTO_DIARIO_USD:
        raise PresupuestoAgotado(
            f"Presupuesto diario de IA agotado ({PRESUPUESTO_DIARIO_USD} $). Vuelve mañana."
        )
    inicio = time.perf_counter()
    llamar = _parse_gemini if PROVEEDOR == "gemini" else _parse_claude
    try:
        objeto, nombre, entrada, salida = llamar(modelo, system, contenido, formato, max_tokens)
    except Exception as e:  # clave mal, sin saldo, límite por minuto, timeout, respuesta cortada...
        with _cerrojo:
            _errores[type(e).__name__] = _errores.get(type(e).__name__, 0) + 1
        if isinstance(e, ErrorLLM):
            raise
        log.exception("Fallo al llamar a la IA")
        raise ErrorLLM(f"{type(e).__name__}: {str(e)[:300]}") from e
    llamada = Llamada(tarea, nombre, entrada, salida, round(time.perf_counter() - inicio, 2))
    _registrar(llamada)
    log.info(json.dumps({**asdict(llamada), "coste_usd": round(llamada.coste_usd, 6)}))
    return objeto, llamada
