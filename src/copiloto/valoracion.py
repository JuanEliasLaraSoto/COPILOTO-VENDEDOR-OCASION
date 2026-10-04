"""Precio recomendado para un coche del stock y alertas de coches que no se venden."""

from copiloto.precio import ModeloPrecio, valorar
from copiloto.texto import normalizar
from copiloto.vehiculo import CocheCliente, Vehiculo

DIAS_STOCK_LENTO = 60  # a partir de aquí, un coche «se está quedando»
DIAS_STOCK_MUY_LENTO = 90


def precio_recomendado(modelo: ModeloPrecio, v: Vehiculo | CocheCliente) -> dict:
    """Rango de mercado del modelo de ML y cómo está el precio actual frente a ese rango."""
    coche = {
        "marca": normalizar(v.marca),
        "modelo": normalizar(v.modelo),
        "combustible": v.combustible,
        "cambio": v.cambio,
        "anio": v.anio,
        "km": v.km,
        "potencia_cv": v.potencia_cv,
        "precio": v.precio,
    }
    return valorar(modelo, coche)


def alerta(v: Vehiculo, val: dict) -> dict | None:
    """Reglas de negocio sencillas y explicables. Devuelve None si el coche está bien."""
    desv = val["desviacion_pct"]
    estimado = round(val["precio_estimado"], -2)  # redondeado a centenas
    if v.dias_en_stock >= DIAS_STOCK_LENTO and desv > 5:
        prioridad = "alta" if v.dias_en_stock >= DIAS_STOCK_MUY_LENTO else "media"
        accion = f"Bajar a unos {estimado:,.0f} €".replace(",", ".")
        motivo = f"{v.dias_en_stock} días en stock y {desv:+.1f} % sobre el mercado"
    elif v.dias_en_stock >= DIAS_STOCK_MUY_LENTO:
        prioridad, accion = "media", "Revisar anuncio y fotos: el precio es de mercado"
        motivo = f"{v.dias_en_stock} días en stock con precio de mercado"
    elif v.dias_en_stock < 30 and desv < -10:
        prioridad, accion = "baja", "Margen sin aprovechar: se podría subir el precio"
        motivo = f"Recién entrado y {desv:+.1f} % bajo el mercado"
    else:
        return None
    return {
        "id": v.id,
        "nombre": v.nombre(),
        "precio": v.precio,
        "precio_mercado": val["precio_estimado"],
        "dias_en_stock": v.dias_en_stock,
        "prioridad": prioridad,
        "motivo": motivo,
        "accion": accion,
    }


def alertas_stock(modelo: ModeloPrecio, stock: dict[str, Vehiculo]) -> list[dict]:
    orden = {"alta": 0, "media": 1, "baja": 2}
    lista = [a for v in stock.values() if (a := alerta(v, precio_recomendado(modelo, v)))]
    return sorted(lista, key=lambda a: (orden[a["prioridad"]], -a["dias_en_stock"]))
