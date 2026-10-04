"""Graba el vídeo de LinkedIn de Copiloto VO: recorrido por la web, a 2×, con música.

Usa la IA de verdad (Claude o Gemini, según PROVEEDOR) y los precios reales del día
(Ministerio y Red Eléctrica). Si falta la clave o alguna API da el precio de reserva,
se para antes de grabar: un vídeo con «precio de RESERVA» o errores de la IA no sirve.

    uv run --with playwright python scripts/grabar_video.py
    uv run --with playwright python scripts/grabar_video.py --musica mi_tema.mp3
    uv run --with playwright python scripts/grabar_video.py --ensayo   # sin IA, para probar

La primera vez: `uv run --with playwright playwright install chromium`.
Necesita ffmpeg en el PATH. La música por defecto se genera aquí mismo (sin derechos de autor).
"""

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import httpx
import numpy as np
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
PUERTO = 8765
URL = f"http://127.0.0.1:{PUERTO}"
ANCHO, ALTO = 1920, 1080
ZOOM = 1.5  # la web se ve como en una pantalla de 1280×720: letra legible en el móvil
VELOCIDAD = 2  # el vídeo final va al doble de rápido: las pausas de aquí se ven a la mitad
COCHE = "VO-002"  # Mercedes Clase C diésel con 71 días en stock: da juego en precio y alertas
MENSAJE = "Hola, ¿tiene libro de revisiones? ¿Cuántos dueños ha tenido? ¿Me lo dejas en 25.000?"
ENLACE = "github.com/JuanEliasLaraSoto/COPILOTO-VENDEDOR-OCASION"


# ---------- Comprobaciones antes de grabar ----------
def comprobar_ia() -> str:
    """Devuelve el proveedor si hay clave; si no, para."""
    proveedor = os.getenv("PROVEEDOR", "claude").strip().lower()
    clave = "GEMINI_API_KEY" if proveedor == "gemini" else "ANTHROPIC_API_KEY"
    if not os.getenv(clave):
        sys.exit(f"Falta {clave} (PROVEEDOR={proveedor}). Ponla en .env para grabar con IA real.")
    return proveedor


def comprobar_precios(provincia: str) -> dict:
    """Pide los precios de hoy a las APIs oficiales; para si alguno sale de reserva."""
    from copiloto.coste_anual import perfil_con_precios_reales

    perfil = perfil_con_precios_reales(15000, True, provincia)
    malos = [k for k, o in perfil.origen.items() if "RESERVA" in o]
    if malos:
        sys.exit(
            f"Sin precio real de hoy para: {', '.join(malos)}. Revisa la conexión con "
            "sedeaplicaciones.minetur.gob.es y apidatos.ree.es y vuelve a intentarlo."
        )
    return {
        "gasolina": perfil.precio_gasolina,
        "diesel": perfil.precio_diesel,
        "luz": perfil.precio_kwh_casa,
    }


# ---------- Servidor ----------
def arrancar_servidor() -> subprocess.Popen:
    servidor = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "copiloto.api:app", "--port", str(PUERTO)],
        cwd=RAIZ,
        # Un hilo para el modelo: con el navegador grabando, varios hilos se estorban y va lentísimo
        env={**os.environ, "OMP_NUM_THREADS": "1"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    for _ in range(60):
        try:
            if httpx.get(f"{URL}/health", timeout=1).status_code == 200:
                httpx.get(f"{URL}/alertas", timeout=120)  # carga el modelo antes de grabar
                return servidor
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    servidor.kill()
    sys.exit("El servidor no ha arrancado. Prueba a mano: uv run uvicorn copiloto.api:app")


# ---------- Música ----------
def nota(n: int) -> float:
    """Frecuencia de la nota MIDI n."""
    return 440.0 * 2 ** ((n - 69) / 12)


def generar_musica(segundos: float, destino: Path, bpm: int = 112) -> None:
    """Tema electrónico suave y optimista (La m – Fa – Do – Sol), sintetizado con numpy."""
    sr = 44100
    total = int(segundos * sr) + sr
    t_beat = 60 / bpm
    compas = 4 * t_beat
    mezcla = np.zeros(total)
    acordes = [(57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62)]  # Am F C G
    bajos = [45, 41, 36, 43]

    def env(n, ataque, caida):
        e = np.ones(n)
        a = min(n, int(ataque * sr))
        e[:a] = np.linspace(0, 1, a)
        return e * np.exp(-np.arange(n) / (caida * sr))

    def poner(senal, inicio):
        i = int(inicio * sr)
        if i >= total:
            return
        fin = min(total, i + len(senal))
        mezcla[i:fin] += senal[: fin - i]

    n_compases = math.ceil(segundos / compas) + 1
    for c in range(n_compases):
        t0 = c * compas
        acorde, bajo = acordes[c % 4], bajos[c % 4]
        # Colchón: tres osciladores un poco desafinados por nota
        n = int(compas * sr)
        tt = np.arange(n) / sr
        pad = sum(
            np.sin(2 * np.pi * nota(m) * (1 + d) * tt) for m in acorde for d in (-0.003, 0, 0.003)
        )
        poner(0.035 * pad * env(n, 0.4, 6.0), t0)
        for b in range(4):  # bajo, bombo y charles en cada pulso
            tb = t0 + b * t_beat
            nb = int(t_beat * sr)
            tt = np.arange(nb) / sr
            poner(0.18 * np.sin(2 * np.pi * nota(bajo) * tt) * env(nb, 0.01, 0.25), tb)
            nk = int(0.3 * sr)
            tk = np.arange(nk) / sr
            fase = 2 * np.pi * np.cumsum(50 + 90 * np.exp(-tk * 30)) / sr
            if c >= 1:  # el primer compás, solo colchón
                poner(0.5 * np.sin(fase) * np.exp(-tk * 9), tb)
                nh = int(0.05 * sr)
                ruido = np.diff(np.random.default_rng(c * 4 + b).standard_normal(nh + 1))
                poner(0.05 * ruido * np.exp(-np.arange(nh) / (0.012 * sr)), tb + t_beat / 2)
        # Arpegio de corcheas a partir del tercer compás
        if c >= 2:
            notas = [acorde[0] + 12, acorde[1] + 12, acorde[2] + 12, acorde[1] + 12] * 2
            for k, m in enumerate(notas):
                na = int(t_beat / 2 * sr)
                ta = np.arange(na) / sr
                pluck = np.sin(2 * np.pi * nota(m) * ta) + 0.3 * np.sin(4 * np.pi * nota(m) * ta)
                poner(0.06 * pluck * env(na, 0.005, 0.12), t0 + k * t_beat / 2)

    mezcla = mezcla[: int(segundos * sr)]
    mezcla /= max(1e-9, np.abs(mezcla).max()) / 0.85
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((mezcla * 32767).astype(np.int16).tobytes())


# ---------- Grabación ----------
ESTILO_GRABACION = """
#cursor-falso { position: fixed; width: 22px; height: 22px; margin: -11px 0 0 -11px; z-index: 99999;
  border-radius: 50%; background: rgba(230, 60, 40, .35); border: 2px solid rgba(230, 60, 40, .9);
  pointer-events: none; transition: transform .12s; left: -50px; top: -50px; }
#cursor-falso.pulsa { transform: scale(.6); }
#rotulo { position: fixed; left: 50%; bottom: 26px; transform: translateX(-50%); z-index: 99998;
  background: #111; color: #fff; font: 600 24px/1.2 system-ui, sans-serif; padding: 12px 24px;
  border-radius: 14px; box-shadow: 0 10px 30px rgba(0,0,0,.35); pointer-events: none;
  opacity: 0; transition: opacity .3s; max-width: 80%; text-align: center; }
#rotulo.ver { opacity: 1; }
#rotulo small { display: block; font-weight: 400; font-size: 16px; opacity: .8; margin-top: 4px; }
#tarjeta { position: fixed; inset: 0; z-index: 100000; display: grid; place-items: center;
  background: #f6f1e7; font-family: system-ui, sans-serif; color: #151515;
  transition: opacity .6s; }
#tarjeta.fuera { opacity: 0; }
#tarjeta .c { text-align: center; animation: entra .8s ease-out; }
@keyframes entra { from { opacity: 0; transform: translateY(20px); } }
#tarjeta .pegatina { display: inline-block; background: #ffd23f; border: 4px solid #151515;
  border-radius: 18px; padding: 10px 26px; font-size: 28px; font-weight: 800;
  transform: rotate(-2deg); box-shadow: 8px 8px 0 #151515; margin-bottom: 28px; }
#tarjeta h1 { font-size: 56px; line-height: 1.1; margin: 0 0 18px; letter-spacing: -1.5px; }
#tarjeta p { font-size: 26px; margin: 10px 0; color: #333; }
#tarjeta .chips { margin-top: 32px; display: flex; gap: 12px; justify-content: center;
  flex-wrap: wrap; }
#tarjeta .chips span { border: 3px solid #151515; border-radius: 999px; padding: 6px 16px;
  font-size: 19px; background: #fff; }
#tarjeta .pie { font-size: 17px; color: #666; margin-top: 40px; }
"""

# El cursor va dentro de la página con zoom: su posición se divide entre ZOOM.
SCRIPT_GRABACION = """
window.addEventListener('DOMContentLoaded', () => {
  const z = ZOOM; document.documentElement.style.zoom = z;
  const s = document.createElement('style'); s.textContent = ESTILO; document.head.append(s);
  const c = document.createElement('div'); c.id = 'cursor-falso'; document.body.append(c);
  const r = document.createElement('div'); r.id = 'rotulo'; document.body.append(r);
  addEventListener('mousemove', (e) => {
    c.style.left = e.clientX / z + 'px'; c.style.top = e.clientY / z + 'px'; });
  addEventListener('mousedown', () => c.classList.add('pulsa'));
  addEventListener('mouseup', () => c.classList.remove('pulsa'));
});
""".replace("ZOOM", str(ZOOM)).replace("ESTILO", json.dumps(ESTILO_GRABACION))


def tarjeta(page, contenido: str) -> None:
    """Portada o cierre a pantalla completa, encima de la web."""
    page.evaluate(
        """(html) => { document.getElementById('rotulo').classList.remove('ver');
           const t = document.createElement('div'); t.id = 'tarjeta';
           t.innerHTML = `<div class="c">${html}</div>`; document.body.append(t); }""",
        contenido,
    )


def quitar_tarjeta(page) -> None:
    page.evaluate("document.getElementById('tarjeta').classList.add('fuera')")
    pausa(page, 0.7)
    page.evaluate("document.getElementById('tarjeta').remove()")


def pausa(page, segundos: float) -> None:
    page.wait_for_timeout(int(segundos * 1000))


def rotulo(page, titulo: str, sub: str = "") -> None:
    page.evaluate(
        """([t, s]) => { const r = document.getElementById('rotulo');
           r.innerHTML = ''; r.append(t);
           if (s) { const e = document.createElement('small'); e.textContent = s; r.append(e); }
           r.classList.add('ver'); }""",
        [titulo, sub],
    )


def clic(page, selector: str, espera: float = 0.6) -> None:
    el = page.locator(selector).first
    el.scroll_into_view_if_needed()
    caja = el.bounding_box()
    page.mouse.move(caja["x"] + caja["width"] / 2, caja["y"] + caja["height"] / 2, steps=25)
    pausa(page, 0.3)
    el.click()
    pausa(page, espera)


def desplazar(page, px: int, pasos: int = 30, segundos: float = 2.0) -> None:
    for _ in range(pasos):
        page.mouse.wheel(0, px / pasos)
        pausa(page, segundos / pasos)


def ir(page, seccion: str) -> None:
    clic(page, f'#pestanas button[data-id="{seccion}"]', 1.0)


def esperar_resultado(page, destino: str, ensayo: bool) -> None:
    """Espera a que la IA o la API terminen; si sale un error, para la grabación."""
    page.wait_for_function(
        f"!document.querySelector('#{destino} .cargando') && "
        f"document.querySelector('#{destino}').childElementCount > 0",
        timeout=120_000,
    )
    texto = page.locator(f"#{destino}").inner_text()
    if not ensayo and ("Error:" in texto or "RESERVA" in texto):
        raise RuntimeError(f"Resultado no válido en #{destino}: {texto[:300]}")


def grabar(carpeta: Path, ensayo: bool, precios: dict | None) -> Path:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        opciones = {}
        if os.getenv("CHROMIUM_PATH"):
            opciones["executable_path"] = os.environ["CHROMIUM_PATH"]
        navegador = p.chromium.launch(**opciones)
        contexto = navegador.new_context(
            viewport={"width": ANCHO, "height": ALTO},
            record_video_dir=str(carpeta),
            record_video_size={"width": ANCHO, "height": ALTO},
            locale="es-ES",
            color_scheme="light",
        )
        contexto.add_init_script(SCRIPT_GRABACION)
        page = contexto.new_page()

        # 1. Portada, encima de la web mientras carga el stock y las alertas
        page.goto(f"{URL}/#inicio", wait_until="domcontentloaded")
        tarjeta(
            page,
            '<div class="pegatina">Copiloto VO</div>'
            "<h1>El copiloto del vendedor<br>de coches de ocasión</h1>"
            "<p>La IA redacta. El código comprueba.</p>",
        )
        page.wait_for_function("document.querySelectorAll('#kpis > *').length > 0")
        page.wait_for_selector("#panelAtencion .cargando", state="detached", timeout=60_000)
        page.evaluate(f"elegir(POR_ID['{COCHE}'])")
        pausa(page, 2)

        # 2. Panel
        quitar_tarjeta(page)
        rotulo(
            page, "Tu stock de un vistazo", "Alertas del modelo de precios: qué coche pide atención"
        )
        pausa(page, 4)
        desplazar(page, 500)
        pausa(page, 2.5)

        # 3. Precio con ML
        ir(page, "precio")
        rotulo(
            page, "Precio recomendado con machine learning", "Gradient boosting + rango calibrado"
        )
        clic(page, "#btnPrecio")
        esperar_resultado(page, "resPrecio", ensayo)
        pausa(page, 3)
        desplazar(page, 450)
        pausa(page, 3)

        # 4. Anuncio con IA
        ir(page, "anuncio")
        rotulo(page, "La IA escribe el anuncio…", "…y el código revisa cada cifra contra la ficha")
        if ensayo:
            pausa(page, 3)
        else:
            clic(page, "#btnAnuncio")
            esperar_resultado(page, "resAnuncio", ensayo)
            pausa(page, 3)
            desplazar(page, 600, segundos=3)
            pausa(page, 3)

        # 5. Respuesta a un cliente con IA
        ir(page, "cliente")
        rotulo(
            page,
            "Un cliente pregunta por WhatsApp",
            "Solo responde con lo que dice la ficha; lo demás, «pendiente»",
        )
        clic(page, "#mensaje", 0.3)
        page.keyboard.type(MENSAJE, delay=25)
        pausa(page, 1)
        if ensayo:
            pausa(page, 2)
        else:
            clic(page, "#btnRespuesta")
            esperar_resultado(page, "resRespuesta", ensayo)
            pausa(page, 3)
            desplazar(page, 500, segundos=3)
            pausa(page, 3)

        # 6. Coste por motor con precios de hoy
        ir(page, "coste")
        sub = "Carburantes del Ministerio y luz de Red Eléctrica"
        if precios:
            sub = (
                f"Hoy: gasolina {precios['gasolina']:.3f} €/L · diésel {precios['diesel']:.3f} €/L"
                f" · luz {precios['luz']:.3f} €/kWh"
            ).replace(".", ",")
        rotulo(page, "Gasolina, diésel o eléctrico: ¿qué sale más barato?", sub)
        clic(page, "#btnCoste")
        esperar_resultado(page, "resCoste", ensayo)
        pausa(page, 2)
        desplazar(page, 650, segundos=3)
        pausa(page, 4)

        # 7. Financiación en vivo
        ir(page, "financiacion")
        rotulo(
            page,
            "Financiación al momento",
            "Cuota, TAE y entrada necesaria mientras hablas con el cliente",
        )
        clic(page, "#finUsarCoche", 1)
        deslizador = page.locator("#fMesesR")
        caja = deslizador.bounding_box()
        y = caja["y"] + caja["height"] / 2
        page.mouse.move(caja["x"] + caja["width"] * 0.45, y, steps=20)
        page.mouse.down()
        page.mouse.move(caja["x"] + caja["width"] * 0.85, y, steps=40)
        page.mouse.move(caja["x"] + caja["width"] * 0.25, y, steps=50)
        page.mouse.up()
        pausa(page, 3)

        # 8. Cierre
        tarjeta(
            page,
            '<div class="pegatina">Copiloto VO</div>'
            "<h1>El LLM entiende y redacta.<br>El ML estima. El código verifica.</h1>"
            '<div class="chips"><span>Precio con ML</span><span>Anuncios con IA verificada</span>'
            "<span>Respuestas a clientes</span><span>Precios oficiales de hoy</span>"
            "<span>Financiación</span></div>"
            f'<p class="pie">{ENLACE} · Proyecto personal de portfolio</p>',
        )
        pausa(page, 8)

        video = page.video.path()
        contexto.close()
        navegador.close()
    return Path(video)


# ---------- Montaje ----------
def duracion(fichero: Path) -> float:
    salida = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", fichero],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(salida.stdout.strip())


def montar(crudo: Path, musica: Path | None, salida: Path, carpeta: Path) -> None:
    final = (duracion(crudo) - 0.3) / VELOCIDAD  # se quitan los primeros fotogramas en blanco
    if musica is None:
        musica = carpeta / "musica.wav"
        generar_musica(final, musica)
    fundido = max(0.0, final - 2.5)
    filtro = (
        f"[0:v]setpts=PTS/{VELOCIDAD},fps=30,format=yuv420p[v];"
        f"[1:a]atrim=0:{final:.2f},afade=t=in:d=1,afade=t=out:st={fundido:.2f}:d=2.5,"
        "volume=0.9[a]"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-ss",
            "0.3",
            "-i",
            crudo,
            "-stream_loop",
            "-1",
            "-i",
            musica,
            "-filter_complex",
            filtro,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-t",
            f"{final:.2f}",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "20",
            "-profile:v",
            "high",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            salida,
        ],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--salida", type=Path, default=RAIZ / "video" / "copiloto-vo-linkedin.mp4")
    parser.add_argument("--musica", type=Path, help="tu propio tema (mp3/wav); si no, se genera")
    parser.add_argument("--provincia", default="Málaga")
    parser.add_argument(
        "--ensayo",
        action="store_true",
        help="graba sin IA y acepta precios de reserva, solo para probar el recorrido",
    )
    args = parser.parse_args()

    load_dotenv(RAIZ / ".env")
    sys.path.insert(0, str(RAIZ / "src"))
    if not shutil.which("ffmpeg"):
        sys.exit("Falta ffmpeg. Instálalo (apt install ffmpeg / brew install ffmpeg).")
    precios = None
    if not args.ensayo:
        print(f"IA: {comprobar_ia()}")
        precios = comprobar_precios(args.provincia)
        print(f"Precios de hoy en {args.provincia}: {precios}")

    servidor = arrancar_servidor()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = Path(tmp)
            print("Grabando el recorrido…")
            crudo = grabar(carpeta, args.ensayo, precios)
            print("Montando a 2× con música…")
            args.salida.parent.mkdir(parents=True, exist_ok=True)
            montar(crudo, args.musica, args.salida, carpeta)
    finally:
        servidor.terminate()
    print(f"Listo: {args.salida} ({duracion(args.salida):.0f} s)")


if __name__ == "__main__":
    main()
