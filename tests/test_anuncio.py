from copiloto import anuncio
from copiloto.anuncio import Anuncio, Destacado, verificar_anuncio


def un_anuncio(**cambios):
    base = dict(
        titulo="Mercedes-Benz Clase C 220 d Avantgarde",
        texto_web="Berlina diésel de 2019 con 92.000 km y 194 CV. 12 meses de garantía.",
        texto_corto="Clase C 220 d, 2019, 92.000 km, 27.500 €.",
        texto_ingles="2019 C 220 d, 92,000 km... 27,500 EUR.",
        destacados=[
            Destacado(texto="Garantía de 12 meses", campo="garantia_meses"),
            Destacado(
                texto="Control de crucero adaptativo",
                campo="extras",
                cita="control de crucero adaptativo",
            ),
            Destacado(
                texto="Revisiones en la casa oficial",
                campo="notas",
                cita="revisiones en la casa oficial",
            ),  # no está en las notas
            Destacado(texto="Se vende rápido", campo="dias_en_stock"),  # dato interno
            Destacado(texto="Un solo dueño", campo="propietarios"),  # tiene 2 propietarios
        ],
    )
    return Anuncio(**{**base, **cambios})


def test_anuncio_correcto(stock):
    r = verificar_anuncio(un_anuncio(), stock["VO-002"])
    assert r["anuncio"]["destacados"] == ["Garantía de 12 meses", "Control de crucero adaptativo"]
    assert len(r["destacados_descartados"]) == 3
    assert r["avisos"] == {} and r["listo_para_publicar"]


def test_anuncio_con_invenciones(stock):
    malo = un_anuncio(texto_web="Único propietario, consumo de 4,1 L/100 km.")
    r = verificar_anuncio(malo, stock["VO-002"])  # 2 propietarios y 4,9 L/100 km
    assert not r["listo_para_publicar"]
    assert len(r["avisos"]["texto_web"]) == 2


def test_generar_anuncio_manda_la_ficha_sin_datos_internos(llm_falso, stock):
    falso = llm_falso({Anuncio: un_anuncio()})
    r, _ = anuncio.generar_anuncio(stock["VO-002"])
    assert r["listo_para_publicar"]
    assert "dias_en_stock" not in falso.llamadas[0]["contenido"]
