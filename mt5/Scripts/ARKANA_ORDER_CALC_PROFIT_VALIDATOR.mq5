#property strict
#property version "1.100"
#property script_show_inputs
input string InpBrokerSymbol="XAUUSD.m";
input double InpVolume=0.01;

void WriteCase(int file,string id,ENUM_ORDER_TYPE type,double entry,double exit_price)
{
  double profit=0.0; bool ok=OrderCalcProfit(type,InpBrokerSymbol,InpVolume,entry,exit_price,profit);
  FileWrite(file,"case="+id+"|"+(type==ORDER_TYPE_BUY?"BUY":"SELL")+"|"+DoubleToString(entry,Digits())+"|"+DoubleToString(exit_price,Digits())+"|"+DoubleToString(profit,8)+"|"+(ok?"OK":"FAILED"));
}
void OnStart()
{
  if(!SymbolSelect(InpBrokerSymbol,true)){Print("ARKANA OrderCalcProfit validation failed: unavailable symbol");return;}
  for(int attempt=0;attempt<60 && (!TerminalInfoInteger(TERMINAL_CONNECTED) || SymbolInfoDouble(InpBrokerSymbol,SYMBOL_TRADE_TICK_VALUE_PROFIT)<=0 || SymbolInfoDouble(InpBrokerSymbol,SYMBOL_BID)<=0);attempt++) Sleep(500);
  double tick=SymbolInfoDouble(InpBrokerSymbol,SYMBOL_TRADE_TICK_SIZE), bid=SymbolInfoDouble(InpBrokerSymbol,SYMBOL_BID); if(tick<=0||bid<=0){Print("ARKANA OrderCalcProfit validation failed: invalid quote/metadata");return;}
  FolderCreate("ARKANA",FILE_COMMON);FolderCreate("ARKANA\\broker_metadata",FILE_COMMON);
  string metadata_collected_at="";int metadata=FileOpen("ARKANA\\broker_metadata\\latest.ini",FILE_READ|FILE_TXT|FILE_COMMON|FILE_ANSI);if(metadata==INVALID_HANDLE){Print("ARKANA validation failed: run broker metadata exporter first");return;}while(!FileIsEnding(metadata)){string line=FileReadString(metadata);if(StringFind(line,"collected_at=")==0)metadata_collected_at=StringSubstr(line,13);}FileClose(metadata);if(metadata_collected_at==""){Print("ARKANA validation failed: metadata collected_at unavailable");return;}
  int file=FileOpen("ARKANA\\broker_metadata\\order_calc_profit_validation.ini",FILE_WRITE|FILE_TXT|FILE_COMMON|FILE_ANSI);if(file==INVALID_HANDLE){Print("ARKANA validation failed: cannot write FILE_COMMON");return;}
  double move=10.0*tick;FileWrite(file,"schema_version=2");FileWrite(file,"source=MT5_ORDERCALCPROFIT");FileWrite(file,"broker_symbol="+InpBrokerSymbol);FileWrite(file,"metadata_collected_at="+metadata_collected_at);FileWrite(file,"volume="+DoubleToString(InpVolume,8));FileWrite(file,"currency="+AccountInfoString(ACCOUNT_CURRENCY));FileWrite(file,"timestamp="+TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS));
  WriteCase(file,"BUY_WIN",ORDER_TYPE_BUY,bid,bid+move);WriteCase(file,"BUY_LOSS",ORDER_TYPE_BUY,bid,bid-move);WriteCase(file,"SELL_WIN",ORDER_TYPE_SELL,bid,bid-move);WriteCase(file,"SELL_LOSS",ORDER_TYPE_SELL,bid,bid+move);FileClose(file);Print("ARKANA OrderCalcProfit validation exported to FILE_COMMON/ARKANA/broker_metadata/order_calc_profit_validation.ini");
}
