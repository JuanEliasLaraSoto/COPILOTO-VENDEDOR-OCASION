"""API web con FastAPI: una ruta por cada función del copiloto."""

import logging
import time
from collections import defaultdict, deque
from dataclasses import asdict
from functools import cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from copiloto import anuncio, financiacion, llm, recomendador, respuestas, tasacion
from copiloto.coste_anual import comparar, perfil_con_precios_reales
from copiloto.precio import ModeloPrecio
from copiloto.valoracion import alertas_stock, precio_recomendado
from copiloto.vehiculo import CocheCliente, Vehiculo, cargar_stock

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Copiloto del vendedor de vehículos de ocasión")
WEB = Path("web/index.html")  # rutas relativas a la raíz del proyecto
LIMITE_POR_HORA = 20  # peticiones que usan el LLM, por IP y hora
_peticiones: dict[str, deque] = defaultdict(deque)
log = logging.getLogger("copiloto.api")


@app.exception_handler(llm.ErrorLLM)
def error_de_la_ia(request: Request, e: llm.ErrorLLM):
    """Si la IA falla, la web enseña el motivo en vez de un «Internal Server Error»."""
    return JSONResponse(status_code=502, content={"detail": f"La IA no ha respondido bien. {e}"})


@app.exception_handler(Exception)
def error_inesperado(request: Request, e: Exception):
    log.exception("Error inesperado")  # el detalle completo sale en la terminal
    detalle = f"Error interno ({type(e).__name__}). Mira la terminal donde corre el servidor."
    return JSONResponse(status_code=500, content={"detail": detalle})


@cache
def stock() -> dict[str, Vehiculo]:
    return cargar_stock()


@cache
def modelo_precio() -> ModeloPrecio:
    return ModeloPrecio.cargar()


def vehiculo(id_: str) -> Vehiculo:
    if id_ not in stock():
        raise HTTPException(404, f"No hay ningún coche con referencia {id_} en el stock.")
    return stock()[id_]


def comprobar_limite(request: Request) -> None:
    """Máximo LIMITE_POR_HORA usos del LLM por IP y hora, para proteger el saldo de la API."""
    ip = request.client.host if request.client else "desconocida"
    ahora, cola = time.time(), _peticiones[ip]
    while cola and ahora - cola[0] > 3600:
        cola.popleft()
    if len(cola) >= LIMITE_POR_HORA:
        raise HTTPException(429, "Has llegado al límite de usos por hora. Prueba más tarde.")
    cola.append(ahora)


def uso(*llamadas) -> dict:
    """Modelo, segundos y coste de las llamadas al LLM (se enseña en la web)."""
    ll = [x for x in llamadas if x]
    return {
        "modelos": sorted({x.modelo for x in ll}),
        "segundos": round(sum(x.segundos for x in ll), 2),
        "coste_usd": round(sum(x.coste_usd for x in ll), 5),
    }


# ---------- Peticiones ----------


class PeticionId(BaseModel):
    id: str


class PeticionRespuesta(BaseModel):
    id: str
    mensaje: str = Field(min_length=2, max_length=2000)


class PeticionTasacion(BaseModel):
    coche: CocheCliente
    notas: str = Field("", max_length=3000)


class PeticionCoste(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=4)
    km_anuales: int = Field(15_000, ge=1_000, le=100_000)
    carga_en_casa: bool = True
    provincia: str = "Malaga"
    # Opcionales: si el vendedor los escribe, mandan sobre los de las APIs.
    precio_gasolina: float | None = Field(None, gt=0.5, lt=5)
    precio_diesel: float | None = Field(None, gt=0.5, lt=5)
    precio_kwh_casa: float | None = Field(None, gt=0.01, lt=2)


class PeticionRecomendar(BaseModel):
    texto: str = Field(min_length=5, max_length=3000)
    provincia: str = "Malaga"


class PeticionFinanciacion(BaseModel):
    precio: float = Field(gt=0, le=500_000)
    entrada: float = Field(0, ge=0)
    meses: int = Field(60, ge=1, le=120)
    tin: float = Field(7.99, ge=0, le=30)
    comision_apertura_pct: float = Field(0, ge=0, le=10)


# ---------- Rutas ----------


@app.get("/health")
def health():
    return {"estado": "ok"}


@app.get("/")
def portada():
    return FileResponse(WEB)


@app.get("/stock")
def ver_stock():
    return [v.model_dump() for v in stock().values()]


@app.get("/precio/{id_}")
def precio(id_: str):
    return precio_recomendado(modelo_precio(), vehiculo(id_))


@app.get("/alertas")
def alertas():
    return alertas_stock(modelo_precio(), stock())


@app.post("/anuncio")
def crear_anuncio(p: PeticionId, request: Request):
    v = vehiculo(p.id)
    comprobar_limite(request)
    resultado, ll = anuncio.generar_anuncio(v)
    return {**resultado, "uso": uso(ll)}


@app.post("/respuesta")
def responder_cliente(p: PeticionRespuesta, request: Request):
    v = vehiculo(p.id)
    comprobar_limite(request)
    resultado, ll = respuestas.responder(v, p.mensaje)
    return {**resultado, "uso": uso(ll)}


@app.post("/tasacion")
def tasar(p: PeticionTasacion, request: Request):
    danos, descartados, ll = tasacion.Danos(), [], None
    if p.notas.strip():  # sin notas no hace falta el LLM
        comprobar_limite(request)
        danos, descartados, ll = tasacion.extraer_danos(p.notas)
    resultado = tasacion.tasar(modelo_precio(), p.coche, danos)
    return {
        **resultado,
        "danos": danos.model_dump(exclude={"citas"}),
        "citas": [c.model_dump() for c in danos.citas],
        "descartados_sin_cita": descartados,
        "uso": uso(ll),
    }


@app.post("/coste-anual")
def coste(p: PeticionCoste):
    manuales = {
        "precio_gasolina": p.precio_gasolina,
        "precio_diesel": p.precio_diesel,
        "precio_kwh_casa": p.precio_kwh_casa,
    }
    perfil = perfil_con_precios_reales(p.km_anuales, p.carga_en_casa, p.provincia, manuales)
    resultado = comparar([vehiculo(i) for i in p.ids], perfil)
    return {**resultado, "precios_energia": asdict(perfil)}


@app.post("/recomendar")
def recomendar(p: PeticionRecomendar, request: Request):
    comprobar_limite(request)
    perfil = perfil_con_precios_reales(15_000, True, p.provincia)
    resultado, llamadas = recomendador.recomendar(p.texto, list(stock().values()), perfil)
    return {**resultado, "uso": uso(*llamadas)}


@app.post("/financiacion")
def financiar(p: PeticionFinanciacion):
    try:
        f = financiacion.simular(p.precio, p.entrada, p.meses, p.tin, p.comision_apertura_pct)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return asdict(f)
