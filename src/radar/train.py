"""Entraînement et évaluation du modèle de risque de défaillance.

- découpage temporel (on teste sur les années d'observation les plus récentes) ;
- référence : régression logistique ; modèle principal : LightGBM ;
- calibration isotonique pour que le score soit une vraie probabilité ;
- métriques adaptées aux classes rares : ROC AUC, PR AUC, rappel au top 10 %.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .config import Config
from .features import model_features


def temporal_split(df: pd.DataFrame, test_years: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    years = sorted(df["annee_observation"].unique())
    if len(years) <= test_years:
        raise ValueError(f"Pas assez d'années d'observation pour un découpage temporel : {years}")
    cut = years[-test_years]
    train_df, test_df = df[df["annee_observation"] < cut], df[df["annee_observation"] >= cut]
    if test_df["defaillance"].sum() == 0 or len(test_df) < 1000:
        raise ValueError(
            f"Jeu de test inutilisable ({len(test_df)} lignes, {int(test_df['defaillance'].sum())} défaillances) : "
            "vérifier les dates des sources."
        )
    return train_df, test_df


def recall_at_top(y: np.ndarray, p: np.ndarray, share: float = 0.10) -> float:
    """Part des défaillances captées parmi les `share` entreprises les plus risquées."""
    if y.sum() == 0:
        return float("nan")
    k = max(1, int(len(p) * share))
    top = np.argsort(-p)[:k]
    return float(y[top].sum() / y.sum())


def evaluate(y: np.ndarray, p: np.ndarray) -> dict:
    return {
        "roc_auc": round(float(roc_auc_score(y, p)), 4),
        "pr_auc": round(float(average_precision_score(y, p)), 4),
        "brier": round(float(brier_score_loss(y, p)), 5),
        "recall_top10": round(recall_at_top(y, p), 4),
    }


def train(df: pd.DataFrame, cfg: Config) -> dict:
    feats = model_features(cfg)
    rs = cfg.model["random_state"]
    train_df, test_df = temporal_split(df, cfg.model["test_years"])
    X_tr, y_tr = train_df[feats], train_df["defaillance"].to_numpy()
    X_te, y_te = test_df[feats], test_df["defaillance"].to_numpy()
    pos_weight = (len(y_tr) - y_tr.sum()) / max(1, y_tr.sum())

    # Référence simple et explicable
    baseline = make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        LogisticRegression(max_iter=2000, class_weight="balanced"),
    )
    baseline.fit(X_tr, y_tr)

    # Modèle principal : gradient boosting (gère nativement les valeurs manquantes)
    params = dict(
        n_estimators=400, learning_rate=0.03, num_leaves=15, min_child_samples=40,
        subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
        scale_pos_weight=pos_weight, random_state=rs, verbose=-1,
    )
    booster = lgb.LGBMClassifier(**params)
    booster.fit(X_tr, y_tr)

    # Calibration sur le passé (validation croisée interne), jamais sur le test
    calibrated = CalibratedClassifierCV(lgb.LGBMClassifier(**params), method="isotonic", cv=3)
    calibrated.fit(X_tr, y_tr)

    metrics = {
        "baseline_logreg": evaluate(y_te, baseline.predict_proba(X_te)[:, 1]),
        "lightgbm": evaluate(y_te, booster.predict_proba(X_te)[:, 1]),
        "lightgbm_calibre": evaluate(y_te, calibrated.predict_proba(X_te)[:, 1]),
    }
    report = {
        "entraine_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "features": feats,
        "train": {"lignes": int(len(train_df)), "taux_defaillance": round(float(y_tr.mean()), 4),
                  "annees": sorted(int(a) for a in train_df["annee_observation"].unique())},
        "test": {"lignes": int(len(test_df)), "taux_defaillance": round(float(y_te.mean()), 4),
                 "annees": sorted(int(a) for a in test_df["annee_observation"].unique())},
        "metrics": metrics,
        "importance": dict(sorted(
            zip(feats, (int(v) for v in booster.feature_importances_)), key=lambda kv: -kv[1]
        )),
    }

    cfg.model_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "calibrated": calibrated,
            "booster": booster,
            "features": feats,
            "levels": cfg.model["levels"],
            # Médianes d'entraînement : servent à formuler les explications
            "medians": X_tr.median(numeric_only=True).to_dict(),
        },
        cfg.model_dir / "model.joblib",
    )
    with open(cfg.model_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report
