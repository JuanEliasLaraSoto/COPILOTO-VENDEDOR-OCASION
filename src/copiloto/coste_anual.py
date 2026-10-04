"""Cuánto cuesta al año cada coche según su motor, y en cuántos años compensa pagar más.

Los consumos salen de la ficha técnica (WLTP), nunca del LLM. Los precios de la energía,
de las APIs oficiales. Las cuentas, de este código.
"""

from dataclasses import dataclass, field

from copiloto.vehiculo import Vehiculo

# El consumo homologado WLTP suele quedarse corto en la vida real: lo corregimos un 15 %.
CORRECCION_REAL = 1.15

# Supuestos orientativos (€/año). Se muestran siempre al cliente para que sepa de dónde sale.
MANTENIMIENTO = {
    "electrico": 250,
    "hibrido": 400,
    "hibrido_enchufable": 420,
    "gasolina": 450,
    "diesel": 500,
}
SEGURO = 500  # igual para todos: depende del conductor más que del motor
IMPUESTO_CIRCULACION = {"electrico": 30, "hibrido_enchufable": 30}  # bonificados en muchos sitios
IMPUESTO_CIRCULACION_DEFECTO = 110

# Parte de los km que un enchufable hace en modo eléctrico, según si carga en casa o no.
KM_ELECTRICOS_ENCHUFABLE = {True: 0.6, False: 0.15}


@dataclass
class Perfil:
    """Cómo usa el coche el cliente."""

    km_anuales: int = 15_000
    carga_en_casa: bool = True
    precio_gasolina: float = 1.55  # €/L
    precio_diesel: float = 1.45  # €/L
    precio_kwh_casa: float = 0.15
    precio_kwh_publico: float = 0.45
    # De dónde sale cada precio: «hoy (Ministerio)», «reserva», «escrito por el vendedor»...
    origen: dict = field(default_factory=dict)


@dataclass
class CosteAnual:
    id: str
    nombre: str
    combustible: str
    precio_compra: int
    energia: float
    mantenimiento: float
    seguro: float
    impuesto: float
    supuestos: list[str] = field(default_factory=list)

    @property
    def total(self) -> float:
        return round(self.energia + self.mantenimiento + self.seguro + self.impuesto, 2)


def _precio_kwh(perfil: Perfil) -> float:
    """Con garaje se carga casi todo en casa (90 %); sin garaje, todo en la calle."""
    if perfil.carga_en_casa:
        return 0.9 * perfil.precio_kwh_casa + 0.1 * perfil.precio_kwh_publico
    return perfil.precio_kwh_publico


def coste_energia(v: Vehiculo, perfil: Perfil) -> tuple[float, str]:
    """Euros al año en combustible o electricidad, y una frase que explica la cuenta."""
    km = perfil.km_anuales
    litro = perfil.precio_diesel if v.combustible == "diesel" else perfil.precio_gasolina
    kwh = _precio_kwh(perfil)

    if v.combustible == "electrico":
        consumo = (v.consumo_kwh_100km or 0) * CORRECCION_REAL
        return km / 100 * consumo * kwh, f"{consumo:.1f} kWh/100 km a {kwh:.3f} €/kWh"

    if v.combustible == "hibrido_enchufable" and v.consumo_kwh_100km:
        parte = KM_ELECTRICOS_ENCHUFABLE[perfil.carga_en_casa]
        c_kwh = v.consumo_kwh_100km * CORRECCION_REAL
        c_l = (v.consumo_l_100km or 0) * CORRECCION_REAL
        euros = km * parte / 100 * c_kwh * kwh + km * (1 - parte) / 100 * c_l * litro
        return euros, f"{parte:.0%} de los km en eléctrico; resto a {c_l:.1f} L/100 km"

    consumo = (v.consumo_l_100km or 0) * CORRECCION_REAL
    return km / 100 * consumo * litro, f"{consumo:.1f} L/100 km a {litro:.3f} €/L"


def coste_anual(v: Vehiculo, perfil: Perfil) -> CosteAnual:
    energia, explicacion = coste_energia(v, perfil)
    return CosteAnual(
        id=v.id,
        nombre=v.nombre(),
        combustible=v.combustible,
        precio_compra=v.precio,
        energia=round(energia, 2),
        mantenimiento=MANTENIMIENTO[v.combustible],
        seguro=SEGURO,
        impuesto=IMPUESTO_CIRCULACION.get(v.combustible, IMPUESTO_CIRCULACION_DEFECTO),
        supuestos=[
            f"Energía: {explicacion} (consumo oficial WLTP + {CORRECCION_REAL - 1:.0%} real)",
            f"{perfil.km_anuales:,} km al año".replace(",", "."),
            "Mantenimiento, seguro e impuesto: valores medios orientativos",
        ],
    )


def anios_para_compensar(caro: CosteAnual, barato: CosteAnual) -> float | None:
    """Años que tarda el coche más caro en recuperar la diferencia con lo que ahorra al año.

    None si no ahorra nada (nunca compensa por coste).
    """
    diferencia_precio = caro.precio_compra - barato.precio_compra
    ahorro_anual = barato.total - caro.total
    if ahorro_anual <= 0:
        return None
    return round(max(diferencia_precio, 0) / ahorro_anual, 1)


def comparar(vehiculos: list[Vehiculo], perfil: Perfil, anios: int = 5) -> dict:
    """Coste anual de cada coche, coste total a `anios` años y cuándo compensa cada uno."""
    costes = [coste_anual(v, perfil) for v in vehiculos]
    mas_barato = min(costes, key=lambda c: c.precio_compra)
    filas = []
    for c in sorted(costes, key=lambda c: c.total):
        filas.append(
            {
                "id": c.id,
                "nombre": c.nombre,
                "combustible": c.combustible,
                "precio_compra": c.precio_compra,
                "energia": round(c.energia),
                "mantenimiento": c.mantenimiento,
                "seguro": c.seguro,
                "impuesto": c.impuesto,
                "total_anual": round(c.total),
                f"total_{anios}_anios": round(c.precio_compra + c.total * anios),
                "anios_para_compensar": (
                    None if c is mas_barato else anios_para_compensar(c, mas_barato)
                ),
                "supuestos": c.supuestos,
            }
        )
    return {"referencia": mas_barato.nombre, "anios": anios, "coches": filas}


ORIGEN = {
    "api": "precio de hoy (API oficial)",
    "respaldo": "precio de RESERVA: la API no respondió; escríbelo a mano",
}


def perfil_con_precios_reales(
    km_anuales: int,
    carga_en_casa: bool,
    provincia: str,
    manuales: dict[str, float | None] | None = None,
) -> Perfil:
    """Perfil del cliente con los precios de hoy: carburantes del Ministerio y luz de REE.

    `manuales`: precios escritos por el vendedor; mandan sobre los de las APIs.
    """
    from copiloto.carburantes import precio_actual
    from copiloto.electricidad import precio_kwh_casa

    manuales = {k: v for k, v in (manuales or {}).items() if v}
    precios, origen = {}, {}
    for clave, buscar in [
        ("precio_gasolina", lambda: precio_actual(provincia, "gasolina")),
        ("precio_diesel", lambda: precio_actual(provincia, "diesel")),
        ("precio_kwh_casa", precio_kwh_casa),
    ]:
        if clave in manuales:
            precios[clave], origen[clave] = manuales[clave], "escrito por el vendedor"
        else:
            precio, de_donde = buscar()
            precios[clave], origen[clave] = precio, ORIGEN[de_donde]
    return Perfil(km_anuales, carga_en_casa, **precios, origen=origen)
