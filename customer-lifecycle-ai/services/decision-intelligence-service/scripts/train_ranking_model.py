"""Train LightGBM ranking model — Phase 2.

Generates synthetic training data from heuristic scorer,
trains LightGBM, saves model. Phase 4 retrains with real outcomes.
"""
from __future__ import annotations

import json, logging, os, sys, time
from datetime import date, datetime

import numpy as np
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app.context.builder import build_decision_context
from app.engines.action_generator import ActionGenerator
from app.engines.ranking_engine import RankingEngine

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("train_ranker")

TRAIN_CUSTOMERS = 100
FEATURES = [
    "health_score","churn_probability","clv_percentile","engagement_score",
    "tenure_months","age","days_since_last_txn","total_amount_90d",
    "has_salary_credit","txn_count_30d",
    "st_active","st_at_risk","st_dormant","st_churned",
    "act_retention","act_cross_sell","act_engagement","act_service","act_passive",
]

def context_to_features(ctx, action):
    eng = ctx.engagement_score or 50.0
    days = ctx.days_since_last_txn or 0
    amt = ctx.total_amount_90d or 0
    txn30 = ctx.txn_count_30d or 0
    sal = 1.0 if ctx.has_salary_credit else 0.0
    return [
        ctx.health_score, ctx.churn_probability, ctx.clv_percentile,
        eng, ctx.tenure_months, ctx.age, days, amt, sal, txn30,
        1.0 if ctx.customer_state=="ACTIVE" else 0.0,
        1.0 if ctx.customer_state=="AT_RISK" else 0.0,
        1.0 if ctx.customer_state=="DORMANT" else 0.0,
        1.0 if ctx.customer_state=="CHURNED" else 0.0,
        1.0 if action.category=="retention" else 0.0,
        1.0 if action.category=="cross_sell" else 0.0,
        1.0 if action.category=="engagement" else 0.0,
        1.0 if action.category=="service" else 0.0,
        1.0 if action.category=="passive" else 0.0,
    ]

def main():
    action_gen = ActionGenerator()
    heuristic = RankingEngine()
    all_actions = action_gen.generate()
    adate = date(2026,7,27)
    X_rows, y_rows = [], []

    logger.info("Generating training data from %d customers...", TRAIN_CUSTOMERS)
    for i in range(1, TRAIN_CUSTOMERS+1):
        cid = f"CUST{i:05d}"
        try:
            ctx = build_decision_context(cid, adate)
        except Exception:
            continue
        scored = heuristic.rank(all_actions, ctx, top_n=len(all_actions))
        for sa in scored:
            for ca in all_actions:
                if ca.action == sa.action:
                    X_rows.append(context_to_features(ctx, ca))
                    y_rows.append(sa.score / 100.0)
                    break
        if i % 100 == 0:
            logger.info("  %d/%d", i, TRAIN_CUSTOMERS)

    X = np.array(X_rows, dtype=np.float32)
    y = np.array(y_rows, dtype=np.float32)
    logger.info("Data: X=%s y=%s", X.shape, y.shape)

    X_tr, X_val, y_tr, y_val = train_test_split(X, y, test_size=0.2, random_state=42)
    t0 = time.perf_counter()
    model = lgb.LGBMRegressor(n_estimators=100, max_depth=6, learning_rate=0.05,
                               num_leaves=31, random_state=42, n_jobs=-1, verbosity=-1)
    model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)])
    dur = time.perf_counter() - t0
    yp = model.predict(X_val)
    mae = mean_absolute_error(y_val, yp)
    logger.info("Done in %.1fs. MAE: %.4f", dur, mae)

    out = "models/champion/ranking"
    os.makedirs(out, exist_ok=True)
    model.booster_.save_model(f"{out}/lgbm_ranker_v1.txt")
    meta = {"model_id":"lgbm_ranker_v1","type":"ranking","framework":"lightgbm",
            "version":1,"trained_at":datetime.now().isoformat(),
            "feature_columns":FEATURES,"n_features":len(FEATURES),
            "mae":float(mae),"samples":"synthetic_500"}
    with open(f"{out}/metadata.json","w") as f:
        json.dump(meta, f, indent=2)
    logger.info("Saved to %s/lgbm_ranker_v1.txt", out)

if __name__ == "__main__":
    main()
