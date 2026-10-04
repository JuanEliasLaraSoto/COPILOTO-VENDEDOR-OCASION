import sys
from pathlib import Path

from copiloto.anuncio import Anuncio
from copiloto.respuestas import Respuesta

sys.path.insert(0, str(Path(__file__).parent.parent / "evals"))
import evaluar  # noqa: E402


def test_evaluar_con_llm_falso(llm_falso):
    llm_falso(
        {
            Anuncio: Anuncio(
                titulo="Coche",
                texto_web="Coche con 999 CV.",
                texto_corto="Coche.",
                texto_ingles="Car.",
                destacados=[],
            ),
            Respuesta: Respuesta(texto="Lo consulto.", campos_usados=[], pendiente=["dato"]),
        }
    )
    r = evaluar.evaluar("modelo-de-prueba")
    assert r["anuncios_sin_invenciones_pct"] == 0  # 999 CV es inventado en todos
    assert r["respuestas_sin_invenciones_pct"] == 100
    assert r["trampas_marcadas_pendientes_pct"] == 100
