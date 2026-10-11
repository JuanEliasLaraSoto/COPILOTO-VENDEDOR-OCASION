"""El acceso a la IA: errores claros y el modo Gemini, con un cliente falso."""

from types import SimpleNamespace as N

import pytest

from copiloto import llm
from copiloto.anuncio import Anuncio

ANUNCIO_JSON = (
    '{"titulo": "t", "texto_web": "w", "texto_corto": "c", "texto_ingles": "e", "destacados": []}'
)


class GeminiFalso:
    def __init__(self, texto, motivo="STOP"):
        self.texto, self.motivo = texto, motivo
        self.models = self  # para poder llamar a cliente.models.generate_content(...)

    def generate_content(self, model, contents, config):
        uso = N(prompt_token_count=900, candidates_token_count=100, thoughts_token_count=3000)
        return N(text=self.texto, usage_metadata=uso, candidates=[N(finish_reason=self.motivo)])


@pytest.fixture
def gemini(monkeypatch):
    monkeypatch.setattr(llm, "PROVEEDOR", "gemini")

    def instalar(texto, motivo="STOP"):
        monkeypatch.setattr(llm, "_cliente_gemini", GeminiFalso(texto, motivo))

    return instalar


def test_gemini_cuenta_el_razonamiento_como_salida(gemini):
    gemini(ANUNCIO_JSON)
    anuncio, ll = llm.parse("anuncio", llm.HAIKU, "s", "ficha", Anuncio)
    assert anuncio.titulo == "t" and ll.tokens_salida == 3100 and ll.coste_usd == 0


def test_respuesta_cortada_da_un_error_claro(gemini):
    gemini(None, motivo="MAX_TOKENS")
    with pytest.raises(llm.ErrorLLM, match="MAX_TOKENS"):
        llm.parse("anuncio", llm.HAIKU, "s", "ficha", Anuncio)


def test_json_roto_da_un_error_claro(gemini):
    gemini('{"titulo": "sin cerrar')
    with pytest.raises(llm.ErrorLLM, match="ValidationError"):
        llm.parse("anuncio", llm.HAIKU, "s", "ficha", Anuncio)


@pytest.fixture
def registro_limpio(monkeypatch):
    monkeypatch.setattr(llm, "_historial", llm.deque(maxlen=1000))
    monkeypatch.setattr(llm, "_errores", {})
    monkeypatch.setattr(llm, "_gasto", {"dia": llm.date.today(), "usd": 0.0})


def test_estadisticas_de_tokens_latencia_y_coste(gemini, registro_limpio, monkeypatch):
    monkeypatch.setitem(llm.PRECIOS, llm.GEMINI[llm.HAIKU], (1.0, 5.0))  # como en plan de pago
    gemini(ANUNCIO_JSON)
    for _ in range(2):
        llm.parse("anuncio", llm.HAIKU, "s", "ficha", Anuncio)
    gemini(None, motivo="MAX_TOKENS")
    with pytest.raises(llm.ErrorLLM):
        llm.parse("anuncio", llm.HAIKU, "s", "ficha", Anuncio)

    e = llm.estadisticas()
    fila = e["por_tarea"][0]
    assert e["llamadas"] == 2 and e["errores"] == {"ErrorLLM": 1}
    assert fila["tokens_entrada"] == 1800 and fila["tokens_salida"] == 6200
    assert fila["coste_usd"] == pytest.approx(2 * (900 * 1 + 3100 * 5) / 1e6)
    assert e["gasto_hoy_usd"] == fila["coste_usd"] and "segundos_p95" in fila


def test_presupuesto_diario_corta_las_llamadas(gemini, registro_limpio, monkeypatch):
    monkeypatch.setattr(llm, "PRESUPUESTO_DIARIO_USD", 0.01)
    monkeypatch.setitem(llm.PRECIOS, llm.GEMINI[llm.HAIKU], (1.0, 5.0))
    gemini(ANUNCIO_JSON)
    llm.parse("anuncio", llm.HAIKU, "s", "ficha", Anuncio)  # 0,0164 $: pasa del tope
    with pytest.raises(llm.PresupuestoAgotado):
        llm.parse("anuncio", llm.HAIKU, "s", "ficha", Anuncio)


def test_el_gasto_se_reinicia_cada_dia(registro_limpio, monkeypatch):
    monkeypatch.setattr(llm, "_gasto", {"dia": llm.date(2000, 1, 1), "usd": 5.0})
    assert llm.gasto_hoy() == 0.0
