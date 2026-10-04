"""Conexión a las APIs públicas (Ministerio de carburantes y Red Eléctrica).

El servidor del Ministerio usa una configuración de seguridad antigua: corta la conexión si
Python intenta TLS 1.3 o cifrados modernos. Por eso, si la conexión normal falla, se reintenta
con TLS 1.2 y cifrados antiguos. El certificado del servidor se sigue comprobando siempre.
"""

import logging
import ssl

import httpx

log = logging.getLogger("copiloto.red")

CABECERAS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Accept": "application/json",
}


def contexto_antiguo() -> ssl.SSLContext:
    """TLS 1.2 y cifrados antiguos (nivel de seguridad 1), verificando el certificado."""
    ctx = ssl.create_default_context()
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    ctx.options |= getattr(ssl, "OP_IGNORE_UNEXPECTED_EOF", 0)
    return ctx


def get(url: str, **kwargs) -> httpx.Response:
    """Como httpx.get, pero si el servidor corta la conexión, reintenta en modo compatible."""
    try:
        respuesta = httpx.get(url, headers=CABECERAS, timeout=30, **kwargs)
    except httpx.ConnectError as e:
        log.info("Conexión normal rechazada (%s); reintento con TLS 1.2", e)
        respuesta = httpx.get(
            url, headers=CABECERAS, timeout=30, verify=contexto_antiguo(), **kwargs
        )
    respuesta.raise_for_status()
    return respuesta
