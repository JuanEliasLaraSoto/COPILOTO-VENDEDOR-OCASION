from copiloto.texto import cifras, cifras_sin_respaldo, normalizar, quitar_datos_personales


def test_normalizar():
    assert normalizar("  Garantía   ÚNICA ") == "garantia unica"


def test_cifras_formatos_espanoles():
    assert cifras("21.500 €, 92.000 km, 4,9 l/100 km y 194 CV") == {21500, 92000, 4.9, 194}


def test_cifras_sin_respaldo():
    assert cifras_sin_respaldo("Precio 21.500 € con 3 años", {21500}) == [3]


def test_quitar_datos_personales():
    texto = quitar_datos_personales("Llámame al 612 345 678 o a juan@correo.es")
    assert "612" not in texto and "@" not in texto


def test_cifras_en_ingles():
    assert cifras("92,000 km for 27,500 EUR, 4.9 l") == {92000, 27500, 4.9}
