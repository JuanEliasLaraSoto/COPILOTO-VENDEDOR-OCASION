"""Modelo de precio de mercado: baseline, gradient boosting y rango calibrado (conformal)."""

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

CATEGORICAS = ["marca", "modelo", "combustible", "cambio"]
NUMERICAS = ["anio", "km", "potencia_cv"]
FEATURES = CATEGORICAS + NUMERICAS
RUTA_MODELO = Path("modelos/precio.joblib")


def _pipeline(categoricas: list[str], **params) -> Pipeline:
    """Codifica las categóricas como enteros y entrena un gradient boosting sobre log(precio)."""
    codificador = ColumnTransformer(
        [
            (
                "cat",
                OrdinalEncoder(
                    handle_unknown="use_encoded_value",
                    unknown_value=-1,
                    encoded_missing_value=-1,
                    max_categories=250,
                ),
                categoricas,
            )
        ],
        remainder="passthrough",
    )
    modelo = HistGradientBoostingRegressor(
        categorical_features=list(range(len(categoricas))), random_state=42, **params
    )
    return Pipeline([("codificador", codificador), ("modelo", modelo)])


def baseline(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Mediana de precio por marca, modelo y año; si no hay, por marca y modelo; si no, global."""
    claves = [["marca", "modelo", "anio"], ["marca", "modelo"]]
    pred = pd.Series(np.nan, index=test.index)
    for k in claves:
        medianas = train.groupby(k)["precio"].median().rename("m")
        pred = pred.fillna(test.join(medianas, on=k)["m"])
    return pred.fillna(train["precio"].median()).to_numpy()


def metricas(y_real, y_pred) -> dict[str, float]:
    return {
        "mae": round(float(mean_absolute_error(y_real, y_pred)), 1),
        "mape": round(float(mean_absolute_percentage_error(y_real, y_pred)) * 100, 2),
    }


@dataclass
class ModeloPrecio:
    central: Pipeline
    margen_log: float  # semiancho del rango en escala logarítmica
    features: list[str]
    cobertura: float = 0.80

    @classmethod
    def entrenar(cls, df: pd.DataFrame, cobertura: float = 0.80, **params) -> "ModeloPrecio":
        """Entrena el modelo y calcula un rango de precio con conformal prediction.

        Se separa un 20 % de los datos (calibración): el margen es el percentil `cobertura`
        de los errores absolutos en log sobre esos datos. Así, ~80 % de los precios reales
        caen dentro del rango.
        """
        features = [f for f in FEATURES if df[f].notna().any()]  # solo columnas con datos
        cats = [f for f in CATEGORICAS if f in features]
        train, calib = train_test_split(df, test_size=0.2, random_state=42)

        modelo = _pipeline(cats, **params).fit(train[features], np.log(train["precio"]))
        errores = np.abs(np.log(calib["precio"]) - modelo.predict(calib[features]))
        margen = float(np.quantile(errores, cobertura))

        # Modelo final con todos los datos; el margen calibrado se mantiene.
        final = _pipeline(cats, **params).fit(df[features], np.log(df["precio"]))
        return cls(final, margen, features, cobertura)

    def predecir(self, df: pd.DataFrame) -> pd.DataFrame:
        log_pred = self.central.predict(df[self.features])
        return pd.DataFrame(
            {
                "precio_estimado": np.exp(log_pred),
                "rango_min": np.exp(log_pred - self.margen_log),
                "rango_max": np.exp(log_pred + self.margen_log),
            },
            index=df.index,
        ).round(0)

    def guardar(self, ruta: Path = RUTA_MODELO) -> None:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, ruta)

    @staticmethod
    def cargar(ruta: Path = RUTA_MODELO) -> "ModeloPrecio":
        return joblib.load(ruta)


def valorar(modelo: ModeloPrecio, coche: dict) -> dict:
    """Estimación para un coche y cuánto se desvía su precio anunciado."""
    fila = pd.DataFrame([{c: coche.get(c) for c in FEATURES}])
    fila[NUMERICAS] = fila[NUMERICAS].astype("float")
    fila[CATEGORICAS] = fila[CATEGORICAS].astype("object")
    est = modelo.predecir(fila).iloc[0].to_dict()
    precio = coche.get("precio")
    if precio:
        est["desviacion_pct"] = round(
            (precio - est["precio_estimado"]) / est["precio_estimado"] * 100, 1
        )
        est["veredicto"] = (
            "por debajo del rango"
            if precio < est["rango_min"]
            else "por encima del rango"
            if precio > est["rango_max"]
            else "dentro del rango normal"
        )
    return est
