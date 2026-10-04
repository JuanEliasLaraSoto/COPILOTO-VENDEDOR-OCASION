import httpx

from copiloto import red


def test_reintenta_en_modo_compatible(monkeypatch):
    intentos = []

    def get_falso(url, **kwargs):
        intentos.append(kwargs.get("verify"))
        if len(intentos) == 1:
            raise httpx.ConnectError("EOF occurred in violation of protocol")
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get_falso)
    assert red.get("https://ejemplo.es").json() == {"ok": True}
    assert intentos[0] is None and intentos[1] is not None  # 2.º intento con TLS 1.2
