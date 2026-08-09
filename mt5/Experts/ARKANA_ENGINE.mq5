// ARKANA generic DEMO-only execution prototype. No web/API/LLM dependency in OnTick.
#property strict
#property version   "001.000"
#include <Trade/Trade.mqh>

input string InpConfigFile="ARKANA/strategy.ini";
input string InpTelemetryFile="ARKANA/telemetry.csv";
input long   InpMagicNumber=260806;
input int    InpReloadSeconds=10;

CTrade trade;
struct StrategyConfig {
  int schema_version; string strategy_id; string strategy_version; string symbol;
  bool enabled; string allowed_environment; string rule_set; double volume;
  double stop_distance; double target_distance; double max_spread_price;
  int max_open_positions; string checksum;
};
StrategyConfig active;
bool has_config=false;
datetime last_bar=0;

string Trim(const string value) { string output=value; StringTrimLeft(output); StringTrimRight(output); return output; }
bool ToBool(const string value) { string normalized=Trim(value); StringToLower(normalized); return normalized=="true" || normalized=="1"; }
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
  cfg.schema_version=0; cfg.strategy_id=""; cfg.strategy_version=""; cfg.symbol=""; cfg.enabled=false;
  cfg.allowed_environment=""; cfg.rule_set=""; cfg.volume=0.0; cfg.stop_distance=0.0;
  cfg.target_distance=0.0; cfg.max_spread_price=0.0; cfg.max_open_positions=0; cfg.checksum="";
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
  while(!FileIsEnding(handle)) {
    string line=Trim(FileReadString(handle));
    if(line=="" || StringGetCharacter(line,0)=='#' || StringGetCharacter(line,0)==';') continue;
    int separator=StringFind(line,"="); if(separator<1) continue;
    string key=Trim(StringSubstr(line,0,separator)); string value=Trim(StringSubstr(line,separator+1));
    if(key=="schema_version") cfg.schema_version=(int)StringToInteger(value);
    else if(key=="strategy_id") cfg.strategy_id=value;
    else if(key=="strategy_version") cfg.strategy_version=value;
    else if(key=="symbol") cfg.symbol=value;
    else if(key=="enabled") cfg.enabled=ToBool(value);
    else if(key=="allowed_environment") cfg.allowed_environment=value;
    else if(key=="rule_set") cfg.rule_set=value;
    else if(key=="volume") cfg.volume=StringToDouble(value);
    else if(key=="stop_distance") cfg.stop_distance=StringToDouble(value);
    else if(key=="target_distance") cfg.target_distance=StringToDouble(value);
    else if(key=="max_spread_price") cfg.max_spread_price=StringToDouble(value);
    else if(key=="max_open_positions") cfg.max_open_positions=(int)StringToInteger(value);
    else if(key=="checksum") cfg.checksum=value;
  }
  FileClose(handle);
  if(cfg.schema_version!=1 || cfg.strategy_id=="" || cfg.strategy_version=="" || cfg.symbol=="" || cfg.rule_set!="BULLISH_REVERSAL_M1" || cfg.volume<=0 || cfg.stop_distance<=0 || cfg.target_distance<=0 || cfg.max_spread_price<=0 || cfg.max_open_positions<1 || cfg.allowed_environment!="DEMO") {
    Print("ARKANA config rejected: invalid or unsupported fields"); return false;
  }
  if(cfg.symbol!=_Symbol) { Print("ARKANA config rejected: chart symbol differs from config"); return false; }
  if(cfg.checksum=="") { Print("ARKANA config rejected: checksum is required"); return false; }
  return true;
}
void WriteTelemetry(const string decision,const string detail) {
  int handle=FileOpen(InpTelemetryFile,FILE_READ|FILE_WRITE|FILE_CSV|FILE_COMMON|FILE_ANSI,',');
  if(handle==INVALID_HANDLE) return;
  if(FileSize(handle)==0) FileWrite(handle,"timestamp","strategy_id","version","symbol","environment","decision","detail","positions","emergency_stop");
  FileSeek(handle,0,SEEK_END);
  FileWrite(handle,TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS),active.strategy_id,active.strategy_version,_Symbol,"DEMO",decision,detail,PositionsTotal(),EmergencyStop()?"true":"false");
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
