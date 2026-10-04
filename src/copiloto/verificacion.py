"""Comprobaciones con código de lo que escribe el LLM. Es la red de seguridad del proyecto.

Tres reglas sencillas:
1. Citas: cada dato sacado de un texto debe venir con la frase literal de la que sale.
2. Cifras: todo número de un texto generado tiene que existir en la ficha del coche.
3. Promesas: si el texto habla de garantía, libro de revisiones, propietarios o ITV,
   ese dato tiene que estar en la ficha.
"""

from pydantic import BaseModel

from copiloto.texto import cifras_sin_respaldo, normalizar
from copiloto.vehiculo import Vehiculo


class Cita(BaseModel):
    campo: str
    texto: str  # copiado literalmente del texto original


def campos_con_cita(citas: list[Cita], original: str) -> set[str]:
    """Campos cuya cita aparece de verdad (literalmente) en el texto original."""
    texto = normalizar(original)
    return {c.campo for c in citas if c.texto.strip() and normalizar(c.texto) in texto}


def anular_sin_cita(modelo: BaseModel, campos: list[str], original: str) -> tuple[dict, list[str]]:
    """Pone a None los campos rellenos sin una cita válida. Devuelve (datos, descartados)."""
    validos = campos_con_cita(modelo.citas, original)
    datos = modelo.model_dump()
    descartados = []
    for campo in campos:
        if datos[campo] is not None and datos[campo] != [] and campo not in validos:
            datos[campo] = None
            descartados.append(campo)
    datos["citas"] = [c for c in datos["citas"] if c["campo"] in validos]
    return datos, descartados


# Palabras que suponen una promesa al cliente -> qué campo de la ficha la respalda
PROMESAS = {
    "garantia": "garantia_meses",
    "libro": "libro_revisiones",
    "propietario": "propietarios",
    "dueno": "propietarios",
    "itv": "itv_hasta",
    "autonomia": "autonomia_electrica_km",
}


def promesas_sin_respaldo(texto: str, v: Vehiculo) -> list[str]:
    """Promesas que hace el texto y la ficha no respalda (dato vacío o en contra)."""
    t = normalizar(texto)
    notas = normalizar(v.notas)
    fallos = []
    for palabra, campo in PROMESAS.items():
        if palabra not in t:
            continue
        valor = getattr(v, campo)
        respaldado = bool(valor) or palabra in notas
        if campo == "libro_revisiones" and valor is False:
            # La ficha dice que NO tiene libro: solo vale si el texto también lo niega.
            antes = t[max(0, t.find("libro") - 25) : t.find("libro")]
            respaldado = " sin " in f" {antes}" or " no " in f" {antes}"
        if not respaldado:
            fallos.append(f"Menciona «{palabra}» pero la ficha no lo respalda")
    frases_un_dueno = ("unico propietario", "un solo propietario", "unico dueno", "un solo dueno")
    if any(f in t for f in frases_un_dueno) and v.propietarios != 1:
        fallos.append("Dice «un solo dueño» pero la ficha no dice 1 propietario")
    return fallos


def revisar_texto(texto: str, v: Vehiculo, otras_cifras: set[float] | None = None) -> list[str]:
    """Todos los avisos de un texto generado: cifras inventadas y promesas sin respaldo.

    `otras_cifras`: números que también se pueden repetir (p. ej. los que escribió el cliente).
    """
    permitidas = v.cifras_de_la_ficha() | (otras_cifras or set())
    avisos = [
        f"La cifra {c:g} no aparece en la ficha" for c in cifras_sin_respaldo(texto, permitidas)
    ]
    return avisos + promesas_sin_respaldo(texto, v)
