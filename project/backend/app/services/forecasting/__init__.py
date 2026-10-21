from app.services.forecasting.outlook import estimated_quote_date, timing_signal
from app.services.forecasting.scorecard import (
    MIN_OUTCOMES,
    WINDOW,
    apply_forward_selection,
    configuration_key,
    forecast_at_horizon,
    scorecard,
    settle_forecasts,
)

__all__ = [
    "MIN_OUTCOMES",
    "WINDOW",
    "apply_forward_selection",
    "configuration_key",
    "estimated_quote_date",
    "forecast_at_horizon",
    "scorecard",
    "settle_forecasts",
    "timing_signal",
]

try:
    from app.services.forecasting.simple_models import SIMPLE_CONFIG, fit_simple, predict_simple
    __all__.extend(["SIMPLE_CONFIG", "fit_simple", "predict_simple"])
except ImportError:
    pass

try:
    from app.services.forecasting.engine import (
        CONFIG,
        HORIZONS,
        LocalLSTM,
        MIN_OBSERVATIONS,
        NEWS_CHANNELS,
        PRICE_FEATURES,
        SEQUENCE,
        build_dataset,
        fit_candidate,
        fit_model,
        metrics,
        news_vector,
        predict_candidate,
        predict_model,
        train_forecasts,
        train_pair,
    )
    __all__.extend([
        "CONFIG",
        "HORIZONS",
        "LocalLSTM",
        "MIN_OBSERVATIONS",
        "NEWS_CHANNELS",
        "PRICE_FEATURES",
        "SEQUENCE",
        "build_dataset",
        "fit_candidate",
        "fit_model",
        "metrics",
        "news_vector",
        "predict_candidate",
        "predict_model",
        "train_forecasts",
        "train_pair",
    ])
except ImportError:
    pass
