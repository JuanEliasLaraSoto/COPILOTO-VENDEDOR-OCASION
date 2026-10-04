"""Utilidades de texto: normalizar, quitar datos personales y sacar las cifras de un texto."""

import re
import unicodedata

_TELEFONO = re.compile(r"(\+34[\s-]?)?[6789]\d{2}[\s.-]?\d{3}[\s.-]?\d{3}")
_EMAIL = re.compile(r"\S+@\S+\.\S+")
# Un número: 21.500 / 21500 / 5,2 / 4.8 / 92,000 (inglés). Los separadores de miles se quitan.
# No cuenta los que van tras «/», que son unidades: «L/100 km», «kWh/100 km».
_NUMERO = re.compile(
    r"(?<![/\d.,])(?:\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d{1,3}(?:,\d{3})+(?!\d)|\d+(?:[.,]\d+)?)"
)
_MILES_ES = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?")  # 21.500 o 21.500,50
_MILES_EN = re.compile(r"\d{1,3}(?:,\d{3})+")  # 92,000


def normalizar(texto: str) -> str:
    """'  Málaga ' -> 'malaga': minúsculas, sin tildes y sin espacios sobrantes."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sin_tildes.lower()).strip()


def quitar_datos_personales(texto: str) -> str:
    """Borra teléfonos y emails antes de enviar el texto a ningún sitio."""
    return _EMAIL.sub("[email]", _TELEFONO.sub("[teléfono]", texto))


def cifras(texto: str) -> set[float]:
    """Todas las cifras de un texto como números: '21.500 € y 5,2 l' -> {21500.0, 5.2}."""
    resultado = set()
    for n in _NUMERO.findall(texto):
        if _MILES_ES.fullmatch(n):  # 21.500 -> 21500
            n = n.replace(".", "")
        elif _MILES_EN.fullmatch(n):  # 92,000 -> 92000
            n = n.replace(",", "")
        resultado.add(float(n.replace(",", ".")))
    return resultado


def cifras_sin_respaldo(texto: str, permitidas: set[float]) -> list[float]:
    """Cifras de `texto` que no están en `permitidas`. Sirve para pillar números inventados."""
    return sorted(c for c in cifras(texto) if not any(abs(c - p) < 0.01 for p in permitidas))
