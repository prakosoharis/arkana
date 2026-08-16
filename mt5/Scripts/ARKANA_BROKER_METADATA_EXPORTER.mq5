#property strict
#property version   "1.000"
#property script_show_inputs

input string InpBrokerSymbol="XAUUSD.m";

void OnStart()
{
  if(!SymbolSelect(InpBrokerSymbol,true)){ Print("ARKANA metadata export failed: symbol unavailable: ",InpBrokerSymbol); return; }
  FolderCreate("ARKANA",FILE_COMMON); FolderCreate("ARKANA\\broker_metadata",FILE_COMMON);
  int file=FileOpen("ARKANA\\broker_metadata\\latest.ini",FILE_WRITE|FILE_TXT|FILE_COMMON|FILE_ANSI);
  if(file==INVALID_HANDLE){ Print("ARKANA metadata export failed: cannot write FILE_COMMON"); return; }
  FileWrite(file,"schema_version=1"); FileWrite(file,"source=MT5"); FileWrite(file,"canonical_symbol=XAUUSD"); FileWrite(file,"broker_symbol="+InpBrokerSymbol);
  FileWrite(file,"digits="+IntegerToString((int)SymbolInfoInteger(InpBrokerSymbol,SYMBOL_DIGITS)));
  FileWrite(file,"point="+DoubleToString(SymbolInfoDouble(InpBrokerSymbol,SYMBOL_POINT),12));
  FileWrite(file,"tick_size="+DoubleToString(SymbolInfoDouble(InpBrokerSymbol,SYMBOL_TRADE_TICK_SIZE),12));
  FileWrite(file,"tick_value="+DoubleToString(SymbolInfoDouble(InpBrokerSymbol,SYMBOL_TRADE_TICK_VALUE),12));
  FileWrite(file,"tick_value_profit="+DoubleToString(SymbolInfoDouble(InpBrokerSymbol,SYMBOL_TRADE_TICK_VALUE_PROFIT),12));
  FileWrite(file,"tick_value_loss="+DoubleToString(SymbolInfoDouble(InpBrokerSymbol,SYMBOL_TRADE_TICK_VALUE_LOSS),12));
  FileWrite(file,"contract_size="+DoubleToString(SymbolInfoDouble(InpBrokerSymbol,SYMBOL_TRADE_CONTRACT_SIZE),12));
  FileWrite(file,"volume_min="+DoubleToString(SymbolInfoDouble(InpBrokerSymbol,SYMBOL_VOLUME_MIN),12));
  FileWrite(file,"volume_max="+DoubleToString(SymbolInfoDouble(InpBrokerSymbol,SYMBOL_VOLUME_MAX),12));
  FileWrite(file,"volume_step="+DoubleToString(SymbolInfoDouble(InpBrokerSymbol,SYMBOL_VOLUME_STEP),12));
  FileWrite(file,"currency_base="+SymbolInfoString(InpBrokerSymbol,SYMBOL_CURRENCY_BASE)); FileWrite(file,"currency_profit="+SymbolInfoString(InpBrokerSymbol,SYMBOL_CURRENCY_PROFIT)); FileWrite(file,"currency_margin="+SymbolInfoString(InpBrokerSymbol,SYMBOL_CURRENCY_MARGIN));
  FileWrite(file,"trade_calc_mode="+IntegerToString((int)SymbolInfoInteger(InpBrokerSymbol,SYMBOL_TRADE_CALC_MODE))); FileWrite(file,"account_currency="+AccountInfoString(ACCOUNT_CURRENCY)); FileWrite(file,"collected_at="+TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS));
  FileClose(file); Print("ARKANA broker metadata exported: FILE_COMMON/ARKANA/broker_metadata/latest.ini");
}
