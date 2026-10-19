"""Small deterministic competitors using the same lagged rates as the LSTM."""
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

SIMPLE_CONFIG = {"ridge_alpha": 10., "trees": 60, "tree_depth": 2, "tree_min_leaf": 15,
                 "tree_learning_rate": .05, "seed": 42}


def fit_simple(name, x, y):
    if name == "ridge":
        model = make_pipeline(StandardScaler(), Ridge(alpha=SIMPLE_CONFIG["ridge_alpha"]))
    elif name == "boosted_trees":
        model = GradientBoostingRegressor(n_estimators=SIMPLE_CONFIG["trees"], max_depth=SIMPLE_CONFIG["tree_depth"],
            min_samples_leaf=SIMPLE_CONFIG["tree_min_leaf"], learning_rate=SIMPLE_CONFIG["tree_learning_rate"],
            random_state=SIMPLE_CONFIG["seed"], n_iter_no_change=None)
    else:
        raise ValueError(f"Unknown simple model: {name}")
    model.fit(x.reshape(len(x), -1), y)
    return model, max(float(np.std(y)), .05)


def predict_simple(fitted, x):
    model, scale = fitted
    return np.clip(model.predict(x.reshape(len(x), -1)), -5*scale, 5*scale)
