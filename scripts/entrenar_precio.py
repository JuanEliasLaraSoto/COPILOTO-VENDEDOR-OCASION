"""Entrena el modelo de precio, lo compara con el baseline y registra todo en MLflow.

Uso:
    uv run python scripts/entrenar_precio.py data/coches.csv
"""

import json
import sys
from datetime import date

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


def main(ruta_csv: str) -> None:
    df = limpiar(cargar(ruta_csv, MAPA_COLUMNAS), anio_actual=date.today().year)
    train, test = train_test_split(df, test_size=0.2, random_state=42)
    print(f"Entrenamiento: {len(train)} filas · Test: {len(test)} filas")

    mlflow.set_experiment("precio-coches")
    with mlflow.start_run():
        mlflow.log_params(
            {**PARAMS, "filas_train": len(train), "filas_test": len(test), "dataset": ruta_csv}
        )

        m_base = metricas(test["precio"], baseline(train, test))
        modelo = ModeloPrecio.entrenar(train, **PARAMS)
        pred = modelo.predecir(test)
        m_gb = metricas(test["precio"], pred["precio_estimado"])
        cobertura = float(
            np.mean(test["precio"].between(pred["rango_min"], pred["rango_max"])) * 100
        )

        resultados = {
            "baseline_mae": m_base["mae"],
            "baseline_mape": m_base["mape"],
            "gb_mae": m_gb["mae"],
            "gb_mape": m_gb["mape"],
            "cobertura_rango_pct": round(cobertura, 1),
        }
        mlflow.log_metrics(resultados)
        print(json.dumps(resultados, indent=2))

        # Error por segmento: ¿dónde se equivoca más el modelo?
        test = test.assign(
            error_pct=(pred["precio_estimado"] - test["precio"]).abs() / test["precio"] * 100
        )
        print("\nError medio (%) por combustible:")
        print(test.groupby("combustible", dropna=False)["error_pct"].mean().round(1).to_string())

        # El modelo final se entrena con todos los datos.
        ModeloPrecio.entrenar(df, **PARAMS).guardar()
        mlflow.log_artifact("modelos/precio.joblib")
        print("\nModelo guardado en modelos/precio.joblib")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/coches.csv")
