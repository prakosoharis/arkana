#property strict
#property version "1.000"
#property script_show_inputs
input string InpBrokerSymbol="XAUUSD.m";

void WriteCase(int file,string id,ENUM_ORDER_TYPE type,double volume,double price)
{
  double margin=0.0; bool ok=OrderCalcMargin(type,InpBrokerSymbol,volume,price,margin);
  FileWrite(file,"case="+id+"|"+(type==ORDER_TYPE_BUY?"BUY":"SELL")+"|"+DoubleToString(volume,8)+"|"+DoubleToString(price,Digits())+"|"+DoubleToString(margin,8)+"|"+(ok?"OK":"FAILED"));
}

void OnStart()
{
  if(!SymbolSelect(InpBrokerSymbol,true)){Print("ARKANA OrderCalcMargin validation failed: unavailable symbol");return;}
  for(int attempt=0;attempt<60 && (!TerminalInfoInteger(TERMINAL_CONNECTED) || SymbolInfoDouble(InpBrokerSymbol,SYMBOL_BID)<=0);attempt++) Sleep(500);
  double minimum=SymbolInfoDouble(InpBrokerSymbol,SYMBOL_VOLUME_MIN),step=SymbolInfoDouble(InpBrokerSymbol,SYMBOL_VOLUME_STEP),bid=SymbolInfoDouble(InpBrokerSymbol,SYMBOL_BID),ask=SymbolInfoDouble(InpBrokerSymbol,SYMBOL_ASK),tick=SymbolInfoDouble(InpBrokerSymbol,SYMBOL_TRADE_TICK_SIZE);
  if(minimum<=0||step<=0||bid<=0||ask<=0||tick<=0){Print("ARKANA OrderCalcMargin validation failed: invalid quote/metadata");return;}
  FolderCreate("ARKANA",FILE_COMMON);FolderCreate("ARKANA\\broker_metadata",FILE_COMMON);
  string collected="";int metadata=FileOpen("ARKANA\\broker_metadata\\latest.ini",FILE_READ|FILE_TXT|FILE_COMMON|FILE_ANSI);if(metadata==INVALID_HANDLE){Print("ARKANA margin validation failed: run broker metadata exporter first");return;}while(!FileIsEnding(metadata)){string line=FileReadString(metadata);if(StringFind(line,"collected_at=")==0)collected=StringSubstr(line,13);}FileClose(metadata);if(collected==""){Print("ARKANA margin validation failed: metadata collected_at unavailable");return;}
  int file=FileOpen("ARKANA\\broker_metadata\\order_calc_margin_validation.ini",FILE_WRITE|FILE_TXT|FILE_COMMON|FILE_ANSI);if(file==INVALID_HANDLE){Print("ARKANA margin validation failed: cannot write FILE_COMMON");return;}
  FileWrite(file,"schema_version=1");FileWrite(file,"source=MT5_ORDERCALCMARGIN");FileWrite(file,"broker_symbol="+InpBrokerSymbol);FileWrite(file,"metadata_collected_at="+collected);FileWrite(file,"currency="+AccountInfoString(ACCOUNT_CURRENCY));FileWrite(file,"timestamp="+TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS));
  WriteCase(file,"BUY_MIN",ORDER_TYPE_BUY,minimum,ask);WriteCase(file,"SELL_MIN",ORDER_TYPE_SELL,minimum,bid);WriteCase(file,"BUY_STEP",ORDER_TYPE_BUY,minimum+step,ask+100.0*tick);WriteCase(file,"SELL_STEP",ORDER_TYPE_SELL,minimum+step,bid+100.0*tick);
  FileClose(file);Print("ARKANA OrderCalcMargin validation exported to FILE_COMMON/ARKANA/broker_metadata/order_calc_margin_validation.ini");
}
