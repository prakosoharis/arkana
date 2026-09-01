"""Deterministic OHLC-only Sprint 09 feature, discovery, and similarity engine."""
from __future__ import annotations
from hashlib import sha256
import json, math
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import Dataset
from .market_data import latest_dataset, read_bars

FEATURE_VERSION="OHLC_FEATURES_V1"; LOOKBACK=10; HORIZON=3; MIN_SUPPORT=8; SIMILARITY_EMBARGO=LOOKBACK+HORIZON
DISCOVERY_ROW_CAP={"M1":250000,"M5":250000,"M15":250000,"M30":250000,"H1":250000,"H4":250000}

def _asset(session, symbol, timeframe):
    dataset=latest_dataset(session,symbol)
    if not dataset: raise ValueError("Registered OHLC dataset is unavailable")
    asset=next((x for x in dataset.bars if x.timeframe==timeframe),None)
    if not asset: raise ValueError("Required timeframe dataset is unavailable")
    # Bulk research is separate from the 1,000-bar chart safety boundary.  The cap is explicit
    # and covers every currently registered non-M1 derived dataset in full.
    #
    # ARK-S24-08: `latest=True` is load-bearing on a fragmented asset.  Without
    # it, read_bars runs its duplicate-resolving window over the whole glob
    # before applying the limit, and the registered 2.99M-bar M1 asset exhausts
    # DuckDB's memory before returning a row.  The bounded path restricts the
    # timestamp range first.  A dataset smaller than the cap is still returned
    # in full, so nothing changes for the derived timeframes.
    bars=read_bars(asset,start=None,end=None,limit=DISCOVERY_ROW_CAP.get(timeframe,250000),latest=True)
    return dataset,bars

def features(session:Session,symbol="XAUUSD",timeframe="M15"):
    dataset,bars=_asset(session,symbol,timeframe); rows=[]
    for i in range(LOOKBACK,len(bars)-HORIZON):
        b=bars[i]; rng=max(b["high"]-b["low"],1e-12); body=b["close"]-b["open"]
        closes=[x["close"] for x in bars[i-LOOKBACK:i+1]]; ranges=[x["high"]-x["low"] for x in bars[i-LOOKBACK:i+1]]
        ret=(b["close"]-bars[i-1]["close"])/bars[i-1]["close"]; mom=(b["close"]-bars[i-3]["close"])/bars[i-3]["close"]
        vol=math.sqrt(sum(((closes[j]-closes[j-1])/closes[j-1])**2 for j in range(1,len(closes)))/LOOKBACK)
        avg=sum(ranges[:-1])/max(1,len(ranges)-1); hi=max(x["high"] for x in bars[i-LOOKBACK:i+1]); lo=min(x["low"] for x in bars[i-LOOKBACK:i+1])
        vector={"return_1":ret,"body_ratio":body/rng,"upper_wick_ratio":(b["high"]-max(b["open"],b["close"]))/rng,"lower_wick_ratio":(min(b["open"],b["close"])-b["low"])/rng,"volatility":vol,"momentum_3":mom,"range_ratio":rng/max(avg,1e-12),"distance_high":(b["close"]-hi)/max(hi-lo,1e-12),"distance_low":(b["close"]-lo)/max(hi-lo,1e-12),"slope":(closes[-1]-closes[0])/max(abs(closes[0]),1e-12)}
        forward=bars[i+HORIZON]; path=bars[i+1:i+HORIZON+1]; entry=b["close"]
        # Keep the feature store compact.  Chart context is materialized only for the
        # handful of samples returned to the client, rather than copied for every
        # historical state in a multi-year dataset.
        rows.append({"index":i,"timestamp":str(b["timestamp"]),"features":vector,"forward_return":(forward["close"]-entry)/entry,"mfe":(max(x["high"] for x in path)-entry)/entry,"mae":(min(x["low"] for x in path)-entry)/entry})
    fingerprint=sha256(json.dumps({"v":FEATURE_VERSION,"dataset":dataset.fingerprint,"timeframe":timeframe,"lookback":LOOKBACK,"horizon":HORIZON},sort_keys=True).encode()).hexdigest()
    return {"version":FEATURE_VERSION,"fingerprint":fingerprint,"timeframe":timeframe,"dataset_id":dataset.id,"coverage":{"start":str(bars[0]["timestamp"]) if bars else None,"end":str(bars[-1]["timestamp"]) if bars else None,"bar_count":len(bars)},"rows":rows,"_bars":bars}

def _stats(rows):
    values=[x["forward_return"] for x in rows]; return {"occurrences":len(rows),"positive_rate":sum(x>0 for x in values)/len(values) if values else None,"mean_forward_return":sum(values)/len(values) if values else None}

def _sample(row, bars):
    """Attach an intentionally small, deterministic chart window for visual review."""
    i=row["index"]
    return {**row,"context":[{**x,"timestamp":str(x["timestamp"])} for x in bars[max(0,i-12):i+HORIZON+1]]}

def discover(session,symbol,timeframe):
    store=features(session,symbol,timeframe); store_bars=store["_bars"]; cut=int(len(store["rows"])*.7); train,hold=store["rows"][:cut],store["rows"][cut:]
    rules={"BULLISH_EXPANSION":lambda f:f["body_ratio"]>.55 and f["range_ratio"]>1.1,"BEARISH_EXPANSION":lambda f:f["body_ratio"]<-.55 and f["range_ratio"]>1.1,"COMPRESSION_UP_MOMENTUM":lambda f:f["range_ratio"]<.8 and f["momentum_3"]>0,"NEAR_ROLLING_LOW_REVERSAL":lambda f:f["distance_low"]<.15 and f["body_ratio"]>.2}
    candidates=[]
    for name,rule in rules.items():
        a,b=[x for x in train if rule(x["features"])],[x for x in hold if rule(x["features"])]
        ts,hs=_stats(a),_stats(b); status="WORTH_INVESTIGATING"
        if ts["occurrences"]<MIN_SUPPORT or hs["occurrences"]<MIN_SUPPORT: status="INSUFFICIENT_SUPPORT"
        elif abs((ts["positive_rate"] or 0)-(hs["positive_rate"] or 0))>.2: status="UNSTABLE"
        elif (ts["positive_rate"] or 0)>.65 and (hs["positive_rate"] or 0)<.5: status="OVERFIT_RISK"
        samples=[{**_sample(x, store_bars), "partition":"TRAIN"} for x in a[:3]] + [{**_sample(x, store_bars), "partition":"HOLDOUT"} for x in b[:3]]
        candidates.append({"name":name,"conditions":name.replace("_"," "),"status":status,"train":ts,"holdout":hs,"sample_timestamps":[x["timestamp"] for x in (a+b)[:10]],"samples":samples})
    counts={status:sum(x["status"]==status for x in candidates) for status in ("INSUFFICIENT_SUPPORT","OVERFIT_RISK","UNSTABLE","WORTH_INVESTIGATING")}
    return {**{k:v for k,v in store.items() if k not in ("rows","_bars")},"split":{"policy":"chronological 70/30; holdout excluded from candidate condition selection","train_rows":len(train),"holdout_rows":len(hold),"train_period":{"start":train[0]["timestamp"] if train else None,"end":train[-1]["timestamp"] if train else None},"holdout_period":{"start":hold[0]["timestamp"] if hold else None,"end":hold[-1]["timestamp"] if hold else None},"minimum_support":MIN_SUPPORT},"search_space":{"candidate_library":list(rules),"evaluated":len(candidates),"status_counts":counts},"candidates":candidates,"warning":"OHLC descriptive evidence only. Candidates do not create strategies or backtests."}

def similar(session,symbol,timeframe,timestamp,top_n=8):
    store=features(session,symbol,timeframe); store_bars=store["_bars"]; selected=next((x for x in store["rows"] if x["timestamp"]==timestamp),None)
    if not selected: raise ValueError("Selected timestamp is not a supported historical feature state")
    keys=list(selected["features"]); scales={k:max(1e-12,math.sqrt(sum(x["features"][k]**2 for x in store["rows"])/len(store["rows"]))) for k in keys}
    scored=[]
    for row in store["rows"]:
        if abs(row["index"]-selected["index"])<SIMILARITY_EMBARGO: continue
        deltas={k:row["features"][k]-selected["features"][k] for k in keys}; distance=math.sqrt(sum((deltas[k]/scales[k])**2 for k in keys)); scored.append({**row,"similarity_score":1/(1+distance),"feature_delta":deltas})
    analogs=sorted(scored,key=lambda x:x["similarity_score"],reverse=True)[:max(1,min(top_n,20))]
    return {**{k:v for k,v in store.items() if k not in ("rows","_bars")},"selected":_sample(selected,store_bars),"analogs":[_sample(x,store_bars) for x in analogs],"aggregate":{**_stats(analogs),"mean_mfe":sum(x["mfe"] for x in analogs)/len(analogs) if analogs else None,"mean_mae":sum(x["mae"] for x in analogs)/len(analogs) if analogs else None},"method":{"feature_version":FEATURE_VERSION,"embargo_bars":SIMILARITY_EMBARGO,"forward_outcome_excluded_from_features":True},"warning":"Historical similarity is evidence, not a prediction or guarantee."}
