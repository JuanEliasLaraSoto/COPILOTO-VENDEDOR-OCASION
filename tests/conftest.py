import numpy as np
import pandas as pd
import pytest

from copiloto import llm
from copiloto.precio import ModeloPrecio


@pytest.fixture(scope="session")
def coches_sinteticos() -> pd.DataFrame:
    """Dataset pequeño e inventado para entrenar el modelo de precio en los tests."""
    rng = np.random.default_rng(0)
    modelos = [
        ("seat", "leon", "gasolina", 24000),
        ("toyota", "corolla", "hibrido", 28000),
        ("mercedes-benz", "clase c", "diesel", 45000),
        ("tesla", "model 3", "electrico", 50000),
    ]
    filas = []
    for _ in range(400):
        marca, modelo, combustible, base = modelos[rng.integers(len(modelos))]
        anio = int(rng.integers(2014, 2025))
        km = int(14000 * (2026 - anio) + rng.integers(0, 8000))
        precio = base * 0.88 ** (2026 - anio) * rng.lognormal(0, 0.05)
        filas.append(
            {
                "marca": marca,
                "modelo": modelo,
                "anio": anio,
                "km": km,
                "combustible": combustible,
                "cambio": "automatico",
                "potencia_cv": np.nan,
                "precio": round(precio),
            }
        )
    return pd.DataFrame(filas)


@pytest.fixture(scope="session")
def modelo_precio(coches_sinteticos) -> ModeloPrecio:
    return ModeloPrecio.entrenar(coches_sinteticos, max_iter=60)


@pytest.fixture(scope="session")
def stock():
    from copiloto.vehiculo import cargar_stock  # aquí dentro: este archivo se usa desde la fase 1

    return cargar_stock()  # stock/stock.csv: los tests se ejecutan desde la raíz del proyecto


class LLMFalso:
    """Un LLM de mentira: devuelve respuestas preparadas según el esquema que se le pide."""

    def __init__(self, respuestas: dict):
        self.respuestas = respuestas  # {Esquema: objeto que devuelve}
        self.llamadas = []  # lo que se le ha enviado, para comprobarlo en los tests

    def __call__(self, tarea, modelo, system, contenido, formato, max_tokens=2000):
        self.llamadas.append({"tarea": tarea, "modelo": modelo, "contenido": contenido})
        return self.respuestas[formato], llm.Llamada(tarea, modelo, 1000, 200, 0.5)


@pytest.fixture
def llm_falso(monkeypatch):
    """Sustituye llm.parse por un LLMFalso: los tests no gastan dinero ni necesitan internet."""

    def instalar(respuestas: dict) -> LLMFalso:
        falso = LLMFalso(respuestas)
        monkeypatch.setattr(llm, "parse", falso)
        return falso

    return instalar
