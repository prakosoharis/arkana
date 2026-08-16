# Sprint 09 — Pattern Discovery & Historical Similarity

**Status: ACCEPTED / COMPLETE — Owner Acceptance passed on the registered real MT5 historical dataset.**

## Data readiness OAT correction

Bulk MT5 acquisition is separate from the bounded interactive bars endpoint. A chart request is capped to its requested limit and no longer rejects a registered multi-million-row dataset during UI refresh. The actual owner export was detected and imported as M1 canonical data; no partial cleanup is required.

## MT5 historical acquisition contract

`mt5/Scripts/ARKANA_HISTORICAL_EXPORTER.mq5` is a manual one-shot, non-trading Script. It requests maximum practical broker-available completed `XAUUSD.m` M1 bars, preserves broker timestamps, and atomically writes CSV plus manifest under `FILE_COMMON/ARKANA/historical/`. ARKANA sync reads only finalized artifacts, stores a fingerprint-addressed immutable raw copy, then reuses the Sprint 01 validator/importer/Parquet M1 canonical source/resampler/registry. Timestamp status remains `UNVERIFIED_BROKER_TIME`; session capabilities remain unavailable and gaps are reported, never filled.

## Boundary

Only registered XAUUSD OHLC M1/M5/M15/M30/H1/H4 data is used. Tick/Bid-Ask/spread, verified sessions, external events, LLM, strategy creation, backtest execution, MT5 deployment, and LIVE trading are out of scope.

## Deterministic feature contract v1

Each feature row is derived from one OHLC bar with a prior-bar window: one-bar return, normalized candle body/range, upper/lower wick ratios, rolling volatility, short momentum, compression/expansion ratio, distance from rolling high/low, and deterministic rolling slope. The contract is versioned and fingerprinted by dataset fingerprint, timeframe, lookback, and feature version.

## Discovery

The engine mines a small fixed library of interpretable OHLC condition combinations; it does not brute-force arbitrary indicators. Candidates are assessed on a chronological TRAIN/HOLDOUT split, use minimum support, expose train and holdout outcome summaries, and receive `INSUFFICIENT_SUPPORT`, `OVERFIT_RISK`, `UNSTABLE`, or `WORTH_INVESTIGATING`. They are research evidence only.

## Similarity

Owner selects one historical timestamp. The engine compares its same v1 feature vector to preceding historical feature states, returns Top-N analogs, forward OHLC outcome at supported horizon, MFE/MAE where bars permit it, aggregate outcome distribution, feature deltas, and visual samples. It is evidence, not prediction.

## Owner-facing UX contract

The `/discovery` presentation uses two owner goals: **Cari Pola Historis** and **Cari Kondisi yang Mirip**. Machine-readable API values and analytical methodology remain unchanged. The UI translates them as follows while preserving the original enum under progressive disclosure: `WORTH_INVESTIGATING` → *Layak Diteliti*, `OVERFIT_RISK` → *Bagus di Data Lama, Lemah di Data Baru*, `UNSTABLE` → *Hasil Belum Konsisten*, and `INSUFFICIENT_SUPPORT` → *Data Kejadian Belum Cukup*.

Every positive-rate percentage explains the measured event—close three supported candles after the occurrence is higher than the close at the occurrence—and states its occurrence count. Train/Holdout are presented as *Data Penemuan*/*Data Uji Baru*. Technical fingerprints, feature contract, raw enums, feature deltas, MFE/MAE terminology, and embargo details remain available through **Pengaturan Lanjutan** or **Detail Analisis**, with contextual help. The UI does not create a strategy, backtest, BUY/SELL instruction, or deployment.

## Final Owner Acceptance

Owner Acceptance passed for production historical-dataset selection, Pattern Discovery, Data Penemuan/Data Uji Baru, explicit outcome definition, visual occurrence samples, Historical Similarity, Top-N analogs, understandable MFE/MAE, retained technical audit details, and the `UNVERIFIED_BROKER_TIME` boundary. The owner also verified that ARKANA does not infer sessions, issue BUY/SELL recommendations, create a strategy, or expose an MT5 deployment action from this feature.
