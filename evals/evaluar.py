"""Evalúa anuncios y respuestas con la API de verdad (cuesta unos céntimos).

Uso:
    uv run python evals/evaluar.py                  # modelo rápido (HAIKU)
    uv run python evals/evaluar.py --modelo listo   # modelo potente (SONNET)

Mide lo que importa en un concesionario: que la IA no invente nada.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from copiloto import llm
from copiloto.anuncio import generar_anuncio
from copiloto.respuestas import responder
from copiloto.vehiculo import cargar_stock

CARPETA = Path(__file__).parent
ANUNCIOS = ["VO-002", "VO-004", "VO-008", "VO-011", "VO-013", "VO-018", "VO-024", "VO-016"]


def evaluar(modelo: str) -> dict:
    stock = cargar_stock()
    coste = segundos = 0.0
    fallos = []

    # 1) Anuncios: ¿cuántos salen sin cifras ni promesas inventadas?
    limpios = descartados = 0
    for id_ in ANUNCIOS:
        r, ll = generar_anuncio(stock[id_], modelo)
        coste, segundos = coste + ll.coste_usd, segundos + ll.segundos
        limpios += r["listo_para_publicar"]
        descartados += len(r["destacados_descartados"])
        for campo, avisos in r["avisos"].items():
            fallos += [f"anuncio {id_}.{campo}: {a}" for a in avisos]

    # 2) Respuestas: sin invenciones, y las preguntas trampa deben quedar «pendientes».
    preguntas = [json.loads(x) for x in (CARPETA / "preguntas.jsonl").read_text().splitlines() if x]
    sin_avisos = trampas_ok = trampas = 0
    for p in preguntas:
        r, ll = responder(stock[p["coche"]], p["mensaje"], modelo)
        coste, segundos = coste + ll.coste_usd, segundos + ll.segundos
        sin_avisos += r["listo_para_enviar"]
        fallos += [f"respuesta {p['id']}: {a}" for a in r["avisos"]]
        if p["trampa"]:
            trampas += 1
            if r["pendiente_de_consultar"]:
                trampas_ok += 1
            else:
                fallos.append(f"respuesta {p['id']}: no lo marcó como pendiente")

    llamadas = len(ANUNCIOS) + len(preguntas)
    return {
        "modelo": modelo,
        "anuncios_sin_invenciones_pct": round(100 * limpios / len(ANUNCIOS), 1),
        "destacados_descartados": descartados,
        "respuestas_sin_invenciones_pct": round(100 * sin_avisos / len(preguntas), 1),
        "trampas_marcadas_pendientes_pct": round(100 * trampas_ok / trampas, 1),
        "coste_medio_usd": round(coste / llamadas, 5),
        "segundos_medios": round(segundos / llamadas, 2),
        "fallos": fallos,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--modelo", choices=["rapido", "listo"], default="rapido")
    args = parser.parse_args()
    resultado = evaluar(llm.HAIKU if args.modelo == "rapido" else llm.SONNET)
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
    carpeta = CARPETA / "resultados"
    carpeta.mkdir(exist_ok=True)
    nombre = f"{datetime.now():%Y%m%d-%H%M}-{args.modelo}.json"
    (carpeta / nombre).write_text(json.dumps(resultado, indent=2, ensure_ascii=False))
