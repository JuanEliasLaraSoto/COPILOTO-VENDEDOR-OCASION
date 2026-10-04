from copiloto.valoracion import alerta, alertas_stock, precio_recomendado


def val(desviacion, estimado=20_000):
    return {"desviacion_pct": desviacion, "precio_estimado": estimado}


def test_reglas_de_alerta(stock):
    v = stock["VO-013"].model_copy(update={"dias_en_stock": 103})
    a = alerta(v, val(+9))
    assert a["prioridad"] == "alta" and "20.000" in a["accion"]
    assert alerta(v.model_copy(update={"dias_en_stock": 10}), val(+9)) is None
    assert alerta(v.model_copy(update={"dias_en_stock": 10}), val(-15))["prioridad"] == "baja"


def test_precio_recomendado_y_alertas(stock, modelo_precio):
    r = precio_recomendado(modelo_precio, stock["VO-007"])
    assert r["rango_min"] < r["precio_estimado"] < r["rango_max"]
    lista = alertas_stock(modelo_precio, stock)
    prioridades = [a["prioridad"] for a in lista]
    assert prioridades == sorted(prioridades, key=["alta", "media", "baja"].index)
