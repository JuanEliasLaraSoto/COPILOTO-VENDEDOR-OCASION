"""Simulador de financiación: cuota mensual, intereses y TAE. Matemáticas, sin IA.

Orientativo: las condiciones reales las fija la entidad financiera.
"""

from dataclasses import dataclass


@dataclass
class Financiacion:
    importe: float  # lo que se financia (precio - entrada)
    meses: int
    cuota: float
    total_pagado: float  # cuotas + comisión
    intereses: float
    tae: float  # en %, incluye la comisión de apertura


def cuota_mensual(importe: float, tin_anual: float, meses: int) -> float:
    """Sistema francés (cuota fija): C = P·i / (1 − (1 + i)^−n), con i = TIN/12."""
    i = tin_anual / 100 / 12
    if i == 0:
        return importe / meses
    return importe * i / (1 - (1 + i) ** -meses)


def _tae(recibido: float, cuota: float, meses: int) -> float:
    """TAE: el tipo anual r con el que lo recibido = valor actual de las cuotas.

    Se busca el tipo mensual por bisección (no hay fórmula cerrada) y se anualiza: (1+m)^12 − 1.
    """

    def valor_actual(m: float) -> float:
        return sum(cuota / (1 + m) ** k for k in range(1, meses + 1))

    bajo, alto = 0.0, 1.0
    for _ in range(100):
        medio = (bajo + alto) / 2
        if valor_actual(medio) > recibido:
            bajo = medio  # el tipo es mayor
        else:
            alto = medio
    return ((1 + medio) ** 12 - 1) * 100


def simular(
    precio: float, entrada: float, meses: int, tin_anual: float, comision_apertura_pct: float = 0
) -> Financiacion:
    if not 0 <= entrada < precio:
        raise ValueError("La entrada tiene que ser menor que el precio.")
    if not 1 <= meses <= 120:
        raise ValueError("El plazo tiene que estar entre 1 y 120 meses.")
    importe = precio - entrada
    comision = importe * comision_apertura_pct / 100
    cuota = cuota_mensual(importe, tin_anual, meses)
    total = cuota * meses + comision
    return Financiacion(
        importe=round(importe, 2),
        meses=meses,
        cuota=round(cuota, 2),
        total_pagado=round(total, 2),
        intereses=round(total - importe, 2),
        tae=round(_tae(importe - comision, cuota, meses), 2),
    )
