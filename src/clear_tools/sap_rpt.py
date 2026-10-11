"""SAP-RPT-1.6 on SAP AI Core, the Level 0 prediction backend (docs/PLAN.md §3).

RPT predicts by in-context learning: a request carries example rows with a
known target plus query rows whose target is "[PREDICT]", and returns a
prediction with a confidence interval for each query row. Two optional
explanations: the context rows RPT found most relevant (similar past cases,
the clearest explanation for a planner) and a weight per column (attention,
not cause and effect).

Request and response fields follow the RPT API types in SAP's
@sap-ai-sdk/rpt package. Credentials are the team's AI Core service key,
read from environment variables. Standard library only.
"""

import base64
import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

PLACEHOLDER = "[PREDICT]"
INDEX = "row_ref"

_SETTINGS = {
    "auth_url": "SAP_AICORE_AUTH_URL",
    "client_id": "SAP_AICORE_CLIENT_ID",
    "client_secret": "SAP_AICORE_CLIENT_SECRET",
    "api_url": "SAP_AICORE_API_URL",
    "resource_group": "SAP_AICORE_RESOURCE_GROUP",
    "deployment_id": "SAP_RPT_DEPLOYMENT_ID",
}


@dataclass(frozen=True)
class Config:
    auth_url: str
    client_id: str
    client_secret: str
    api_url: str
    resource_group: str
    deployment_id: str

    @classmethod
    def from_env(cls, deployment_setting: str = _SETTINGS["deployment_id"]) -> "Config":
        """The service key and one deployment, whose ID is in the variable deployment_setting."""
        names = {**_SETTINGS, "deployment_id": deployment_setting}
        missing = [name for name in names.values() if not os.environ.get(name)]
        if missing:
            raise LookupError(f"SAP AI Core settings missing: {', '.join(missing)}")
        return cls(**{field: os.environ[name] for field, name in names.items()})

    def __repr__(self) -> str:  # Never print the client secret.
        return f"Config(api_url={self.api_url!r}, deployment_id={self.deployment_id!r})"


@dataclass(frozen=True)
class Prediction:
    value: float
    interval: tuple[float, float] | None
    column_scores: dict[str, float] | None
    similar_rows: list[int] | None  # Indices into the context rows, most relevant first.


_tokens: dict[str, tuple[str, float]] = {}  # client_id -> (token, expiry as time.monotonic())


def access_token(config: Config, timeout: float = 10) -> str:
    """OAuth access token for the service key (client credentials grant), reused until shortly before expiry."""
    cached = _tokens.get(config.client_id)
    if cached and cached[1] > time.monotonic():
        return cached[0]
    key = base64.b64encode(f"{config.client_id}:{config.client_secret}".encode()).decode()
    response = _post(
        f"{config.auth_url.rstrip('/')}/oauth/token",
        urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(),
        {"Authorization": f"Basic {key}", "Content-Type": "application/x-www-form-urlencoded"},
        timeout,
    )
    lifetime = float(response.get("expires_in", 3600))
    _tokens[config.client_id] = (response["access_token"], time.monotonic() + max(0.0, lifetime - 60))
    return response["access_token"]


def predict(
    config: Config,
    context: list[dict],
    queries: list[dict],
    target: str,
    *,
    token: str,
    explain_columns: int = 0,
    explain_rows: int = 0,
    timeout: float = 30,
) -> list[Prediction]:
    """Predict the numeric `target` of each query row, learning from the context rows.

    explain_columns and explain_rows (each at most 20) ask for column weights
    and for the most relevant context rows per query row.
    """
    rows = [{**row, INDEX: f"c{i}"} for i, row in enumerate(context)]
    rows += [{**row, target: PLACEHOLDER, INDEX: f"q{i}"} for i, row in enumerate(queries)]
    prediction_config: dict = {
        "target_columns": [{"name": target, "prediction_placeholder": PLACEHOLDER, "task_type": "regression"}]
    }
    explanations = {"top_column_scores": explain_columns, "top_relevant_context_rows": explain_rows}
    if any(explanations.values()):
        prediction_config["explanations"] = {k: v for k, v in explanations.items() if v}
    result = _post(
        f"{config.api_url.rstrip('/')}/v2/inference/deployments/{config.deployment_id}/predict",
        json.dumps({"prediction_config": prediction_config, "index_column": INDEX, "rows": rows}).encode(),
        {
            "Authorization": f"Bearer {token}",
            "AI-Resource-Group": config.resource_group,
            "Content-Type": "application/json",
        },
        timeout,
    )
    status = result.get("status") or {}
    if status.get("code") not in (0, None):
        raise RuntimeError(f"RPT returned status {status}")

    cells = {p[INDEX]: p[target][0] for p in result["predictions"]}
    explained = result.get("explanations") or {}
    scores = explained.get("top_column_scores") or []
    # Row indices count all rows in request order; context rows come first.
    relevant = explained.get("top_relevant_context_rows") or []
    predictions = []
    for i in range(len(queries)):
        cell = cells[f"q{i}"]
        interval = cell.get("confidence_interval")
        predictions.append(Prediction(
            value=float(cell["prediction"]),
            interval=(float(interval[0]), float(interval[1])) if interval else None,
            column_scores=scores[i] if i < len(scores) else None,
            similar_rows=[r for r in relevant[i] if r < len(context)] if i < len(relevant) else None,
        ))
    return predictions


def _post(url: str, body: bytes, headers: dict[str, str], timeout: float) -> dict:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)
