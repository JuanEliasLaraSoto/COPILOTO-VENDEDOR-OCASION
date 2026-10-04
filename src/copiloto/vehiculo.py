"""La ficha de un coche del stock del concesionario y la carga del stock desde un CSV.

La ficha es la «fuente de la verdad»: el anuncio, las respuestas a clientes y los cálculos
solo pueden usar lo que esté aquí (o en las notas del vendedor).
"""

from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field

from copiloto.texto import cifras

Combustible = Literal["gasolina", "diesel", "hibrido", "hibrido_enchufable", "electrico"]
Cambio = Literal["manual", "automatico"]
Etiqueta = Literal["0", "ECO", "C", "B", "sin etiqueta"]

RUTA_STOCK = Path("stock/stock.csv")


class Vehiculo(BaseModel):
    id: str
    marca: str
    modelo: str
    version: str | None = None
    carroceria: str | None = None  # compacto, berlina, familiar, suv, monovolumen...
    anio: int
    km: int
    combustible: Combustible
    cambio: Cambio
    potencia_cv: int | None = None
    plazas: int = 5
    precio: int  # precio de venta al público, en euros
    # Consumo homologado WLTP, tal cual aparece en la ficha técnica del coche.
    consumo_l_100km: float | None = Field(None, description="Gasolina/diésel/híbridos")
    consumo_kwh_100km: float | None = Field(None, description="Eléctricos e híbridos enchufables")
    autonomia_electrica_km: int | None = None
    etiqueta_dgt: Etiqueta
    propietarios: int | None = None
    libro_revisiones: bool | None = None
    garantia_meses: int | None = None
    itv_hasta: str | None = None  # "03/2027"
    color: str | None = None
    extras: list[str] = []
    notas: str = ""  # notas internas del vendedor ("2 llaves, rayón en la puerta trasera")
    dias_en_stock: int = 0

    def nombre(self) -> str:
        return f"{self.marca} {self.modelo} {self.version or ''}".strip()

    def cifras_de_la_ficha(self) -> set[float]:
        """Todas las cifras que se pueden mencionar sobre este coche sin inventar nada."""
        datos = self.para_el_llm().values()
        numeros = {
            float(v) for v in datos if isinstance(v, int | float) and not isinstance(v, bool)
        }
        numeros |= cifras(" ".join([self.version or "", self.itv_hasta or "", self.notas]))
        numeros |= cifras(" ".join(self.extras))
        if self.garantia_meses:
            numeros.add(self.garantia_meses / 12)  # «12 meses» también se puede decir «1 año»
        return numeros

    def para_el_llm(self) -> dict:
        """La ficha sin datos internos que el cliente no debe ver (días en stock)."""
        return self.model_dump(exclude={"dias_en_stock"})


class CocheCliente(BaseModel):
    """El coche que trae un cliente para tasar: solo lo que hace falta para el precio."""

    marca: str
    modelo: str
    anio: int = Field(ge=1990, le=2030)
    km: int = Field(ge=0, le=600_000)
    combustible: Combustible
    cambio: Cambio
    potencia_cv: int | None = None
    precio: int | None = None  # no tiene precio de venta: es lo que queremos calcular


def cargar_stock(ruta: Path = RUTA_STOCK) -> dict[str, Vehiculo]:
    """Lee el CSV del stock. Los extras van separados por «|» en una sola columna."""
    df = pd.read_csv(ruta, dtype={"id": str, "etiqueta_dgt": str})
    df = df.astype(object).where(df.notna(), None)  # celdas vacías -> None
    stock = {}
    for fila in df.to_dict(orient="records"):
        fila["extras"] = [e.strip() for e in (fila.get("extras") or "").split("|") if e.strip()]
        fila["notas"] = fila.get("notas") or ""
        v = Vehiculo.model_validate(fila)
        stock[v.id] = v
    return stock
