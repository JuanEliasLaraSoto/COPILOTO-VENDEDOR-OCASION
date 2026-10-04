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

## Datos

- Stock: **ficticio**, creado para la demo.
- Precios de coches para el modelo: _(nombre del dataset, autores, licencia y fecha)_.
- Carburantes: datos abiertos del Ministerio. Electricidad: API REData de Red Eléctrica.

Proyecto personal de portfolio, no oficial. Resultados orientativos.
