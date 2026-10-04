"""Carga y limpieza del dataset de coches de ocasión."""

import re

import numpy as np
import pandas as pd

from copiloto.texto import normalizar

# Columnas internas que usa el modelo. El dataset original se traduce a estas.
COLUMNAS = ["marca", "modelo", "anio", "km", "combustible", "cambio", "potencia_cv", "precio"]

SINONIMOS_COMBUSTIBLE = {
    "gasolina": "gasolina",
    "petrol": "gasolina",
    "gasoline": "gasolina",
    "diesel": "diesel",
    "gasoil": "diesel",
    "gasoleo": "diesel",
    "hibrido": "hibrido",
    "hybrid": "hibrido",
    "hibrido enchufable": "hibrido_enchufable",
    "plug-in hybrid": "hibrido_enchufable",
    "phev": "hibrido_enchufable",
    "electrico": "electrico",
    "electric": "electrico",
    "glp": "glp",
    "gnc": "gnc",
}
SINONIMOS_CAMBIO = {
    "manual": "manual",
    "automatico": "automatico",
    "automatic": "automatico",
    "auto": "automatico",
}


def a_entero(valor) -> float:
    """'12.500 €' -> 12500; '85.000 km' -> 85000; '110 CV' -> 110; vacío -> NaN."""
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return np.nan
    if isinstance(valor, (int, float, np.integer, np.floating)):
        return float(valor)
    digitos = re.sub(r"[^\d]", "", str(valor).split(",")[0])
    return float(digitos) if digitos else np.nan


def limpiar_texto(serie: pd.Series) -> pd.Series:
    return serie.astype("string").map(lambda t: normalizar(t) if isinstance(t, str) else pd.NA)


def leer_csv(ruta: str, sep: str = ";") -> pd.DataFrame:
    """Lee un CSV probando primero UTF-8 y, si falla, Latin-1 (habitual en archivos de Windows)."""
    try:
        return pd.read_csv(ruta, sep=sep, encoding="utf-8")
    except UnicodeDecodeError:
        return pd.read_csv(ruta, sep=sep, encoding="latin-1")


def potencia_desde_motor(motor: pd.Series) -> pd.Series:
    """'SC 1.2 TSI 90cv Style' -> 90. Si no hay 'cv', queda vacío."""
    return motor.astype(str).str.extract(r"(\d+)\s*cv", flags=re.IGNORECASE)[0].astype(float)


def cargar(ruta: str, mapa_columnas: dict[str, str], sep: str = ";") -> pd.DataFrame:
    """Lee el CSV y renombra sus columnas a las internas.

    mapa_columnas: {"nombre en el CSV": "nombre interno"}, p. ej. {"brand": "marca"}.
    Si el mapa incluye una columna "motor", se saca de ella la potencia en CV.
    Las columnas internas que falten se crean vacías.
    """
    df = leer_csv(ruta, sep)
    df = df.rename(columns=mapa_columnas)
    if "motor" in df.columns and "potencia_cv" not in df.columns:
        df["potencia_cv"] = potencia_desde_motor(df["motor"])
    for col in COLUMNAS:
        if col not in df.columns:
            df[col] = np.nan
    return df[COLUMNAS].copy()


def limpiar(df: pd.DataFrame, anio_actual: int) -> pd.DataFrame:
    """Normaliza tipos y textos y quita filas imposibles."""
    df = df.copy()
    for col in ["anio", "km", "potencia_cv", "precio"]:
        df[col] = df[col].map(a_entero)
    for col in ["marca", "modelo", "combustible", "cambio"]:
        df[col] = limpiar_texto(df[col])
    df["combustible"] = df["combustible"].map(
        lambda c: SINONIMOS_COMBUSTIBLE.get(c, c) if isinstance(c, str) else c
    )
    df["cambio"] = df["cambio"].map(
        lambda c: SINONIMOS_CAMBIO.get(c, c) if isinstance(c, str) else c
    )

    antes = len(df)
    df = df.dropna(subset=["marca", "modelo", "anio", "km", "precio"])
    df = df[df["anio"].between(1990, anio_actual)]
    df = df[df["km"].between(0, 600_000)]
    df = df[df["precio"].between(1_000, 150_000)]
    df = df.drop_duplicates()
    print(f"Limpieza: {antes} -> {len(df)} filas")
    return df.reset_index(drop=True)
