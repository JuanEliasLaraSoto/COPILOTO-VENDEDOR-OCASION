def test_cargar_stock(stock):
    assert len(stock) == 24
    eqa = stock["VO-004"]
    assert eqa.combustible == "electrico" and eqa.consumo_kwh_100km == 17.7
    assert eqa.extras == ["navegador", "bomba de calor", "carga rápida"]


def test_cifras_de_la_ficha_no_incluye_datos_internos(stock):
    c = stock["VO-002"]  # 71 días en stock: no se le debe contar al cliente
    numeros = c.cifras_de_la_ficha()
    assert {27500, 92000, 194, 2019, 4.9, 1}.issubset(numeros)  # 1 = 12 meses de garantía
    assert 71 not in numeros
    assert "dias_en_stock" not in c.para_el_llm()
