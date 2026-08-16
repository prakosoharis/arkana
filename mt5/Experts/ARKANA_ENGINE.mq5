// ARKANA generic DEMO-only execution prototype. No web/API/LLM dependency in OnTick.
#property strict
#property version   "001.000"
#include <Trade/Trade.mqh>

input string InpConfigFile="ARKANA/strategy.ini";
input string InpTelemetryFile="ARKANA/telemetry.csv";
input string InpTradeTelemetryFile="ARKANA/trades.csv";
input long   InpMagicNumber=260806;
input int    InpReloadSeconds=10;

CTrade trade;
struct StrategyConfig {
  int schema_version; string strategy_id; string strategy_version; string canonical_instrument; string broker_symbol;
  bool enabled; string allowed_environment; string rule_set; double volume;
  double stop_distance; double target_distance; double max_spread_price;
  int max_open_positions; string checksum;
  // Preserve wire values so the accepted file has one unambiguous serialization.
  string volume_text; string stop_distance_text; string target_distance_text; string max_spread_price_text; string max_open_positions_text;
};
StrategyConfig active;
bool has_config=false;
datetime last_bar=0;

string Trim(const string value) { string output=value; StringTrimLeft(output); StringTrimRight(output); return output; }
bool ToBool(const string value) { string normalized=Trim(value); StringToLower(normalized); return normalized=="true" || normalized=="1"; }
bool IsDecimalDigits(const string value) {
  if(value=="") return false;
  for(int index=0;index<StringLen(value);index++) { int character=(int)StringGetCharacter(value,index); if(character<'0' || character>'9') return false; }
  return true;
}
string CommonConfigPath() {
  string relative=InpConfigFile; StringReplace(relative,"/","\\");
  return TerminalInfoString(TERMINAL_COMMONDATA_PATH)+"\\Files\\"+relative;
}
void PrepareCommonConfigFolder() {
  string folder=InpConfigFile; int slash=StringFind(folder,"/");
  if(slash>0) folder=StringSubstr(folder,0,slash);
  // FolderCreate is idempotent for this FILE_COMMON sandbox path on supported MT5 builds.
  if(folder!="") FolderCreate(folder,FILE_COMMON);
  Print("ARKANA TERMINAL_COMMONDATA_PATH: ",TerminalInfoString(TERMINAL_COMMONDATA_PATH));
  if(!FileIsExist(InpConfigFile,FILE_COMMON)) Print("ARKANA strategy.ini is missing. Copy a disabled config to: ",CommonConfigPath());
}
void ResetConfig(StrategyConfig &cfg) {
  cfg.schema_version=0; cfg.strategy_id=""; cfg.strategy_version=""; cfg.canonical_instrument=""; cfg.broker_symbol=""; cfg.enabled=false;
  cfg.allowed_environment=""; cfg.rule_set=""; cfg.volume=0.0; cfg.stop_distance=0.0;
  cfg.target_distance=0.0; cfg.max_spread_price=0.0; cfg.max_open_positions=0; cfg.checksum="";
  cfg.volume_text=""; cfg.stop_distance_text=""; cfg.target_distance_text=""; cfg.max_spread_price_text=""; cfg.max_open_positions_text="";
}
string ConfigChecksumV1(const StrategyConfig &cfg) {
  string payload=IntegerToString(cfg.schema_version)+"|"+cfg.strategy_id+"|"+cfg.strategy_version+"|"+cfg.canonical_instrument+"|"+cfg.broker_symbol+"|"+(cfg.enabled?"true":"false")+"|"+cfg.allowed_environment+"|"+cfg.rule_set+"|"+DoubleToString(cfg.volume,8)+"|"+DoubleToString(cfg.stop_distance,8)+"|"+DoubleToString(cfg.target_distance,8)+"|"+DoubleToString(cfg.max_spread_price,8)+"|"+IntegerToString(cfg.max_open_positions);
  long value=0;
  for(int index=0;index<StringLen(payload);index++) value=(value+(long)StringGetCharacter(payload,index))%2147483647;
  return IntegerToString((int)value);
}
bool IsDemoAccount() { return (ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO; }
bool EmergencyStop() { return GlobalVariableCheck("ARKANA_EMERGENCY_STOP") && GlobalVariableGet("ARKANA_EMERGENCY_STOP")>0.0; }
bool HasOurPosition(const string symbol) {
  for(int index=PositionsTotal()-1;index>=0;index--) {
    ulong ticket=PositionGetTicket(index);
    if(ticket>0 && PositionGetString(POSITION_SYMBOL)==symbol && PositionGetInteger(POSITION_MAGIC)==InpMagicNumber) return true;
  }
  return false;
}
bool ReadConfig(StrategyConfig &cfg) {
  ResetConfig(cfg);
  int handle=FileOpen(InpConfigFile,FILE_READ|FILE_TXT|FILE_COMMON|FILE_ANSI);
  if(handle==INVALID_HANDLE) { Print("ARKANA config unavailable: ",InpConfigFile); return false; }
  string seen="|";
  while(!FileIsEnding(handle)) {
    string line=Trim(FileReadString(handle));
    if(line=="" || StringGetCharacter(line,0)=='#' || StringGetCharacter(line,0)==';') continue;
    int separator=StringFind(line,"=");
    if(separator<1 || StringFind(line,"=",separator+1)>=0) { FileClose(handle); Print("ARKANA config rejected: invalid field serialization"); return false; }
    string key=Trim(StringSubstr(line,0,separator)); string value=Trim(StringSubstr(line,separator+1));
    if(StringFind(seen,"|"+key+"|")>=0) { FileClose(handle); Print("ARKANA config rejected: duplicate field ",key); return false; }
    if(key=="schema_version") cfg.schema_version=(int)StringToInteger(value);
    else if(key=="strategy_id") cfg.strategy_id=value;
    else if(key=="strategy_version") cfg.strategy_version=value;
    else if(key=="canonical_instrument") cfg.canonical_instrument=value;
    else if(key=="broker_symbol") cfg.broker_symbol=value;
    else if(key=="enabled") { if(value!="true" && value!="false") { FileClose(handle); Print("ARKANA config rejected: enabled must be true or false"); return false; } cfg.enabled=(value=="true"); }
    else if(key=="allowed_environment") cfg.allowed_environment=value;
    else if(key=="rule_set") cfg.rule_set=value;
    else if(key=="volume") { cfg.volume_text=value; cfg.volume=StringToDouble(value); }
    else if(key=="stop_distance") { cfg.stop_distance_text=value; cfg.stop_distance=StringToDouble(value); }
    else if(key=="target_distance") { cfg.target_distance_text=value; cfg.target_distance=StringToDouble(value); }
    else if(key=="max_spread_price") { cfg.max_spread_price_text=value; cfg.max_spread_price=StringToDouble(value); }
    else if(key=="max_open_positions") { cfg.max_open_positions_text=value; cfg.max_open_positions=(int)StringToInteger(value); }
    else if(key=="checksum") cfg.checksum=value;
    else { FileClose(handle); Print("ARKANA config rejected: unknown field ",key); return false; }
    seen+=key+"|";
  }
  FileClose(handle);
  string required[]={"schema_version","strategy_id","strategy_version","canonical_instrument","broker_symbol","enabled","allowed_environment","rule_set","volume","stop_distance","target_distance","max_spread_price","max_open_positions","checksum"};
  for(int index=0;index<ArraySize(required);index++) if(StringFind(seen,"|"+required[index]+"|")<0) { Print("ARKANA config rejected: missing mandatory field ",required[index]); return false; }
  if(cfg.schema_version!=1) { Print("ARKANA config rejected: unsupported schema_version"); return false; }
  if(cfg.strategy_id=="" || cfg.strategy_version=="" || cfg.canonical_instrument=="" || cfg.broker_symbol=="") { Print("ARKANA config rejected: strategy identity or broker_symbol is empty"); return false; }
  if(cfg.allowed_environment!="DEMO") { Print("ARKANA config rejected: allowed_environment must be DEMO"); return false; }
  if(cfg.rule_set!="BULLISH_REVERSAL_M1") { Print("ARKANA config rejected: unsupported rule_set"); return false; }
  if(cfg.volume<=0 || cfg.stop_distance<=0 || cfg.target_distance<=0 || cfg.max_spread_price<=0 || cfg.max_open_positions<1) { Print("ARKANA config rejected: invalid positive risk parameter"); return false; }
  if(cfg.volume_text!=DoubleToString(cfg.volume,8)) { Print("ARKANA config rejected: non-canonical numeric serialization: volume"); return false; }
  if(cfg.stop_distance_text!=DoubleToString(cfg.stop_distance,8)) { Print("ARKANA config rejected: non-canonical numeric serialization: stop_distance"); return false; }
  if(cfg.target_distance_text!=DoubleToString(cfg.target_distance,8)) { Print("ARKANA config rejected: non-canonical numeric serialization: target_distance"); return false; }
  if(cfg.max_spread_price_text!=DoubleToString(cfg.max_spread_price,8)) { Print("ARKANA config rejected: non-canonical numeric serialization: max_spread_price"); return false; }
  if(cfg.max_open_positions_text!=IntegerToString(cfg.max_open_positions)) { Print("ARKANA config rejected: non-canonical numeric serialization: max_open_positions"); return false; }
  if(cfg.broker_symbol!=_Symbol) { Print("ARKANA config rejected: broker symbol differs from current chart"); return false; }
  if(cfg.checksum=="") { Print("ARKANA config rejected: checksum is required"); return false; }
  if(!IsDecimalDigits(cfg.checksum) || cfg.checksum!=IntegerToString((int)StringToInteger(cfg.checksum))) { Print("ARKANA config rejected: non-canonical numeric serialization: checksum"); return false; }
  if(cfg.checksum!=ConfigChecksumV1(cfg)) { Print("ARKANA config rejected: checksum mismatch"); return false; }
  return true;
}
void WriteTelemetry(const string decision,const string detail) {
  int handle=FileOpen(InpTelemetryFile,FILE_READ|FILE_WRITE|FILE_CSV|FILE_COMMON|FILE_ANSI,',');
  if(handle==INVALID_HANDLE) return;
  if(FileSize(handle)==0) FileWrite(handle,"timestamp","strategy_id","version","broker_symbol","environment","decision","detail","positions","emergency_stop");
  FileSeek(handle,0,SEEK_END);
  FileWrite(handle,TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS),active.strategy_id,active.strategy_version,active.broker_symbol,"DEMO",decision,detail,PositionsTotal(),EmergencyStop()?"true":"false");
  FileClose(handle);
}
void WriteTradeTelemetry(const ulong deal_ticket) {
  // Deal capture is emitted by MT5's trade-transaction callback, never by Web/API/DB and never by an HTTP request.
  if(!HistoryDealSelect(deal_ticket)) return;
  if((long)HistoryDealGetInteger(deal_ticket,DEAL_MAGIC)!=InpMagicNumber || HistoryDealGetString(deal_ticket,DEAL_SYMBOL)!=_Symbol) return;
  ENUM_DEAL_ENTRY entry=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(deal_ticket,DEAL_ENTRY);
  if(entry!=DEAL_ENTRY_IN && entry!=DEAL_ENTRY_OUT && entry!=DEAL_ENTRY_OUT_BY) return;
  ENUM_DEAL_TYPE type=(ENUM_DEAL_TYPE)HistoryDealGetInteger(deal_ticket,DEAL_TYPE);
  string side=(type==DEAL_TYPE_BUY?"LONG":type==DEAL_TYPE_SELL?"SHORT":"NOT_REPORTED");
  string decision=(entry==DEAL_ENTRY_IN?"DEAL_ENTRY":"DEAL_EXIT");
  string exit_reason=IntegerToString((int)HistoryDealGetInteger(deal_ticket,DEAL_REASON));
  double profit=HistoryDealGetDouble(deal_ticket,DEAL_PROFIT);
  double commission=HistoryDealGetDouble(deal_ticket,DEAL_COMMISSION);
  double swap=HistoryDealGetDouble(deal_ticket,DEAL_SWAP);
  double net=profit+commission+swap;
  int handle=FileOpen(InpTradeTelemetryFile,FILE_READ|FILE_WRITE|FILE_CSV|FILE_COMMON|FILE_ANSI,',');
  if(handle==INVALID_HANDLE) return;
  if(FileSize(handle)==0) FileWrite(handle,"timestamp","strategy_id","version","broker_symbol","environment","decision","detail","positions","emergency_stop","checksum","deal_ticket","position_id","side","price","stop_loss","take_profit","volume","exit_reason","realized_pnl","commission","swap","spread_price");
  FileSeek(handle,0,SEEK_END);
  FileWrite(handle,TimeToString((datetime)HistoryDealGetInteger(deal_ticket,DEAL_TIME),TIME_DATE|TIME_SECONDS),active.strategy_id,active.strategy_version,active.broker_symbol,"DEMO",decision,"MT5 deal transaction",PositionsTotal(),EmergencyStop()?"true":"false",active.checksum,(string)deal_ticket,(string)HistoryDealGetInteger(deal_ticket,DEAL_POSITION_ID),side,DoubleToString(HistoryDealGetDouble(deal_ticket,DEAL_PRICE),_Digits),"","",DoubleToString(HistoryDealGetDouble(deal_ticket,DEAL_VOLUME),2),exit_reason,entry==DEAL_ENTRY_IN?"":DoubleToString(net,2),DoubleToString(commission,2),DoubleToString(swap,2),"");
  FileClose(handle);
}
bool IsNewM1Bar() {
  datetime time=iTime(_Symbol,PERIOD_M1,0); if(time==0 || time==last_bar) return false; last_bar=time; return true;
}
void ReloadConfig() {
  StrategyConfig candidate;
  if(ReadConfig(candidate)) { active=candidate; has_config=true; WriteTelemetry("CONFIG_LOADED",active.checksum); }
  else if(has_config) WriteTelemetry("CONFIG_RELOAD_REJECTED","Using last valid cached configuration");
  else WriteTelemetry("NO_VALID_CONFIG","No trading permitted");
}
int OnInit() {
  PrepareCommonConfigFolder();
  if(!IsDemoAccount()) { Print("ARKANA refuses non-DEMO account"); return INIT_FAILED; }
  trade.SetExpertMagicNumber(InpMagicNumber); trade.SetTypeFillingBySymbol(_Symbol);
  ReloadConfig(); EventSetTimer(MathMax(InpReloadSeconds,5)); WriteTelemetry("HEARTBEAT","EA initialized"); return INIT_SUCCEEDED;
}
void OnDeinit(const int reason) { EventKillTimer(); WriteTelemetry("HEARTBEAT_STOP",IntegerToString(reason)); }
void OnTimer() { ReloadConfig(); WriteTelemetry("HEARTBEAT",has_config?"cached config active":"no valid config"); }
void OnTradeTransaction(const MqlTradeTransaction &transaction,const MqlTradeRequest &request,const MqlTradeResult &result) {
  if(transaction.type==TRADE_TRANSACTION_DEAL_ADD && transaction.deal>0 && has_config) WriteTradeTelemetry(transaction.deal);
}
void OnTick() {
  if(!IsNewM1Bar()) return;
  if(!IsDemoAccount() || EmergencyStop() || !has_config || !active.enabled) { WriteTelemetry("NO_TRADE","guard: demo/emergency/config/enabled"); return; }
  if(HasOurPosition(_Symbol)) { WriteTelemetry("NO_TRADE","existing ARKANA position"); return; }
  MqlTick tick; if(!SymbolInfoTick(_Symbol,tick)) return;
  if((tick.ask-tick.bid)>active.max_spread_price) { WriteTelemetry("NO_TRADE","spread guard"); return; }
  MqlRates rates[]; ArraySetAsSeries(rates,true);
  if(CopyRates(_Symbol,PERIOD_M1,0,3,rates)<3) return;
  bool bearish_then_bullish=rates[2].close<rates[2].open && rates[1].close>rates[1].open;
  if(!bearish_then_bullish) { WriteTelemetry("NO_TRADE","no BULLISH_REVERSAL_M1 signal"); return; }
  double ask=SymbolInfoDouble(_Symbol,SYMBOL_ASK);
  double sl=NormalizeDouble(ask-active.stop_distance,_Digits); double tp=NormalizeDouble(ask+active.target_distance,_Digits);
  if(!trade.Buy(active.volume,_Symbol,ask,sl,tp,"ARKANA "+active.strategy_id+" "+active.strategy_version)) WriteTelemetry("ORDER_REJECTED",trade.ResultRetcodeDescription());
  else WriteTelemetry("LONG",DoubleToString(ask,_Digits));
}
