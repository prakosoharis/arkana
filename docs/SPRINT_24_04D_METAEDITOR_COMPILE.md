# ARK-S24-04d — The MetaEditor Compile, Finally Run

**Date:** 2026-09-01

**Status:** complete

**Technical checkpoint claim:** `VALIDATED`

`VALIDATED` covers the MQL5 toolchain compile of `ARKANA_ENGINE.mq5` and the
differential result recorded below. No EA was published, attached to a chart,
or deployed. No order, trade, or DEMO authority was created. The Owner's
installed terminal files were not modified.

## The limitation that is now closed

ARK-S24-01, ARK-S24-02, and ARK-S24-03 each recorded the same known limitation:

> **MetaEditor has not compiled the EA.** The MQL5 changes are validated by
> mirrored logic and source assertions, not by the MetaEditor toolchain, which
> is not available in this environment.

That last clause was wrong. MetaTrader 5 is installed on this machine under
MetaQuotes' own bundled Wine:

```text
/Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine   (wine-11.1)
~/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/
    Program Files/MetaTrader 5/MetaEditor64.exe
```

`MetaEditor64.exe /compile:` runs headless. The compile could have been run at
ARK-S24-01 and was not, because the environment was assumed rather than checked.

## Result

```text
Result: 0 errors, 0 warnings, 5025 ms elapsed, cpu='X64 Regular'
```

`<Trade/Trade.mqh>` and its five transitive includes resolved from the
terminal's own `MQL5/Include`, and a 107,028-byte `.ex5` was produced.

## The differential that matters

ARK-S24-03 claimed, from structure alone, that ARK-S24-01 had used
`session_clock` and `session_windows` throughout the EA without ever declaring
them in the `GenericConfig` struct — and therefore that the source reported
`VALIDATED` at ARK-S24-01 and again at ARK-S24-02 **would not have compiled**.

That claim is no longer an argument. The ARK-S24-02 source was checked out from
commit `0036b3f` and put through the same compiler:

```text
ARKANA_S24_02_CHECK.mq5(128,1598) : error 256: undeclared identifier 'session_clock'
ARKANA_S24_02_CHECK.mq5(128,1637) : error 256: undeclared identifier 'session_windows'
ARKANA_S24_02_CHECK.mq5(144,163)  : error 256: undeclared identifier 'session_clock'
ARKANA_S24_02_CHECK.mq5(145,39)   : error 256: undeclared identifier 'session_windows'
ARKANA_S24_02_CHECK.mq5(193,31)   : error 256: undeclared identifier 'session_clock'
ARKANA_S24_02_CHECK.mq5(193,49)   : error 256: undeclared identifier 'session_windows'
Result: 6 errors, 2 warnings
```

| source | result |
|---|---|
| ARK-S24-02 (`0036b3f`) | **6 errors, 2 warnings** |
| ARK-S24-03 onward (`HEAD`) | **0 errors, 0 warnings** |

Two accepted checkpoints carried a technical claim of `VALIDATED` over source
that the MQL5 compiler rejects. The claim covered evaluator/compiler parity and
source assertions, which were all true — but the EA in those two records could
not have been built. The structural tests added at ARK-S24-03 now make that
class of defect fail a test rather than a publication.

## What was and was not touched

The Owner's installed terminal already contained `ARKANA_ENGINE.mq5` and
`ARKANA_ENGINE.ex5` dated 2026-08-10. **Neither was overwritten.** Both
compiles ran on temporary copies under distinct names, and every temporary
artifact was removed afterwards:

```text
=== temp files removed ===
(none left)
=== your original files, untouched ===
-rw-r--r-- 48740 Aug 10 04:44 ARKANA_ENGINE.ex5
-rw-r--r-- 11599 Aug 10 04:26 ARKANA_ENGINE.mq5
```

Installing the Sprint 24 EA into the terminal is a **publication** step. It is
governed, it is the Owner's decision, and it was deliberately not taken here.

## Known limitations

1. **A clean compile is not a correct EA.** It proves the source builds. It
   proves nothing about whether the session filter, the sell path, or the ATR
   distance behave correctly against a live terminal. That still requires a
   DEMO run, which requires a strategy worth deploying.
2. **The EA has still never executed against a broker.**
3. **The terminal's installed EA is three checkpoints out of date**, by choice.
4. The compile used the terminal's current `MQL5/Include`. A different
   MetaTrader build could in principle differ.

## Owner OAT steps

```bash
cd "$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5"
WINEPREFIX="$HOME/Library/Application Support/net.metaquotes.wine.metatrader5" \
  "/Applications/MetaTrader 5.app/Contents/SharedSupport/wine/bin/wine" \
  MetaEditor64.exe "/compile:MQL5\Experts\ARKANA_ENGINE.mq5" /log
```

**ARK-S24-04d is ready for Owner acceptance with technical claim `VALIDATED`.**

```text
DITERIMA — ARK-S24-04d
```
