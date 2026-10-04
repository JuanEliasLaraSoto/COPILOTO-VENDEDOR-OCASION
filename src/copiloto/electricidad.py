"""Precio de la luz para cargar un eléctrico.

En casa: precio oficial PVPC del día, de la API pública de Red Eléctrica (REData).
Fuera de casa: precio orientativo de los cargadores públicos (no hay un dato oficial único).
"""

import logging
import time
from datetime import date
from statistics import median

import httpx

from copiloto import red

log = logging.getLogger("copiloto.electricidad")

URL_REE = "https://apidatos.ree.es/es/datos/mercados/precios-mercados-tiempo-real"

PRECIO_CASA_RESPALDO = 0.15  # €/kWh, si la API no responde
PRECIO_PUBLICO = 0.45  # €/kWh, media orientativa de cargadores públicos (rápidos y lentos)

_CACHE: dict[str, tuple[float, float]] = {}
CACHE_SEGUNDOS = 6 * 3600


def descargar_precios(dia: date) -> dict:
    respuesta = red.get(
        URL_REE,
        params={"start_date": f"{dia}T00:00", "end_date": f"{dia}T23:59", "time_trunc": "hour"},
    )
    return respuesta.json()


def pvpc_medio(datos: dict) -> float | None:
    """Mediana del día en €/kWh. La API da varias series en €/MWh; buscamos la del PVPC."""
    for serie in datos.get("included", []):
        atributos = serie.get("attributes", {})
        if "pvpc" in atributos.get("title", "").lower():
            valores = [v["value"] for v in atributos.get("values", [])]
            return round(median(valores) / 1000, 4) if valores else None
    return None


def precio_kwh_casa(dia: date | None = None) -> tuple[float, str]:
    """Devuelve (precio €/kWh, origen). Origen es 'api' o 'respaldo'."""
    dia = dia or date.today()
    clave = str(dia)
    if clave in _CACHE and time.time() - _CACHE[clave][0] < CACHE_SEGUNDOS:
        return _CACHE[clave][1], "api"
    try:
        precio = pvpc_medio(descargar_precios(dia))
    except (httpx.HTTPError, KeyError, ValueError) as e:
        log.warning("API de Red Eléctrica sin respuesta: %s: %s", type(e).__name__, e)
        precio = None
    if precio is None:
        return PRECIO_CASA_RESPALDO, "respaldo"
    _CACHE[clave] = (time.time(), precio)
    return precio, "api"
