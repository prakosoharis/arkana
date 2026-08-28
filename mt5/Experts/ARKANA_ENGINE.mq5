// ARKANA generic DEMO-only execution prototype. No web/API/LLM dependency in OnTick.
#property strict
#property version   "2.000"
#include <Trade/Trade.mqh>

input string InpConfigFile="ARKANA/strategy.ini";
input string InpTelemetryFile="ARKANA/telemetry.csv";
input string InpTradeTelemetryFile="ARKANA/trades.csv";
input string InpGenericPublicationFile="ARKANA/generic/publication.ini";
input string InpGenericAcknowledgementFile="ARKANA/generic/acknowledgement.csv";
input string InpGenericTelemetryFile="ARKANA/generic/telemetry.csv";
input string InpGenericControlFile="ARKANA/generic/control.ini";
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
struct GenericPublication {
  string publication_protocol_version; string publication_id; string target_environment;
  string target_account_login; string target_account_server; string target_reference;
  string broker_symbol; string strategy_version_id; string compiler_protocol_version;
  string adapter_capability_id; string config_checksum; string config_file;
  string published_at; string publication_checksum;
};
struct GenericConfig {
  string schema_version; string compiler_protocol_version; string adapter_capability_id;
  string generic_demo_contract_id; string generic_demo_contract_fingerprint;
  string strategy_version_id; string strategy_checksum; string canonical_instrument;
  string broker_symbol; string enabled; string allowed_environment; string direction;
  string execution_timeframe; string context_rule; string context_timeframe;
  string sma_fast_period; string sma_slow_period; string sma_relation; string setup_rule;
  string setup_timeframe; string setup_direction; string trigger_rule;
  string trigger_timeframe; string trigger_direction; string entry_rule;
  string entry_price_source; string uses_completed_candles; string uses_future_ohlc;
  string invalidation_rule; string volume; string stop_rule; string stop_distance;
  string target_rule; string target_distance; string spread_guard; string max_spread_price;
  string max_open_positions; string ambiguity_policy; string emergency_stop_source;
  string emergency_stop_variable; string emergency_stop_condition;
  string emergency_stop_action; string force_close_positions; string checksum;
};
struct GenericControl {
  string control_protocol_version; string publication_id; string config_checksum;
  string action; string reason_code; string issued_at; string control_checksum;
};
GenericPublication active_publication;
GenericConfig active_generic;
bool has_generic_config=false;
bool generic_entries_blocked=false;
datetime last_bar=0;

string Trim(const string value) { string output=value; StringTrimLeft(output); StringTrimRight(output); return output; }
bool ToBool(const string value) { string normalized=Trim(value); StringToLower(normalized); return normalized=="true" || normalized=="1"; }
bool IsDecimalDigits(const string value) {
  if(value=="") return false;
  for(int index=0;index<StringLen(value);index++) { int character=(int)StringGetCharacter(value,index); if(character<'0' || character>'9') return false; }
  return true;
}
string Sha256Hex(const string payload) {
  uchar source[],key[],digest[];
  int length=StringToCharArray(payload,source,0,WHOLE_ARRAY,CP_UTF8);
  if(length<=1) return "";
  ArrayResize(source,length-1); ArrayResize(key,0);
  if(CryptEncode(CRYPT_HASH_SHA256,source,key,digest)!=32) return "";
  string output="";
  for(int index=0;index<ArraySize(digest);index++) output+=StringFormat("%02x",(int)digest[index]);
  return output;
}
bool ReadLineField(const int handle,string &seen,string &key,string &value) {
  string line=Trim(FileReadString(handle));
  if(line=="" || StringGetCharacter(line,0)=='#' || StringGetCharacter(line,0)==';') return false;
  int separator=StringFind(line,"=");
  if(separator<1 || StringFind(line,"=",separator+1)>=0) { key="!INVALID!"; return true; }
  key=Trim(StringSubstr(line,0,separator)); value=StringSubstr(line,separator+1);
  if(value=="" || StringFind(seen,"|"+key+"|")>=0) { key="!INVALID!"; return true; }
  seen+=key+"|"; return true;
}
bool HasFields(const string seen,const string &required[]) {
  for(int index=0;index<ArraySize(required);index++) if(StringFind(seen,"|"+required[index]+"|")<0) return false;
  return true;
}
string PublicationPayload(const GenericPublication &item) {
  return "publication_protocol_version="+item.publication_protocol_version+"\npublication_id="+item.publication_id+"\ntarget_environment="+item.target_environment+"\ntarget_account_login="+item.target_account_login+"\ntarget_account_server="+item.target_account_server+"\ntarget_reference="+item.target_reference+"\nbroker_symbol="+item.broker_symbol+"\nstrategy_version_id="+item.strategy_version_id+"\ncompiler_protocol_version="+item.compiler_protocol_version+"\nadapter_capability_id="+item.adapter_capability_id+"\nconfig_checksum="+item.config_checksum+"\nconfig_file="+item.config_file+"\npublished_at="+item.published_at+"\n";
}
bool ReadGenericPublication(GenericPublication &item) {
  ZeroMemory(item);
  int handle=FileOpen(InpGenericPublicationFile,FILE_READ|FILE_TXT|FILE_COMMON|FILE_ANSI);
  if(handle==INVALID_HANDLE) return false;
  string seen="|";
  while(!FileIsEnding(handle)) {
    string key="",value=""; if(!ReadLineField(handle,seen,key,value)) continue;
    if(key=="publication_protocol_version") item.publication_protocol_version=value;
    else if(key=="publication_id") item.publication_id=value;
    else if(key=="target_environment") item.target_environment=value;
    else if(key=="target_account_login") item.target_account_login=value;
    else if(key=="target_account_server") item.target_account_server=value;
    else if(key=="target_reference") item.target_reference=value;
    else if(key=="broker_symbol") item.broker_symbol=value;
    else if(key=="strategy_version_id") item.strategy_version_id=value;
    else if(key=="compiler_protocol_version") item.compiler_protocol_version=value;
    else if(key=="adapter_capability_id") item.adapter_capability_id=value;
    else if(key=="config_checksum") item.config_checksum=value;
    else if(key=="config_file") item.config_file=value;
    else if(key=="published_at") item.published_at=value;
    else if(key=="publication_checksum") item.publication_checksum=value;
    else { FileClose(handle); return false; }
  }
  FileClose(handle);
  string required[]={"publication_protocol_version","publication_id","target_environment","target_account_login","target_account_server","target_reference","broker_symbol","strategy_version_id","compiler_protocol_version","adapter_capability_id","config_checksum","config_file","published_at","publication_checksum"};
  if(!HasFields(seen,required)) return false;
  if(item.publication_protocol_version!="GENERIC_MT5_DEMO_PUBLICATION_V1" || item.target_environment!="DEMO") return false;
  if(item.compiler_protocol_version!="GENERIC_STRATEGY_MT5_COMPILER_V1" || item.adapter_capability_id!="GENERIC_SMA_REVERSAL_LONG_M1_V2") return false;
  if(item.broker_symbol!=_Symbol || item.target_account_login!=IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN))) return false;
  if(item.target_account_server!=AccountInfoString(ACCOUNT_SERVER) || !IsDemoAccount()) return false;
  if(item.config_file!="ARKANA/generic/config-"+item.config_checksum+".ini") return false;
  if(Sha256Hex(PublicationPayload(item))!=item.publication_checksum) return false;
  return true;
}
string GenericConfigPayload(const GenericConfig &cfg) {
  return "schema_version="+cfg.schema_version+"\ncompiler_protocol_version="+cfg.compiler_protocol_version+"\nadapter_capability_id="+cfg.adapter_capability_id+"\ngeneric_demo_contract_id="+cfg.generic_demo_contract_id+"\ngeneric_demo_contract_fingerprint="+cfg.generic_demo_contract_fingerprint+"\nstrategy_version_id="+cfg.strategy_version_id+"\nstrategy_checksum="+cfg.strategy_checksum+"\ncanonical_instrument="+cfg.canonical_instrument+"\nbroker_symbol="+cfg.broker_symbol+"\nenabled="+cfg.enabled+"\nallowed_environment="+cfg.allowed_environment+"\ndirection="+cfg.direction+"\nexecution_timeframe="+cfg.execution_timeframe+"\ncontext_rule="+cfg.context_rule+"\ncontext_timeframe="+cfg.context_timeframe+"\nsma_fast_period="+cfg.sma_fast_period+"\nsma_slow_period="+cfg.sma_slow_period+"\nsma_relation="+cfg.sma_relation+"\nsetup_rule="+cfg.setup_rule+"\nsetup_timeframe="+cfg.setup_timeframe+"\nsetup_direction="+cfg.setup_direction+"\ntrigger_rule="+cfg.trigger_rule+"\ntrigger_timeframe="+cfg.trigger_timeframe+"\ntrigger_direction="+cfg.trigger_direction+"\nentry_rule="+cfg.entry_rule+"\nentry_price_source="+cfg.entry_price_source+"\nuses_completed_candles="+cfg.uses_completed_candles+"\nuses_future_ohlc="+cfg.uses_future_ohlc+"\ninvalidation_rule="+cfg.invalidation_rule+"\nvolume="+cfg.volume+"\nstop_rule="+cfg.stop_rule+"\nstop_distance="+cfg.stop_distance+"\ntarget_rule="+cfg.target_rule+"\ntarget_distance="+cfg.target_distance+"\nspread_guard="+cfg.spread_guard+"\nmax_spread_price="+cfg.max_spread_price+"\nmax_open_positions="+cfg.max_open_positions+"\nsession_clock="+cfg.session_clock+"\nsession_windows="+cfg.session_windows+"\nambiguity_policy="+cfg.ambiguity_policy+"\nemergency_stop_source="+cfg.emergency_stop_source+"\nemergency_stop_variable="+cfg.emergency_stop_variable+"\nemergency_stop_condition="+cfg.emergency_stop_condition+"\nemergency_stop_action="+cfg.emergency_stop_action+"\nforce_close_positions="+cfg.force_close_positions+"\n";
}
bool AssignGenericField(GenericConfig &cfg,const string key,const string value) {
  if(key=="schema_version") cfg.schema_version=value; else if(key=="compiler_protocol_version") cfg.compiler_protocol_version=value;
  else if(key=="adapter_capability_id") cfg.adapter_capability_id=value; else if(key=="generic_demo_contract_id") cfg.generic_demo_contract_id=value;
  else if(key=="generic_demo_contract_fingerprint") cfg.generic_demo_contract_fingerprint=value; else if(key=="strategy_version_id") cfg.strategy_version_id=value;
  else if(key=="strategy_checksum") cfg.strategy_checksum=value; else if(key=="canonical_instrument") cfg.canonical_instrument=value;
  else if(key=="broker_symbol") cfg.broker_symbol=value; else if(key=="enabled") cfg.enabled=value; else if(key=="allowed_environment") cfg.allowed_environment=value;
  else if(key=="direction") cfg.direction=value; else if(key=="execution_timeframe") cfg.execution_timeframe=value; else if(key=="context_rule") cfg.context_rule=value;
  else if(key=="context_timeframe") cfg.context_timeframe=value; else if(key=="sma_fast_period") cfg.sma_fast_period=value; else if(key=="sma_slow_period") cfg.sma_slow_period=value;
  else if(key=="sma_relation") cfg.sma_relation=value; else if(key=="setup_rule") cfg.setup_rule=value; else if(key=="setup_timeframe") cfg.setup_timeframe=value;
  else if(key=="setup_direction") cfg.setup_direction=value; else if(key=="trigger_rule") cfg.trigger_rule=value; else if(key=="trigger_timeframe") cfg.trigger_timeframe=value;
  else if(key=="trigger_direction") cfg.trigger_direction=value; else if(key=="entry_rule") cfg.entry_rule=value; else if(key=="entry_price_source") cfg.entry_price_source=value;
  else if(key=="uses_completed_candles") cfg.uses_completed_candles=value; else if(key=="uses_future_ohlc") cfg.uses_future_ohlc=value; else if(key=="invalidation_rule") cfg.invalidation_rule=value;
  else if(key=="volume") cfg.volume=value; else if(key=="stop_rule") cfg.stop_rule=value; else if(key=="stop_distance") cfg.stop_distance=value;
  else if(key=="target_rule") cfg.target_rule=value; else if(key=="target_distance") cfg.target_distance=value; else if(key=="spread_guard") cfg.spread_guard=value;
  else if(key=="max_spread_price") cfg.max_spread_price=value; else if(key=="max_open_positions") cfg.max_open_positions=value; else if(key=="session_clock") cfg.session_clock=value;
  else if(key=="session_windows") cfg.session_windows=value; else if(key=="ambiguity_policy") cfg.ambiguity_policy=value;
  else if(key=="emergency_stop_source") cfg.emergency_stop_source=value; else if(key=="emergency_stop_variable") cfg.emergency_stop_variable=value; else if(key=="emergency_stop_condition") cfg.emergency_stop_condition=value;
  else if(key=="emergency_stop_action") cfg.emergency_stop_action=value; else if(key=="force_close_positions") cfg.force_close_positions=value; else if(key=="checksum") cfg.checksum=value;
  else return false; return true;
}
// ARK-S24-01. Windows are broker-time, which is the same clock TimeCurrent()
// reports, so no offset conversion is performed or needed.
int g_session_start[]; int g_session_end[]; int g_session_count=0;
bool ParseSessionWindows(const string clock,const string windows) {
  g_session_count=0; ArrayResize(g_session_start,0); ArrayResize(g_session_end,0);
  if(clock=="NONE") return windows=="NONE";
  if(clock!="BROKER_TIME" || windows=="NONE" || windows=="") return false;
  string parts[]; int count=StringSplit(windows,',',parts);
  if(count<1) return false;
  int previous_end=-1;
  for(int index=0;index<count;index++) {
    string part=parts[index];
    if(StringLen(part)!=5 || StringGetCharacter(part,2)!='-') return false;
    string a=StringSubstr(part,0,2), b=StringSubstr(part,3,2);
    if(!IsDecimalDigits(a) || !IsDecimalDigits(b)) return false;
    int start=(int)StringToInteger(a), end=(int)StringToInteger(b);
    if(start<0 || start>23 || end<0 || end>23 || start>end) return false;
    if(start<=previous_end) return false;   // ascending and non-overlapping
    previous_end=end;
    ArrayResize(g_session_start,g_session_count+1); ArrayResize(g_session_end,g_session_count+1);
    g_session_start[g_session_count]=start; g_session_end[g_session_count]=end; g_session_count++;
  }
  return g_session_count>0;
}
bool SessionAllows(const datetime moment) {
  if(g_session_count==0) return true;
  MqlDateTime parts; TimeToStruct(moment,parts);
  for(int index=0;index<g_session_count;index++)
    if(parts.hour>=g_session_start[index] && parts.hour<=g_session_end[index]) return true;
  return false;
}
bool ReadGenericConfig(const string file,GenericConfig &cfg) {
  ZeroMemory(cfg); int handle=FileOpen(file,FILE_READ|FILE_TXT|FILE_COMMON|FILE_ANSI); if(handle==INVALID_HANDLE) return false;
  string seen="|";
  while(!FileIsEnding(handle)) { string key="",value=""; if(!ReadLineField(handle,seen,key,value)) continue; if(!AssignGenericField(cfg,key,value)) { FileClose(handle); return false; } }
  FileClose(handle);
  string required[]={"schema_version","compiler_protocol_version","adapter_capability_id","generic_demo_contract_id","generic_demo_contract_fingerprint","strategy_version_id","strategy_checksum","canonical_instrument","broker_symbol","enabled","allowed_environment","direction","execution_timeframe","context_rule","context_timeframe","sma_fast_period","sma_slow_period","sma_relation","setup_rule","setup_timeframe","setup_direction","trigger_rule","trigger_timeframe","trigger_direction","entry_rule","entry_price_source","uses_completed_candles","uses_future_ohlc","invalidation_rule","volume","stop_rule","stop_distance","target_rule","target_distance","spread_guard","max_spread_price","max_open_positions","session_clock","session_windows","ambiguity_policy","emergency_stop_source","emergency_stop_variable","emergency_stop_condition","emergency_stop_action","force_close_positions","checksum"};
  if(!HasFields(seen,required) || Sha256Hex(GenericConfigPayload(cfg))!=cfg.checksum) return false;
  if(cfg.schema_version!="2" || cfg.compiler_protocol_version!="GENERIC_STRATEGY_MT5_COMPILER_V1" || cfg.adapter_capability_id!="GENERIC_SMA_REVERSAL_LONG_M1_V2") return false;
  if(cfg.canonical_instrument!="XAUUSD" || cfg.broker_symbol!=_Symbol || cfg.enabled!="true" || cfg.allowed_environment!="DEMO" || (cfg.direction!="LONG" && cfg.direction!="SHORT") || cfg.execution_timeframe!="M1") return false;
  if(cfg.context_rule!="SMA_RELATION" || cfg.context_timeframe!="M1" || cfg.sma_relation!="ABOVE" || cfg.setup_rule!="TWO_BAR_REVERSAL" || cfg.setup_timeframe!="M1" || (cfg.setup_direction!="BULLISH" && cfg.setup_direction!="BEARISH")) return false;
  if(cfg.trigger_rule!="CANDLE_DIRECTION" || cfg.trigger_timeframe!="M1" || cfg.trigger_direction!=cfg.setup_direction || cfg.entry_rule!="NEXT_BAR_OPEN" || cfg.entry_price_source!="MT5_ASK_FIRST_TICK_NEXT_M1") return false;
  if(cfg.uses_completed_candles!="true" || cfg.uses_future_ohlc!="false" || cfg.invalidation_rule!="ALWAYS" || cfg.stop_rule!="FIXED_PRICE_DISTANCE_SL" || cfg.target_rule!="FIXED_PRICE_DISTANCE_TP") return false;
  if(!ParseSessionWindows(cfg.session_clock,cfg.session_windows)) return false;
  if(cfg.spread_guard!="FIXED_SPREAD_GUARD" || cfg.max_open_positions!="1" || cfg.ambiguity_policy!="STOP_FIRST" || cfg.emergency_stop_variable!="ARKANA_EMERGENCY_STOP" || cfg.force_close_positions!="false") return false;
  int fast=(int)StringToInteger(cfg.sma_fast_period),slow=(int)StringToInteger(cfg.sma_slow_period);
  if(fast<=0 || slow<=fast || slow>1000 || DoubleToString(StringToDouble(cfg.volume),8)!=cfg.volume || DoubleToString(StringToDouble(cfg.stop_distance),8)!=cfg.stop_distance || DoubleToString(StringToDouble(cfg.target_distance),8)!=cfg.target_distance || DoubleToString(StringToDouble(cfg.max_spread_price),8)!=cfg.max_spread_price) return false;
  return StringToDouble(cfg.volume)>0 && StringToDouble(cfg.stop_distance)>0 && StringToDouble(cfg.target_distance)>0 && StringToDouble(cfg.max_spread_price)>0;
}
string GenericControlPayload(const GenericControl &control) {
  return "control_protocol_version="+control.control_protocol_version+"\npublication_id="+control.publication_id+"\nconfig_checksum="+control.config_checksum+"\naction="+control.action+"\nreason_code="+control.reason_code+"\nissued_at="+control.issued_at+"\n";
}
int GenericControlState(const GenericPublication &publication,const GenericConfig &cfg) {
  if(!FileIsExist(InpGenericControlFile,FILE_COMMON)) return 0;
  GenericControl control; ZeroMemory(control);
  int handle=FileOpen(InpGenericControlFile,FILE_READ|FILE_TXT|FILE_COMMON|FILE_ANSI); if(handle==INVALID_HANDLE) return -1;
  string seen="|";
  while(!FileIsEnding(handle)) {
    string key="",value=""; if(!ReadLineField(handle,seen,key,value)) continue;
    if(key=="control_protocol_version") control.control_protocol_version=value; else if(key=="publication_id") control.publication_id=value;
    else if(key=="config_checksum") control.config_checksum=value; else if(key=="action") control.action=value;
    else if(key=="reason_code") control.reason_code=value; else if(key=="issued_at") control.issued_at=value;
    else if(key=="control_checksum") control.control_checksum=value; else { FileClose(handle); return -1; }
  }
  FileClose(handle);
  string required[]={"control_protocol_version","publication_id","config_checksum","action","reason_code","issued_at","control_checksum"};
  if(!HasFields(seen,required) || control.control_protocol_version!="GENERIC_MT5_DEMO_CONTROL_V1" || control.action!="BLOCK_NEW_ENTRIES" || Sha256Hex(GenericControlPayload(control))!=control.control_checksum) return -1;
  if(control.publication_id!=publication.publication_id || control.config_checksum!=cfg.checksum) return 0;
  return 1;
}
void WriteGenericAcknowledgement(const GenericPublication &publication,const GenericConfig &cfg) {
  int handle=FileOpen(InpGenericAcknowledgementFile,FILE_READ|FILE_WRITE|FILE_CSV|FILE_COMMON|FILE_ANSI,','); if(handle==INVALID_HANDLE) return;
  if(FileSize(handle)==0) FileWrite(handle,"timestamp","publication_id","environment","account_login","account_server","broker_symbol","strategy_version_id","compiler_protocol_version","adapter_capability_id","config_checksum","publication_checksum","decision");
  FileSeek(handle,0,SEEK_END);
  FileWrite(handle,TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS),publication.publication_id,"DEMO",IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN)),AccountInfoString(ACCOUNT_SERVER),_Symbol,cfg.strategy_version_id,cfg.compiler_protocol_version,cfg.adapter_capability_id,cfg.checksum,publication.publication_checksum,"GENERIC_CONFIG_LOADED");
  FileClose(handle);
}
long NextGenericEventSequence() {
  string key="ARKANA_GENERIC_EVENT_SEQUENCE_"+StringSubstr(active_generic.checksum,0,16);
  long value=GlobalVariableCheck(key)?(long)GlobalVariableGet(key):0;
  value++; GlobalVariableSet(key,(double)value); return value;
}
string GenericEventPayload(const string &fields[]) {
  string delimiter=ShortToString(31),payload="";
  for(int index=0;index<ArraySize(fields);index++) { if(index>0) payload+=delimiter; payload+=fields[index]; }
  return payload;
}
string ReportNumber(const double value,const int digits) { return MathIsValidNumber(value)?DoubleToString(value,digits):"NOT_REPORTED"; }
void EmitGenericEvent(const string event_type,const string event_code,const string decision_context,const string decision_setup,const string decision_trigger,const string position_id,const string order_ticket,const string deal_ticket,const string side,const string requested_price,const string filled_price,const string stop_loss,const string take_profit,const string volume,const string spread_price,const string commission,const string swap,const string realized_pnl,const string slippage_price) {
  if(!has_generic_config) return;
  string fields[]={TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS),active_publication.publication_id,IntegerToString(NextGenericEventSequence()),event_type,event_code,"DEMO",IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN)),AccountInfoString(ACCOUNT_SERVER),_Symbol,active_generic.strategy_version_id,active_generic.compiler_protocol_version,active_generic.adapter_capability_id,active_generic.checksum,active_publication.publication_checksum,decision_context,decision_setup,decision_trigger,position_id,order_ticket,deal_ticket,side,requested_price,filled_price,stop_loss,take_profit,volume,spread_price,commission,swap,realized_pnl,slippage_price,IntegerToString(PositionsTotal()),EmergencyStop()?"true":"false"};
  string checksum=Sha256Hex(GenericEventPayload(fields)); if(checksum=="") return;
  int handle=FileOpen(InpGenericTelemetryFile,FILE_READ|FILE_WRITE|FILE_CSV|FILE_COMMON|FILE_ANSI,','); if(handle==INVALID_HANDLE) return;
  if(FileSize(handle)==0) FileWrite(handle,"event_timestamp","publication_id","event_sequence","event_type","event_code","environment","account_login","account_server","broker_symbol","strategy_version_id","compiler_protocol_version","adapter_capability_id","config_checksum","publication_checksum","decision_context","decision_setup","decision_trigger","position_id","order_ticket","deal_ticket","side","requested_price","filled_price","stop_loss","take_profit","volume","spread_price","commission","swap","realized_pnl","slippage_price","positions","emergency_stop","payload_checksum");
  FileSeek(handle,0,SEEK_END); FileWrite(handle,fields[0],fields[1],fields[2],fields[3],fields[4],fields[5],fields[6],fields[7],fields[8],fields[9],fields[10],fields[11],fields[12],fields[13],fields[14],fields[15],fields[16],fields[17],fields[18],fields[19],fields[20],fields[21],fields[22],fields[23],fields[24],fields[25],fields[26],fields[27],fields[28],fields[29],fields[30],fields[31],fields[32],checksum); FileClose(handle);
}
void EmitGenericSimple(const string event_type,const string event_code) {
  EmitGenericEvent(event_type,event_code,"NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED");
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
void GenericOnNewBar() {
  if(generic_entries_blocked) { EmitGenericSimple("BLOCKER","ENTRY_CONTROL_BLOCKED"); return; }
  if(!IsDemoAccount() || active_generic.enabled!="true") { EmitGenericSimple("BLOCKER","DEMO_OR_CONFIG_GUARD"); return; }
  if(EmergencyStop()) { EmitGenericSimple("EMERGENCY","EMERGENCY_STOP_ACTIVE"); EmitGenericSimple("BLOCKER","EMERGENCY_STOP_BLOCKED_ENTRY"); return; }
  if(HasOurPosition(_Symbol)) { EmitGenericSimple("POSITION","OPEN_POSITION_PRESENT"); EmitGenericSimple("BLOCKER","MAX_OPEN_POSITIONS"); return; }
  MqlTick tick; if(!SymbolInfoTick(_Symbol,tick)) { EmitGenericSimple("BLOCKER","BROKER_TICK_UNAVAILABLE"); return; }
  double spread=tick.ask-tick.bid;
  if(spread>StringToDouble(active_generic.max_spread_price)) { EmitGenericEvent("BLOCKER","SPREAD_GUARD","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED",DoubleToString(spread,8),"NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED"); return; }
  int fast=(int)StringToInteger(active_generic.sma_fast_period),slow=(int)StringToInteger(active_generic.sma_slow_period);
  MqlRates rates[]; ArraySetAsSeries(rates,true); if(CopyRates(_Symbol,PERIOD_M1,0,slow+2,rates)<slow+2) { EmitGenericSimple("BLOCKER","COMPLETED_BARS_UNAVAILABLE"); return; }
  // Judged on the completed signal bar, matching the evaluator exactly.
  if(!SessionAllows(rates[1].time)) { EmitGenericSimple("BLOCKER","SESSION_WINDOW_CLOSED"); return; }
  double fast_sum=0.0,slow_sum=0.0;
  for(int index=1;index<=slow;index++) { slow_sum+=rates[index].close; if(index<=fast) fast_sum+=rates[index].close; }
  bool context=(fast_sum/(double)fast)>(slow_sum/(double)slow);
  // ARK-S24-02: the reversal and trigger polarity follow the declared setup
  // direction, which the config validator has already forced to match trigger.
  bool bullish_setup=active_generic.setup_direction=="BULLISH";
  bool setup=bullish_setup ? (rates[2].close<rates[2].open && rates[1].close>rates[1].open)
                           : (rates[2].close>rates[2].open && rates[1].close<rates[1].open);
  bool trigger=bullish_setup ? rates[1].close>rates[1].open : rates[1].close<rates[1].open;
  bool is_short=active_generic.direction=="SHORT";
  string side_text=is_short?"SHORT":"LONG";
  string context_text=context?"true":"false",setup_text=setup?"true":"false",trigger_text=trigger?"true":"false";
  EmitGenericEvent("DECISION",context&&setup&&trigger?"SIGNAL_TRUE":"NO_TRADE",context_text,setup_text,trigger_text,"NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED",DoubleToString(spread,8),"NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED");
  if(!context || !setup || !trigger) return;
  EmitGenericEvent("SIGNAL",side_text+"_SIGNAL",context_text,setup_text,trigger_text,"NOT_REPORTED","NOT_REPORTED","NOT_REPORTED",side_text,"NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED",active_generic.volume,DoubleToString(spread,8),"NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED");
  // NEXT_BAR_OPEN means the first available tick after the completed M1 signal:
  // the ASK for a buy, the BID for a sell.
  double entry=is_short?tick.bid:tick.ask;
  double stop_distance=StringToDouble(active_generic.stop_distance), target_distance=StringToDouble(active_generic.target_distance);
  double sl=NormalizeDouble(is_short?entry+stop_distance:entry-stop_distance,_Digits);
  double tp=NormalizeDouble(is_short?entry-target_distance:entry+target_distance,_Digits);
  string ask_text=DoubleToString(entry,_Digits),sl_text=DoubleToString(sl,_Digits),tp_text=DoubleToString(tp,_Digits);
  EmitGenericEvent("ORDER_REQUEST",is_short?"SELL_REQUEST":"BUY_REQUEST","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED",side_text,ask_text,"NOT_REPORTED",sl_text,tp_text,active_generic.volume,DoubleToString(spread,8),"NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED");
  bool accepted=is_short ? trade.Sell(StringToDouble(active_generic.volume),_Symbol,entry,sl,tp,"ARKANA generic "+active_generic.strategy_version_id)
                         : trade.Buy(StringToDouble(active_generic.volume),_Symbol,entry,sl,tp,"ARKANA generic "+active_generic.strategy_version_id);
  string order_ticket=trade.ResultOrder()>0?(string)trade.ResultOrder():"NOT_REPORTED";
  string filled=trade.ResultPrice()>0?DoubleToString(trade.ResultPrice(),_Digits):"NOT_REPORTED";
  // Slippage is signed against the position: worse fill is negative either way.
  string slippage=trade.ResultPrice()>0?DoubleToString(is_short?entry-trade.ResultPrice():trade.ResultPrice()-entry,_Digits):"NOT_REPORTED";
  // Rejected orders have no broker ticket, so use retcode as the exact result identity.
  if(order_ticket=="NOT_REPORTED") order_ticket="RETCODE_"+IntegerToString((int)trade.ResultRetcode());
  EmitGenericEvent("ORDER_RESULT",accepted?"ORDER_ACCEPTED":"ORDER_REJECTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED",order_ticket,"NOT_REPORTED",side_text,ask_text,filled,sl_text,tp_text,active_generic.volume,DoubleToString(spread,8),"NOT_REPORTED","NOT_REPORTED","NOT_REPORTED",slippage);
  EmitGenericEvent("COST_AVAILABILITY",slippage=="NOT_REPORTED"?"SLIPPAGE_NOT_REPORTED":"SLIPPAGE_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED",order_ticket,"NOT_REPORTED",side_text,ask_text,filled,"NOT_REPORTED","NOT_REPORTED",active_generic.volume,DoubleToString(spread,8),"NOT_REPORTED","NOT_REPORTED","NOT_REPORTED",slippage);
}
void ReloadConfig() {
  GenericPublication publication; GenericConfig generic_candidate;
  if(ReadGenericPublication(publication) && ReadGenericConfig(publication.config_file,generic_candidate) && generic_candidate.checksum==publication.config_checksum && generic_candidate.strategy_version_id==publication.strategy_version_id && generic_candidate.broker_symbol==publication.broker_symbol && generic_candidate.compiler_protocol_version==publication.compiler_protocol_version && generic_candidate.adapter_capability_id==publication.adapter_capability_id) {
    active_publication=publication; active_generic=generic_candidate; has_generic_config=true; has_config=false;
    generic_entries_blocked=GenericControlState(active_publication,active_generic)!=0;
    WriteGenericAcknowledgement(active_publication,active_generic); Print("ARKANA GENERIC_CONFIG_LOADED ",active_generic.checksum); return;
  }
  if(has_generic_config) { generic_entries_blocked=GenericControlState(active_publication,active_generic)!=0; Print("ARKANA generic reload rejected; using last exact valid checksum ",active_generic.checksum); return; }
  StrategyConfig candidate;
  if(ReadConfig(candidate)) { active=candidate; has_config=true; WriteTelemetry("CONFIG_LOADED",active.checksum); }
  else if(has_config) WriteTelemetry("CONFIG_RELOAD_REJECTED","Using last valid cached configuration");
  else WriteTelemetry("NO_VALID_CONFIG","No trading permitted");
}
int OnInit() {
  PrepareCommonConfigFolder();
  if(!IsDemoAccount()) { Print("ARKANA refuses non-DEMO account"); return INIT_FAILED; }
  trade.SetExpertMagicNumber(InpMagicNumber); trade.SetTypeFillingBySymbol(_Symbol);
  ReloadConfig(); EventSetTimer(MathMax(InpReloadSeconds,5)); if(has_generic_config) EmitGenericSimple("HEARTBEAT","EA_INITIALIZED"); else WriteTelemetry("HEARTBEAT","EA initialized"); return INIT_SUCCEEDED;
}
void OnDeinit(const int reason) { EventKillTimer(); if(has_generic_config) EmitGenericSimple("HEARTBEAT","EA_STOPPED"); else WriteTelemetry("HEARTBEAT_STOP",IntegerToString(reason)); }
void OnTimer() { ReloadConfig(); if(has_generic_config) EmitGenericSimple("HEARTBEAT","CACHED_CONFIG_ACTIVE"); else WriteTelemetry("HEARTBEAT",has_config?"cached config active":"no valid config"); }
void OnTradeTransaction(const MqlTradeTransaction &transaction,const MqlTradeRequest &request,const MqlTradeResult &result) {
  if(transaction.type!=TRADE_TRANSACTION_DEAL_ADD || transaction.deal<=0) return;
  if(has_generic_config && HistoryDealSelect(transaction.deal) && (long)HistoryDealGetInteger(transaction.deal,DEAL_MAGIC)==InpMagicNumber && HistoryDealGetString(transaction.deal,DEAL_SYMBOL)==_Symbol) {
    ENUM_DEAL_ENTRY entry=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(transaction.deal,DEAL_ENTRY);
    if(entry==DEAL_ENTRY_IN || entry==DEAL_ENTRY_OUT || entry==DEAL_ENTRY_OUT_BY) {
      string code=entry==DEAL_ENTRY_IN?"DEAL_ENTRY":"DEAL_EXIT",position_id=(string)HistoryDealGetInteger(transaction.deal,DEAL_POSITION_ID),order_ticket=(string)HistoryDealGetInteger(transaction.deal,DEAL_ORDER),deal_ticket=(string)transaction.deal;
      double commission=HistoryDealGetDouble(transaction.deal,DEAL_COMMISSION),swap=HistoryDealGetDouble(transaction.deal,DEAL_SWAP),profit=HistoryDealGetDouble(transaction.deal,DEAL_PROFIT);
      string commission_text=DoubleToString(commission,2),swap_text=DoubleToString(swap,2),pnl_text=entry==DEAL_ENTRY_IN?"NOT_REPORTED":DoubleToString(profit+commission+swap,2);
      EmitGenericEvent("DEAL",code,"NOT_REPORTED","NOT_REPORTED","NOT_REPORTED",position_id,order_ticket,deal_ticket,active_generic.direction=="SHORT"?"SHORT":"LONG","NOT_REPORTED",DoubleToString(HistoryDealGetDouble(transaction.deal,DEAL_PRICE),_Digits),"NOT_REPORTED","NOT_REPORTED",DoubleToString(HistoryDealGetDouble(transaction.deal,DEAL_VOLUME),2),"NOT_REPORTED",commission_text,swap_text,pnl_text,"NOT_REPORTED");
      EmitGenericEvent("COST_AVAILABILITY","DEAL_COSTS_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED",position_id,order_ticket,deal_ticket,active_generic.direction=="SHORT"?"SHORT":"LONG","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED","NOT_REPORTED",DoubleToString(HistoryDealGetDouble(transaction.deal,DEAL_VOLUME),2),"NOT_REPORTED",commission_text,swap_text,pnl_text,"NOT_REPORTED");
    }
  } else if(has_config) WriteTradeTelemetry(transaction.deal);
}
void OnTick() {
  if(!IsNewM1Bar()) return;
  if(has_generic_config) { GenericOnNewBar(); return; }
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
