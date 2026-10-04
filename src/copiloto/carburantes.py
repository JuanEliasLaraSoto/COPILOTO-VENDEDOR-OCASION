"""Precios reales de carburantes.

Fuente: datos abiertos del Ministerio, «Precios de carburantes en las gasolineras españolas»
(datos.gob.es). Al reutilizarlos hay que citar la fuente.
"""

import logging
import time
from statistics import median

import httpx

from copiloto import red
from copiloto.texto import normalizar

log = logging.getLogger("copiloto.carburantes")

URL_PROVINCIA = (
    "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/"
    "PreciosCarburantes/EstacionesTerrestres/FiltroProvincia/{id}"
)

# Códigos INE de provincia
PROVINCIAS = {
    "alava": "01",
    "albacete": "02",
    "alicante": "03",
    "almeria": "04",
    "avila": "05",
    "badajoz": "06",
    "baleares": "07",
    "barcelona": "08",
    "burgos": "09",
    "caceres": "10",
    "cadiz": "11",
    "castellon": "12",
    "ciudad real": "13",
    "cordoba": "14",
    "a coruna": "15",
    "cuenca": "16",
    "girona": "17",
    "granada": "18",
    "guadalajara": "19",
    "guipuzcoa": "20",
    "huelva": "21",
    "huesca": "22",
    "jaen": "23",
    "leon": "24",
    "lleida": "25",
    "la rioja": "26",
    "lugo": "27",
    "madrid": "28",
    "malaga": "29",
    "murcia": "30",
    "navarra": "31",
    "ourense": "32",
    "asturias": "33",
    "palencia": "34",
    "las palmas": "35",
    "pontevedra": "36",
    "salamanca": "37",
    "santa cruz de tenerife": "38",
    "cantabria": "39",
    "segovia": "40",
    "sevilla": "41",
    "soria": "42",
    "tarragona": "43",
    "teruel": "44",
    "toledo": "45",
    "valencia": "46",
    "valladolid": "47",
    "vizcaya": "48",
    "zamora": "49",
    "zaragoza": "50",
    "ceuta": "51",
    "melilla": "52",
}

CAMPO_PRECIO = {"gasolina": "Precio Gasolina 95 E5", "diesel": "Precio Gasoleo A"}

# Si la API falla, se usan estos valores (€/L) y se avisa en el informe.
PRECIO_RESPALDO = {"gasolina": 1.55, "diesel": 1.45}

_CACHE: dict[str, tuple[float, list[dict]]] = {}
CACHE_SEGUNDOS = 30 * 60


def a_numero(texto: str | None) -> float | None:
    """'1,459' -> 1.459; '' o None -> None."""
    if not texto:
        return None
    return float(texto.replace(",", "."))


def descargar_provincia(id_provincia: str) -> list[dict]:
    """Descarga las gasolineras de una provincia, con caché de 30 minutos."""
    ahora = time.time()
    if id_provincia in _CACHE and ahora - _CACHE[id_provincia][0] < CACHE_SEGUNDOS:
        return _CACHE[id_provincia][1]
    respuesta = red.get(URL_PROVINCIA.format(id=id_provincia))
    estaciones = respuesta.json()["ListaEESSPrecio"]
    _CACHE[id_provincia] = (ahora, estaciones)
    return estaciones


def precio_mediano(estaciones: list[dict], combustible: str) -> float | None:
    """Mediana del precio de un combustible entre las estaciones que lo venden."""
    campo = CAMPO_PRECIO[combustible]
    precios = [p for e in estaciones if (p := a_numero(e.get(campo))) is not None]
    return round(median(precios), 3) if precios else None


def precio_actual(provincia: str, combustible: str) -> tuple[float, str]:
    """Devuelve (precio €/L, origen). Origen es 'api' o 'respaldo'."""
    combustible = "diesel" if combustible == "diesel" else "gasolina"
    id_prov = PROVINCIAS.get(normalizar(provincia))
    if id_prov is None:
        return PRECIO_RESPALDO[combustible], "respaldo"
    try:
        precio = precio_mediano(descargar_provincia(id_prov), combustible)
    except (httpx.HTTPError, KeyError, ValueError) as e:
        log.warning("API de carburantes sin respuesta: %s: %s", type(e).__name__, e)
        precio = None
    if precio is None:
        return PRECIO_RESPALDO[combustible], "respaldo"
    return precio, "api"
