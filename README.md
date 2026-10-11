# Copiloto del vendedor de vehículos de ocasión

Herramienta para el día a día de un vendedor de coches de ocasión: precio, anuncios,
respuestas a clientes, tasaciones, coste por tipo de motor, recomendaciones de stock
y financiación. **La IA redacta; el código comprueba.**

**Demo:** https://TU-SERVICIO.onrender.com

## Qué hace

| Función | Cómo |
|---|---|
| Precio recomendado | Gradient boosting (scikit-learn) + rango calibrado (conformal prediction) |
| Alertas de stock | Reglas: días en stock frente a desviación del precio de mercado |
| Anuncio automático | LLM + verificación: cifras, promesas y destacados contrastados con la ficha |
| Respuestas a clientes | LLM con router (modelo rápido o potente) + verificación; lo desconocido queda «pendiente» |
| Tasación | LLM extrae los daños de las notas (con citas verificadas) + cálculo de la oferta |
| Coste por motor | Consumo WLTP de la ficha + precios oficiales (Ministerio y Red Eléctrica) + punto de equilibrio |
| Recomendador de stock | LLM entiende al cliente (con citas) + puntuación por reglas explicables |
| Financiación | Sistema francés y TAE por bisección |
| Simulador de precio y margen | Mueve el precio y ve al momento el rango, el veredicto y tu margen bruto (sin volver a llamar al servidor) |
| Comparador cara a cara | Hasta 3 coches en columnas; la mejor cifra de cada fila, marcada |
| Ficha para el cliente y cartel | Hojas A4 y A5 listas para imprimir o guardar en PDF, con cuota mensual calculada |
| Historial de IA | Lo generado por la IA se guarda en el navegador: volver a verlo no gasta |
| Métricas del modelo | Error frente al baseline, cobertura del rango y gráfico real frente a estimado (`GET /modelo`, generado por `scripts/entrenar_precio.py`) |

Principio de diseño: **el LLM entiende y redacta; el ML estima; el código calcula y verifica.**
Funciona con Claude o con Gemini cambiando una variable (`PROVEEDOR`).

### Tokens, latencia y coste de la IA

Todas las llamadas pasan por `copiloto/llm.py`, que mide y controla:

- **Tokens**: entrada y salida de cada llamada (con Gemini, el razonamiento cuenta como salida).
- **Latencia**: segundos por llamada, `LLM_TIMEOUT_S` como tope y `LLM_REINTENTOS` ante errores pasajeros.
- **Coste**: dólares por llamada según el precio del modelo; router que usa el modelo rápido salvo en
  preguntas complejas; `PRESUPUESTO_DIARIO_USD` corta las llamadas al llegar al tope (HTTP 503) y
  20 usos por IP y hora protegen el saldo.
- **Observabilidad**: cada llamada sale en el log como JSON y `GET /uso-ia` da el resumen por tarea
  y modelo (tokens, latencia media y p95, coste medio, errores y gasto de hoy frente al presupuesto).
  La web enseña tokens, segundos y coste debajo de cada resultado.

## Resultados

_(Rellena con tus números de `scripts/entrenar_precio.py` y `evals/evaluar.py`.)_

| Métrica | Modelo rápido | Modelo potente |
|---|---|---|
| Anuncios sin invenciones | | |
| Respuestas sin invenciones | | |
| Preguntas trampa marcadas como pendientes | | |
| Coste medio por llamada | | |

## Ejecutar en local

```bash
uv sync
cp .env.example .env                   # y pon tu clave
uv run python scripts/entrenar_precio.py data/coches.csv
uv run uvicorn copiloto.api:app --reload
```

## Vídeo para LinkedIn

`scripts/grabar_video.py` recorre la web (panel, precio, anuncio y respuesta con IA, coste por
motor con los precios de hoy y financiación), la graba a 1080p, la acelera a 2× y le pone música
generada en el propio script (sin derechos de autor). Antes de grabar comprueba que hay clave de
la IA y que el Ministerio y Red Eléctrica dan el precio de hoy; si no, no graba.

```bash
uv run --with playwright playwright install chromium   # solo la primera vez (y ffmpeg instalado)
uv run --with playwright python scripts/grabar_video.py  # -> video/copiloto-vo-linkedin.mp4
uv run --with playwright python scripts/grabar_video.py --musica mi_tema.mp3  # tu propia música
```

## Datos

- Stock: **ficticio**, creado para la demo.
- Precios de coches para el modelo: _(nombre del dataset, autores, licencia y fecha)_.
- Carburantes: datos abiertos del Ministerio. Electricidad: API REData de Red Eléctrica.

Proyecto personal de portfolio, no oficial. Resultados orientativos.
