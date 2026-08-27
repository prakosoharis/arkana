#property strict
#property version   "1.100"
#property script_show_inputs

input string InpBrokerSymbol="XAUUSD.m";

void OnStart()
{
  if(!SymbolSelect(InpBrokerSymbol,true)){ Print("ARKANA metadata export failed: symbol unavailable: ",InpBrokerSymbol); return; }
  for(int attempt=0;attempt<60 && (!TerminalInfoInteger(TERMINAL_CONNECTED) || SymbolInfoDouble(InpBrokerSymbol,SYMBOL_TRADE_TICK_VALUE_PROFIT)<=0 || SymbolInfoDouble(InpBrokerSymbol,SYMBOL_BID)<=0);attempt++) Sleep(500);
  if(!TerminalInfoInteger(TERMINAL_CONNECTED) || SymbolInfoDouble(InpBrokerSymbol,SYMBOL_TRADE_TICK_VALUE_PROFIT)<=0 || SymbolInfoDouble(InpBrokerSymbol,SYMBOL_BID)<=0){ Print("ARKANA metadata export failed: connected broker quote/value unavailable"); return; }
  FolderCreate("ARKANA",FILE_COMMON); FolderCreate("ARKANA\\broker_metadata",FILE_COMMON);
  int file=FileOpen("ARKANA\\broker_metadata\\latest.ini",FILE_WRITE|FILE_TXT|FILE_COMMON|FILE_ANSI);
  if(file==INVALID_HANDLE){ Print("ARKANA metadata export failed: cannot write FILE_COMMON"); return; }
  FileWrite(file,"schema_version=1"); FileWrite(file,"source=MT5"); FileWrite(file,"canonical_symbol=XAUUSD"); FileWrite(file,"broker_symbol="+InpBrokerSymbol);
  FileWrite(file,"digits="+IntegerToString((int)SymbolInfoInteger(InpBrokerSymbol,SYMBOL_DIGITS)));
  FileWrite(file,"point="+DoubleToString(SymbolInfoDouble(InpBrokerSymbol,SYMBOL_POINT),12));
  // ARK-S22-01: the assumed spread is the single most leveraged number in the
  // historical evidence chain, so it must come from the terminal rather than
  // from memory.  These fields are additive; older snapshots stay valid.
  FileWrite(file,"spread_points="+IntegerToString((int)SymbolInfoInteger(InpBrokerSymbol,SYMBOL_SPREAD)));
  FileWrite(file,"spread_float="+(SymbolInfoInteger(InpBrokerSymbol,SYMBOL_SPREAD_FLOAT)?"true":"false"));
  FileWrite(file,"spread_price="+DoubleToString(SymbolInfoDouble(InpBrokerSymbol,SYMBOL_ASK)-SymbolInfoDouble(InpBrokerSymbol,SYMBOL_BID),12));
  FileWrite(file,"ask="+DoubleToString(SymbolInfoDouble(InpBrokerSymbol,SYMBOL_ASK),12));
  FileWrite(file,"bid="+DoubleToString(SymbolInfoDouble(InpBrokerSymbol,SYMBOL_BID),12));
  FileWrite(file,"tick_size="+DoubleToString(SymbolInfoDouble(InpBrokerSymbol,SYMBOL_TRADE_TICK_SIZE),12));
  FileWrite(file,"tick_value="+DoubleToString(SymbolInfoDouble(InpBrokerSymbol,SYMBOL_TRADE_TICK_VALUE),12));
  FileWrite(file,"tick_value_profit="+DoubleToString(SymbolInfoDouble(InpBrokerSymbol,SYMBOL_TRADE_TICK_VALUE_PROFIT),12));
  FileWrite(file,"tick_value_loss="+DoubleToString(SymbolInfoDouble(InpBrokerSymbol,SYMBOL_TRADE_TICK_VALUE_LOSS),12));
  FileWrite(file,"contract_size="+DoubleToString(SymbolInfoDouble(InpBrokerSymbol,SYMBOL_TRADE_CONTRACT_SIZE),12));
  FileWrite(file,"volume_min="+DoubleToString(SymbolInfoDouble(InpBrokerSymbol,SYMBOL_VOLUME_MIN),12));
  FileWrite(file,"volume_max="+DoubleToString(SymbolInfoDouble(InpBrokerSymbol,SYMBOL_VOLUME_MAX),12));
  FileWrite(file,"volume_step="+DoubleToString(SymbolInfoDouble(InpBrokerSymbol,SYMBOL_VOLUME_STEP),12));
  double buy_initial=0.0,buy_maintenance=0.0,sell_initial=0.0,sell_maintenance=0.0;
  if(!SymbolInfoMarginRate(InpBrokerSymbol,ORDER_TYPE_BUY,buy_initial,buy_maintenance) || !SymbolInfoMarginRate(InpBrokerSymbol,ORDER_TYPE_SELL,sell_initial,sell_maintenance)){ FileClose(file); Print("ARKANA metadata export failed: margin rates unavailable"); return; }
  FileWrite(file,"margin_initial="+DoubleToString(SymbolInfoDouble(InpBrokerSymbol,SYMBOL_MARGIN_INITIAL),12));
  FileWrite(file,"margin_maintenance="+DoubleToString(SymbolInfoDouble(InpBrokerSymbol,SYMBOL_MARGIN_MAINTENANCE),12));
  FileWrite(file,"margin_rate_buy_initial="+DoubleToString(buy_initial,12)); FileWrite(file,"margin_rate_buy_maintenance="+DoubleToString(buy_maintenance,12));
  FileWrite(file,"margin_rate_sell_initial="+DoubleToString(sell_initial,12)); FileWrite(file,"margin_rate_sell_maintenance="+DoubleToString(sell_maintenance,12));
  FileWrite(file,"account_leverage="+IntegerToString((int)AccountInfoInteger(ACCOUNT_LEVERAGE)));
  FileWrite(file,"currency_base="+SymbolInfoString(InpBrokerSymbol,SYMBOL_CURRENCY_BASE)); FileWrite(file,"currency_profit="+SymbolInfoString(InpBrokerSymbol,SYMBOL_CURRENCY_PROFIT)); FileWrite(file,"currency_margin="+SymbolInfoString(InpBrokerSymbol,SYMBOL_CURRENCY_MARGIN));
  FileWrite(file,"trade_calc_mode="+IntegerToString((int)SymbolInfoInteger(InpBrokerSymbol,SYMBOL_TRADE_CALC_MODE))); FileWrite(file,"account_currency="+AccountInfoString(ACCOUNT_CURRENCY)); FileWrite(file,"collected_at="+TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS));
  FileClose(file); Print("ARKANA broker metadata exported: FILE_COMMON/ARKANA/broker_metadata/latest.ini");
}
