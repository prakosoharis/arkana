// Non-trading incremental M1 research-data collector.  It never calls OnTick.
#property strict
#property version "1.000"

input string InpBrokerSymbol="XAUUSD.m";
input int InpPollSeconds=15;

string REQUEST_GLOB="ARKANA\\historical\\requests\\request_*.ini";
string REQUEST_DIR="ARKANA/historical/requests/";
string INCREMENT_DIR="ARKANA/historical/increments/";
bool no_request_logged=false;
bool timer_logged=false;

string ReadValue(const string path,const string key) {
  int handle=FileOpen(path,FILE_READ|FILE_TXT|FILE_COMMON|FILE_ANSI);
  if(handle==INVALID_HANDLE) return "";
  while(!FileIsEnding(handle)) {
    string line=FileReadString(handle); int equals=StringFind(line,"=");
    if(equals>0 && StringSubstr(line,0,equals)==key) { string value=StringSubstr(line,equals+1); FileClose(handle); return value; }
  }
  FileClose(handle); return "";
}

bool Finalize(const string temporary,const string final_path) { FileDelete(final_path,FILE_COMMON); return FileMove(temporary,FILE_COMMON,final_path,FILE_COMMON); }

bool ExportRequest(const string request_path) {
  string schema_version=ReadValue(request_path,"schema_version");
  string request_id=ReadValue(request_path,"request_id");
  string broker_symbol=ReadValue(request_path,"broker_symbol");
  string timeframe=ReadValue(request_path,"timeframe");
  datetime requested_from=StringToTime(ReadValue(request_path,"requested_from_timestamp"));
  if(schema_version!="1") { Print("ARKANA collector rejected request schema_version: ",schema_version," path=",request_path); return false; }
  if(request_id=="") { Print("ARKANA collector rejected request_id: missing path=",request_path); return false; }
  if(broker_symbol!=InpBrokerSymbol) { Print("ARKANA collector rejected broker_symbol: ",broker_symbol," expected=",InpBrokerSymbol," request_id=",request_id); return false; }
  if(timeframe!="M1") { Print("ARKANA collector rejected timeframe: ",timeframe," request_id=",request_id); return false; }
  if(requested_from<=0) { Print("ARKANA collector rejected requested_from_timestamp: invalid request_id=",request_id); return false; }
  Print("ARKANA sync request detected: ",request_id," from=",TimeToString(requested_from,TIME_DATE|TIME_MINUTES));
  if(!SymbolSelect(InpBrokerSymbol,true)) { Print("ARKANA collector unavailable broker symbol: ",InpBrokerSymbol); return false; }
  datetime current_open=iTime(InpBrokerSymbol,PERIOD_M1,0);
  datetime last_completed_end=current_open-1;
  if(current_open<=requested_from) { Print("ARKANA CopyRates returned 0 completed M1 bars: request_id=",request_id); return false; }
  MqlRates rates[]; ArraySetAsSeries(rates,false);
  ResetLastError();
  int copied=CopyRates(InpBrokerSymbol,PERIOD_M1,requested_from,last_completed_end,rates);
  if(copied<0) { Print("ARKANA CopyRates failed: request_id=",request_id," from=",TimeToString(requested_from,TIME_DATE|TIME_MINUTES)," to=",TimeToString(last_completed_end,TIME_DATE|TIME_MINUTES)," error=",GetLastError()); return false; }
  if(copied>0 && rates[0].time<requested_from) { Print("ARKANA collector rejected CopyRates range before requested_from: request_id=",request_id); return false; }
  Print("ARKANA CopyRates returned ",copied," M1 bars: request_id=",request_id);
  string csv_path=INCREMENT_DIR+"increment_"+request_id+".csv";
  string temp_csv=csv_path+".tmp";
  int csv=FileOpen(temp_csv,FILE_WRITE|FILE_CSV|FILE_COMMON|FILE_ANSI,',');
  if(csv==INVALID_HANDLE) { Print("ARKANA collector cannot open export artifact"); return false; }
  FileWrite(csv,"timestamp","open","high","low","close","tick_volume","spread","real_volume");
  int rows=0; datetime first=0,last=0;
  for(int i=0;i<copied;i++) {
    if(rates[i].time>=current_open) continue; // never export a forming M1 candle
    FileWrite(csv,TimeToString(rates[i].time,TIME_DATE|TIME_MINUTES),DoubleToString(rates[i].open,_Digits),DoubleToString(rates[i].high,_Digits),DoubleToString(rates[i].low,_Digits),DoubleToString(rates[i].close,_Digits),rates[i].tick_volume,rates[i].spread,rates[i].real_volume);
    if(rows==0) first=rates[i].time; last=rates[i].time; rows++;
  }
  FileClose(csv);
  if(!Finalize(temp_csv,csv_path)) { Print("ARKANA collector cannot finalize CSV"); return false; }
  string manifest_path=INCREMENT_DIR+"increment_"+request_id+".manifest.ini";
  int manifest=FileOpen(manifest_path+".tmp",FILE_WRITE|FILE_TXT|FILE_COMMON|FILE_ANSI);
  if(manifest==INVALID_HANDLE) { Print("ARKANA collector cannot open manifest"); return false; }
  FileWrite(manifest,"schema_version=1\r\nrequest_id="+request_id+"\r\nsource=MT5\r\nbroker_symbol="+InpBrokerSymbol+"\r\ncanonical_instrument=XAUUSD\r\ntimeframe=M1\r\ntimestamp_semantics=UNVERIFIED_BROKER_TIME\r\nfirst_timestamp="+TimeToString(first,TIME_DATE|TIME_MINUTES)+"\r\nlast_timestamp="+TimeToString(last,TIME_DATE|TIME_MINUTES)+"\r\nrow_count="+IntegerToString(rows)+"\r\nexport_timestamp="+TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS)+"\r\nexporter_version=1.000\r\n");
  FileClose(manifest);
  if(!Finalize(manifest_path+".tmp",manifest_path)) { Print("ARKANA collector cannot finalize manifest"); return false; }
  FileDelete(request_path,FILE_COMMON);
  Print("ARKANA collector exported request ",request_id,": ",rows," completed M1 bars from ",TimeToString(requested_from,TIME_DATE|TIME_MINUTES));
  return true;
}

void PollRequests() {
  string name;
  long handle=FileFindFirst(REQUEST_GLOB,name,FILE_COMMON);
  if(handle==INVALID_HANDLE) {
    if(!no_request_logged) { Print("ARKANA no sync request found at FILE_COMMON/",REQUEST_GLOB); no_request_logged=true; }
    return;
  }
  no_request_logged=false;
  do { ExportRequest(REQUEST_DIR+name); } while(FileFindNext(handle,name));
  FileFindClose(handle);
}

int OnInit() { if(!EventSetTimer(MathMax(5,InpPollSeconds))) { Print("ARKANA_DATA_COLLECTOR timer setup failed: ",GetLastError()); return INIT_FAILED; } Print("ARKANA_DATA_COLLECTOR active: ",InpBrokerSymbol," M1; FILE_COMMON request polling only."); PollRequests(); return INIT_SUCCEEDED; }
void OnDeinit(const int reason) { EventKillTimer(); }
void OnTimer() { if(!timer_logged) { Print("ARKANA_DATA_COLLECTOR timer active"); timer_logged=true; } PollRequests(); }
