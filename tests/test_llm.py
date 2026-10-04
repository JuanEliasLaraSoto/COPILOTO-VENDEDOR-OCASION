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
