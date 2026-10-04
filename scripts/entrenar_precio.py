"""Entrena el modelo de precio, lo compara con el baseline y registra todo en MLflow.

Uso:
    uv run python scripts/entrenar_precio.py data/coches.csv
"""

import json
import sys
from datetime import date
from pathlib import Path

import mlflow
import numpy as np
from sklearn.model_selection import train_test_split

from copiloto.datos import cargar, limpiar
from copiloto.precio import ModeloPrecio, baseline, metricas

# Traduce las columnas del CSV (izquierda, tal cual aparecen) a las internas (derecha).
# Son las del dataset de Zenodo de Barcelona 2022. Si usas otro, cámbialas tras mirar df.columns.
MAPA_COLUMNAS = {
    "brand": "marca",
    "model": "modelo",
    "year": "anio",
    "mileage (kms)": "km",
    "fuel": "combustible",
    "gearbox": "cambio",
    "engine": "motor",  # de aquí se saca la potencia ("90cv")
    "price (eur)": "precio",
}

PARAMS = {"max_iter": 300, "learning_rate": 0.05, "max_leaf_nodes": 31, "min_samples_leaf": 10}
RUTA_METRICAS = Path("modelos/metricas.json")  # la web las enseña en «Modelo de precios»


def evaluar(df):
    """Entrena con el 80 % y mide con el 20 % que el modelo no ha visto.

    Devuelve (resultados, test con la estimación de cada coche, filas de entrenamiento).
    """
    train, test = train_test_split(df, test_size=0.2, random_state=42)
    m_base = metricas(test["precio"], baseline(train, test))
    pred = ModeloPrecio.entrenar(train, **PARAMS).predecir(test)
    m_gb = metricas(test["precio"], pred["precio_estimado"])
    cobertura = float(np.mean(test["precio"].between(pred["rango_min"], pred["rango_max"])) * 100)
    resultados = {
        "baseline_mae": m_base["mae"],
        "baseline_mape": m_base["mape"],
        "gb_mae": m_gb["mae"],
        "gb_mape": m_gb["mape"],
        "cobertura_rango_pct": round(cobertura, 1),
    }
    test = test.assign(
        estimado=pred["precio_estimado"],
        rango_min=pred["rango_min"],
        rango_max=pred["rango_max"],
        error_pct=(pred["precio_estimado"] - test["precio"]).abs() / test["precio"] * 100,
    )
    return resultados, test, len(train)


def guardar_metricas(resultados: dict, test, filas_train: int, ruta: Path = RUTA_METRICAS) -> None:
    """Resumen para la web: métricas, error por combustible y cada coche del test."""
    por_combustible = test.groupby("combustible", dropna=False)["error_pct"].agg(["mean", "count"])
    datos = {
        "fecha": date.today().isoformat(),
        "filas_train": filas_train,
        "filas_test": len(test),
        "cobertura_objetivo_pct": 80,
        **resultados,
        "error_por_combustible": [
            {
                "combustible": str(c),
                "error_pct": round(float(f["mean"]), 1),
                "coches": int(f["count"]),
            }
            for c, f in por_combustible.sort_values("mean").iterrows()
        ],
        "muestra": [
            {
                "marca": f.marca,
                "modelo": f.modelo,
                "anio": int(f.anio),
                "km": int(f.km),
                "real": int(f.precio),
                "estimado": int(f.estimado),
                "rango_min": int(f.rango_min),
                "rango_max": int(f.rango_max),
            }
            for f in test.itertuples()
        ],
    }
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


def main(ruta_csv: str) -> None:
    df = limpiar(cargar(ruta_csv, MAPA_COLUMNAS), anio_actual=date.today().year)

    mlflow.set_experiment("precio-coches")
    with mlflow.start_run():
        resultados, test, filas_train = evaluar(df)
        print(f"Entrenamiento: {filas_train} filas · Test: {len(test)} filas")
        mlflow.log_params(
            {**PARAMS, "filas_train": filas_train, "filas_test": len(test), "dataset": ruta_csv}
        )
        mlflow.log_metrics(resultados)
        print(json.dumps(resultados, indent=2))

        # Error por segmento: ¿dónde se equivoca más el modelo?
        print("\nError medio (%) por combustible:")
        print(test.groupby("combustible", dropna=False)["error_pct"].mean().round(1).to_string())

        guardar_metricas(resultados, test, filas_train)
        mlflow.log_artifact(str(RUTA_METRICAS))

        # El modelo final se entrena con todos los datos.
        ModeloPrecio.entrenar(df, **PARAMS).guardar()
        mlflow.log_artifact("modelos/precio.joblib")
        print("\nModelo guardado en modelos/precio.joblib")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/coches.csv")
