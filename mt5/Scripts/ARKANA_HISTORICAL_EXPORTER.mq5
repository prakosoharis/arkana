// One-shot, non-trading MT5 historical M1 exporter for ARKANA Sprint 09.
#property strict
#property script_show_inputs
#property version "001.000"

input string InpBrokerSymbol="XAUUSD.m";
input string InpExportFile="ARKANA/historical/xauusd_m1_mt5.csv";
input string InpManifestFile="ARKANA/historical/xauusd_m1_mt5.manifest.ini";

string Temp(const string path) { return path+".tmp"; }
bool RenameFinal(const string temporary,const string final_path) { FileDelete(final_path,FILE_COMMON); return FileMove(temporary,FILE_COMMON,final_path,FILE_COMMON); }

void OnStart() {
  if(!SymbolSelect(InpBrokerSymbol,true)) { Print("ARKANA historical export failed: broker symbol unavailable: ",InpBrokerSymbol); return; }
  MqlRates rates[]; ArraySetAsSeries(rates,false);
  // CopyRates with start_pos 0 requests the maximum history currently available to this terminal/broker.
  int copied=CopyRates(InpBrokerSymbol,PERIOD_M1,0,INT_MAX,rates);
  if(copied<2) { Print("ARKANA historical export failed: no practical completed M1 history returned for ",InpBrokerSymbol); return; }
  int completed=copied-1; // index 0..completed-1 excludes the current forming M1 bar.
  int csv=FileOpen(Temp(InpExportFile),FILE_WRITE|FILE_CSV|FILE_COMMON|FILE_ANSI,',');
  if(csv==INVALID_HANDLE) { Print("ARKANA historical export failed: cannot open Common Files artifact"); return; }
  FileWrite(csv,"timestamp","open","high","low","close","tick_volume","spread","real_volume");
  for(int i=0;i<completed;i++) FileWrite(csv,TimeToString(rates[i].time,TIME_DATE|TIME_MINUTES),DoubleToString(rates[i].open,_Digits),DoubleToString(rates[i].high,_Digits),DoubleToString(rates[i].low,_Digits),DoubleToString(rates[i].close,_Digits),rates[i].tick_volume,rates[i].spread,rates[i].real_volume);
  FileClose(csv);
  if(!RenameFinal(Temp(InpExportFile),InpExportFile)) { Print("ARKANA historical export failed: cannot finalize CSV"); return; }
  int manifest=FileOpen(Temp(InpManifestFile),FILE_WRITE|FILE_TXT|FILE_COMMON|FILE_ANSI);
  if(manifest==INVALID_HANDLE) { Print("ARKANA historical export failed: cannot write manifest"); return; }
  FileWrite(manifest,"schema_version=1\r\nsource=MT5\r\nbroker_symbol="+InpBrokerSymbol+"\r\ncanonical_instrument=XAUUSD\r\ntimeframe=M1\r\ntimestamp_semantics=UNVERIFIED_BROKER_TIME\r\nfirst_timestamp="+TimeToString(rates[0].time,TIME_DATE|TIME_MINUTES)+"\r\nlast_timestamp="+TimeToString(rates[completed-1].time,TIME_DATE|TIME_MINUTES)+"\r\nrow_count="+IntegerToString(completed)+"\r\nexport_timestamp="+TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS)+"\r\nexporter_version=001.000\r\n");
  FileClose(manifest);
  if(!RenameFinal(Temp(InpManifestFile),InpManifestFile)) { Print("ARKANA historical export failed: cannot finalize manifest"); return; }
  Print("ARKANA historical export complete: ",completed," completed M1 bars; ",InpExportFile);
}
