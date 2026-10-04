from copiloto import llm, respuestas
from copiloto.respuestas import Respuesta


def test_router():
    assert respuestas.elegir_modelo("¿Tiene ITV?") == llm.HAIKU
    assert respuestas.elegir_modelo("¿ITV? ¿Garantía? ¿Financiación?") == llm.SONNET


def test_responder(llm_falso, stock):
    llm_falso(
        {
            Respuesta: Respuesta(
                texto="Hola. Tiene 12 meses de garantía. Sobre los 25.000 € que comentas, "
                "lo hablo con mi responsable y te digo.",
                campos_usados=["garantia_meses", "inventado", "dias_en_stock"],
                pendiente=["Contraoferta de 25.000 €"],
            )
        }
    )
    r, _ = respuestas.responder(stock["VO-002"], "¿Tiene garantía? ¿Me lo dejas en 25.000 €?")
    assert r["campos_usados"] == ["garantia_meses"]
    assert r["listo_para_enviar"]  # 25.000 lo dijo el cliente: se puede repetir


def test_responder_avisa_si_inventa(llm_falso, stock):
    llm_falso(
        {Respuesta: Respuesta(texto="Tiene 24 meses de garantía.", campos_usados=[], pendiente=[])}
    )
    r, _ = respuestas.responder(stock["VO-002"], "¿Garantía?")
    assert not r["listo_para_enviar"] and "24" in r["avisos"][0]
