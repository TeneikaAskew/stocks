"""Research-only EXPLOSIVE-vs-rest model comparison.

The four-class model and its production artifact path are never written. A
chronological train/validation/test split is made per ticker; thresholds are
selected on validation exactly once and evaluated unchanged on final test.
PR AUC is the primary model-selection metric.
"""
from __future__ import annotations
import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
import numpy as np
import pandas as pd
from .binary_config import (BINARY_LABEL, FOCAL_GAMMA, MIN_PARTITION_ROWS,
    RANDOM_STATE, RESEARCH_ARTIFACT_ROOT, TEST_FRACTION, UTILITY,
    VALIDATION_FRACTION, WEIGHT_CAP)

@dataclass(frozen=True)
class Partitions:
    train: np.ndarray
    validation: np.ndarray
    test: np.ndarray

def chronological_partitions(ts: Iterable[Any]) -> Partitions:
    """Return positional chronological 60/20/20 partitions without splitting ties."""
    times = pd.to_datetime(pd.Series(ts), utc=True, errors="raise")
    n = len(times)
    if n < 3 * MIN_PARTITION_ROWS:
        raise ValueError(f"need at least {3 * MIN_PARTITION_ROWS} rows, got {n}")
    order = np.argsort(times.to_numpy(), kind="stable")
    sorted_times = times.iloc[order].reset_index(drop=True)
    cuts = []
    for target in (int(n * (1-VALIDATION_FRACTION-TEST_FRACTION)), int(n*(1-TEST_FRACTION))):
        cut = target
        while cut < n and cut > 0 and sorted_times.iloc[cut] == sorted_times.iloc[cut-1]:
            cut += 1
        cuts.append(cut)
    a, b = cuts
    out = Partitions(order[:a], order[a:b], order[b:])
    if min(map(len, (out.train, out.validation, out.test))) < MIN_PARTITION_ROWS:
        raise ValueError("timestamp grouping leaves an undersized partition")
    return out

def _calibration(y: np.ndarray, p: np.ndarray, bins: int = 10) -> tuple[float, list[dict]]:
    edges = np.linspace(0, 1, bins+1); bucket = np.digitize(p, edges[1:-1]); curve=[]; ece=0.
    for i in range(bins):
        mask=bucket==i; count=int(mask.sum())
        predicted=float(p[mask].mean()) if count else None
        observed=float(y[mask].mean()) if count else None
        if count: ece += count/len(y)*abs(predicted-observed)
        curve.append({"lower":float(edges[i]),"upper":float(edges[i+1]),"count":count,
                      "mean_probability":predicted,"observed_rate":observed})
    return float(ece), curve

def metrics(y: Iterable[int], probability: Iterable[float], threshold: float,
            sessions: Iterable[Any]) -> dict[str, Any]:
    """Compute discrimination, calibration, alert, and utility measures."""
    from sklearn.metrics import (average_precision_score,brier_score_loss,log_loss,
        precision_score,recall_score,roc_auc_score)
    y=np.asarray(y,dtype=np.int8); p=np.clip(np.asarray(probability,dtype=float),1e-12,1-1e-12)
    if not len(y) or len(p)!=len(y): raise ValueError("y and probability must be non-empty and equal length")
    pred=p>=threshold; tp=int(((y==1)&pred).sum()); fp=int(((y==0)&pred).sum())
    fn=int(((y==1)&~pred).sum()); tn=int(((y==0)&~pred).sum())
    n_sessions=int(pd.Series(sessions).nunique()); ece,curve=_calibration(y,p)
    return {"pr_auc":float(average_precision_score(y,p)),
      "roc_auc":float(roc_auc_score(y,p)) if len(np.unique(y))==2 else None,
      "log_loss":float(log_loss(y,p,labels=[0,1])),"brier_score":float(brier_score_loss(y,p)),
      "calibration_ece":ece,"calibration_curve":curve,"threshold":float(threshold),
      "precision":float(precision_score(y,pred,zero_division=0)),
      "recall":float(recall_score(y,pred,zero_division=0)),
      "false_alerts_per_session":fp/n_sessions if n_sessions else None,
      "expected_net_utility":(tp*UTILITY.true_positive+fp*UTILITY.false_positive+
          fn*UTILITY.false_negative+tn*UTILITY.true_negative)/len(y),
      "confusion":{"tp":tp,"fp":fp,"fn":fn,"tn":tn},"base_rate":float(y.mean()),
      "rows":int(len(y)),"sessions":n_sessions}

def choose_threshold(y: Iterable[int], probability: Iterable[float],
                     min_precision: float | None = None) -> dict[str,float]:
    """Select an operating point on validation using the declared utility."""
    y=np.asarray(y,dtype=np.int8); p=np.asarray(probability,dtype=float)
    if not len(y) or len(p)!=len(y): raise ValueError("y and probability must be non-empty and equal length")
    if min_precision is not None and not 0 <= min_precision <= 1: raise ValueError("min_precision must be in [0, 1]")
    best=None
    for threshold in np.unique(np.r_[0.,p,1.]):
        pred=p>=threshold; tp=int(((y==1)&pred).sum()); fp=int(((y==0)&pred).sum())
        precision=tp/(tp+fp) if tp+fp else 0.
        if min_precision is not None and precision<min_precision: continue
        utility=(tp*UTILITY.true_positive+fp*UTILITY.false_positive)/len(y)
        candidate=(utility,precision,-float(threshold),float(threshold))
        if best is None or candidate[:3]>best[:3]: best=candidate
    if best is None: raise ValueError("no validation threshold satisfies minimum precision")
    return {"threshold":best[3],"validation_expected_net_utility":best[0],
            "validation_precision":best[1]}

class BaseRateModel:
    def fit(self, _x: Any, y: Iterable[int], **_: Any) -> "BaseRateModel":
        self.rate_=float(np.mean(y)); return self
    def predict_proba(self, x: Any) -> np.ndarray:
        p=np.full(len(x),self.rate_); return np.column_stack((1-p,p))

class FocalReweightedLGBM:
    """Two-stage focal-style LightGBM.

    A pilot identifies hard training observations, then the final estimator uses
    ``class_weight * (1-p_true)**gamma``.  This is the standard focal-loss
    treatment expressed as bounded observation weights, retaining LightGBM's
    probabilistic binary objective and avoiding an uncalibrated custom Hessian.
    Only training predictions participate in the reweighting.
    """
    def __init__(self, params: dict[str, Any], positive_weight: float):
        self.params = params
        self.positive_weight = positive_weight

    def fit(self, x: Any, y: Iterable[int], **_: Any) -> "FocalReweightedLGBM":
        import lightgbm as lgb
        labels = np.asarray(y, dtype=np.int8)
        pilot = lgb.LGBMClassifier(**self.params).fit(x, labels)
        probability = pilot.predict_proba(x)[:, 1]
        p_true = np.where(labels == 1, probability, 1 - probability)
        class_weight = np.where(labels == 1, self.positive_weight, 1.0)
        weights = np.clip(class_weight * (1 - p_true) ** FOCAL_GAMMA, 1e-3, WEIGHT_CAP)
        self.model_ = lgb.LGBMClassifier(**self.params).fit(x, labels, sample_weight=weights)
        return self

    def predict_proba(self, x: Any) -> np.ndarray:
        return self.model_.predict_proba(x)

def _estimators(y_train: np.ndarray) -> dict[str,tuple[Any,np.ndarray|None]]:
    import lightgbm as lgb
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    pos=max(1,int(y_train.sum())); neg=max(1,int((y_train==0).sum())); ratio=min(WEIGHT_CAP,neg/pos)
    common=dict(n_estimators=300,learning_rate=.05,num_leaves=31,max_depth=6,
                min_child_samples=100,random_state=RANDOM_STATE,n_jobs=-1,verbosity=-1)
    logistic=CalibratedClassifierCV(make_pipeline(StandardScaler(),LogisticRegression(
        max_iter=2000,class_weight="balanced",random_state=RANDOM_STATE)),method="sigmoid",cv=3)
    return {"lightgbm_unweighted":(lgb.LGBMClassifier(**common),None),
      "lightgbm_constrained_weight":(lgb.LGBMClassifier(**common),np.where(y_train==1,ratio,1.)),
      "lightgbm_focal_equivalent":(FocalReweightedLGBM(common,ratio),None),
      "calibrated_logistic":(logistic,None),"base_rate":(BaseRateModel(),None)}

def run_experiment(frame: pd.DataFrame, feature_cols: list[str], ticker: str,
                   output_dir: str|Path, min_precision: float|None=None) -> dict:
    """Fit candidates and atomically store a ticker-specific locked report."""
    missing={"ts",BINARY_LABEL,*feature_cols}-set(frame)
    if missing: raise ValueError(f"missing columns: {sorted(missing)}")
    parts=chronological_partitions(frame.ts); x=frame[feature_cols].replace([np.inf,-np.inf],np.nan).fillna(0)
    y=frame[BINARY_LABEL].astype(np.int8).to_numpy(); sessions=pd.to_datetime(frame.ts,utc=True).dt.date.to_numpy()
    result={"ticker":ticker,"primary_metric":"pr_auc","artifact_root":RESEARCH_ARTIFACT_ROOT,
      "utility":asdict(UTILITY),"threshold_source":"validation","models":{}}
    for name,(model,weights) in _estimators(y[parts.train]).items():
        model.fit(x.iloc[parts.train],y[parts.train],**({"sample_weight":weights} if weights is not None else {}))
        vp=model.predict_proba(x.iloc[parts.validation])[:,1]; locked=choose_threshold(y[parts.validation],vp,min_precision)
        tp=model.predict_proba(x.iloc[parts.test])[:,1]
        result["models"][name]={"locked_threshold":locked,
          "validation":metrics(y[parts.validation],vp,locked["threshold"],sessions[parts.validation]),
          "test":metrics(y[parts.test],tp,locked["threshold"],sessions[parts.test])}
    result["selected_model"]=max(result["models"],key=lambda n:result["models"][n]["validation"]["pr_auc"])
    target=Path(output_dir)/RESEARCH_ARTIFACT_ROOT/ticker; target.mkdir(parents=True,exist_ok=True)
    path=target/"report.json"; tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n"); tmp.replace(path)
    return result

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker",required=True); parser.add_argument("--tf",required=True)
    parser.add_argument("--output-dir",required=True); parser.add_argument("--min-precision",type=float)
    args=parser.parse_args()
    from gcp.database import get_engine
    from .mag_dataset import load_magnitude_dataset
    from .mag_pred_train import featurize
    raw=load_magnitude_dataset(get_engine(),args.ticker,args.tf,"phase0")
    raw[BINARY_LABEL]=(raw["magnitude_bucket"]=="EXPLOSIVE").astype(np.int8)
    features,cols=featurize(raw)
    frame=pd.concat([raw[["ts",BINARY_LABEL]].reset_index(drop=True),features.reset_index(drop=True)],axis=1)
    run_experiment(frame,cols,args.ticker,args.output_dir,args.min_precision)

if __name__=="__main__": main()
