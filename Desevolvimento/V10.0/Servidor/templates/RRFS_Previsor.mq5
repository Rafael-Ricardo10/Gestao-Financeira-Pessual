//+------------------------------------------------------------------+
//|                                               RRFS_Previsor.mq5  |
//|  Previsor de direcao do fechamento da vela M1..M5 (NAO opera)    |
//|  Autonomo, sem parametros, universal (qualquer ativo)            |
//+------------------------------------------------------------------+
#property copyright "RRFS"
#property version   "1.00"
#property description "Preve a direcao de fechamento das velas M1-M5 e valida o acerto. Nao faz trade."

//====================================================================
// BLOCO 0 - INICIALIZACAO
//====================================================================
#define NTF           5          // numero de timeframes (M1..M5)
#define NF            12         // numero de features (inclui bias)
#define RING_SIZE     100        // janela do acerto recente
#define MODEL_VER     1
#define LOCK_FRAC     0.50       // previsao e travada com 50% da vela decorrida
#define LOCK_MAX      0.90       // se passar de 90% nao trava (evita previsao tardia)
#define CONF_LEVEL    0.60       // limiar de previsao "confiante"
#define BARS_NEEDED   120
#define PANEL_PREFIX  "RRFS_PNL_"

struct SModel
{
   int    ver;
   double w[NF];
   long   n;
   long   total, hits;
   long   totalC, hitsC;
   int    ring[RING_SIZE];
   int    ringPos, ringCnt;
};

struct SPred
{
   bool     active;
   datetime barTime;
   int      dir;        // +1 alta, -1 baixa
   double   prob;       // prob. de alta
   double   conf;       // confianca (max(p,1-p))
   double   x[NF];
   double   openPrice;
   double   lockPrice;
};

ENUM_TIMEFRAMES g_tf[NTF]     = {PERIOD_M1,PERIOD_M2,PERIOD_M3,PERIOD_M4,PERIOD_M5};
string          g_tfName[NTF] = {"M1","M2","M3","M4","M5"};

SModel   g_model[NTF];
SPred    g_pred[NTF];
int      g_last[NTF];       // ultimo resultado: 1 acerto, -1 erro, 0 nenhum
datetime g_attempt[NTF];    // ultima vela em que ja se tentou travar previsao
string   g_sym;
string   g_folder;
bool     g_useLast = false;
uint     g_lastPanel = 0;

string SanitizeName(string s)
{
   string r = "";
   for(int i = 0; i < StringLen(s); i++)
   {
      ushort c = StringGetCharacter(s, i);
      bool ok = (c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
                c == '_' || c == '-' || c == '.' || c == '#' || c == '+';
      if(ok) r += ShortToString(c);
      else   r += "_";
   }
   return r;
}

void ResetModel(int k)
{
   ZeroMemory(g_model[k]);
   g_model[k].ver = MODEL_VER;
   // pesos iniciais (conhecimento previo): movimento parcial e fluxo pesam mais
   double pw[NF] = {0.0, 1.2, 0.4, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.3, 0.3};
   ArrayCopy(g_model[k].w, pw);
}

void SaveModel(int k)
{
   string f = g_folder + "\\modelo_" + g_tfName[k] + ".bin";
   int h = FileOpen(f, FILE_WRITE | FILE_BIN);
   if(h == INVALID_HANDLE) return;
   FileWriteStruct(h, g_model[k]);
   FileClose(h);
}

void LoadModel(int k)
{
   string f = g_folder + "\\modelo_" + g_tfName[k] + ".bin";
   if(!FileIsExist(f)) return;
   int h = FileOpen(f, FILE_READ | FILE_BIN);
   if(h == INVALID_HANDLE) return;
   SModel m;
   ZeroMemory(m);
   if((int)FileSize(h) == (int)sizeof(SModel))
   {
      uint rd = FileReadStruct(h, m);
      if(rd == sizeof(SModel) && m.ver == MODEL_VER)
         g_model[k] = m;
   }
   FileClose(h);
}

int OnInit()
{
   g_sym    = _Symbol;
   g_folder = "RRFS\\" + SanitizeName(g_sym);
   FolderCreate("RRFS");
   FolderCreate(g_folder);
   SymbolSelect(g_sym, true);
   g_useLast = (SymbolInfoInteger(g_sym, SYMBOL_CHART_MODE) == SYMBOL_CHART_MODE_LAST);

   for(int k = 0; k < NTF; k++)
   {
      ResetModel(k);
      LoadModel(k);
      ZeroMemory(g_pred[k]);
      g_pred[k].active = false;
      g_last[k]    = 0;
      g_attempt[k] = 0;
   }

   PanelCreate();
   EventSetMillisecondTimer(250);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   for(int k = 0; k < NTF; k++) SaveModel(k);
   ObjectsDeleteAll(0, PANEL_PREFIX);
}

void OnTick()  { Engine(); }
void OnTimer() { Engine(); }

//====================================================================
// BLOCO 1 - FUNCOES DE BUSCA DE DADOS NO MT5
//====================================================================
bool GetRates(ENUM_TIMEFRAMES tf, int count, MqlRates &r[])
{
   ArraySetAsSeries(r, true);
   int got = CopyRates(g_sym, tf, 0, count, r);
   return(got >= count);
}

bool GetBar(ENUM_TIMEFRAMES tf, datetime t, MqlRates &bar)
{
   MqlRates a[];
   if(CopyRates(g_sym, tf, t, 1, a) != 1) return false;
   if(a[0].time != t) return false;
   bar = a[0];
   return true;
}

double PriceNow()
{
   MqlTick t;
   if(!SymbolInfoTick(g_sym, t)) return 0.0;
   if(g_useLast && t.last > 0) return t.last;
   if(t.bid > 0) return t.bid;
   return t.last;
}

double TickPrice(const MqlTick &t)
{
   if(g_useLast) return (t.last > 0 ? t.last : 0.0);
   return (t.bid > 0 ? t.bid : t.last);
}

int FetchTicks(datetime from, MqlTick &t[])
{
   ulong a = (ulong)from * 1000;
   ulong b = (ulong)TimeCurrent() * 1000 + 999;
   int n = CopyTicksRange(g_sym, t, COPY_TICKS_ALL, a, b);
   return (n > 0 ? n : 0);
}

//====================================================================
// BLOCO 2 - INDICADORES
//====================================================================
double Ind_ATR(const MqlRates &r[], int period, int start)
{
   double s = 0;
   for(int i = start; i < start + period; i++)
   {
      double tr = MathMax(r[i].high - r[i].low,
                  MathMax(MathAbs(r[i].high - r[i+1].close), MathAbs(r[i].low - r[i+1].close)));
      s += tr;
   }
   return s / period;
}

double Ind_RSI(const MqlRates &r[], int period, int start)
{
   double g = 0, l = 0;
   for(int i = start; i < start + period; i++)
   {
      double d = r[i].close - r[i+1].close;
      if(d > 0) g += d; else l -= d;
   }
   if(g + l <= 0) return 50.0;
   return 100.0 * g / (g + l);
}

double Ind_EMA(const MqlRates &r[], int period, int depth)
{
   double a = 2.0 / (period + 1.0);
   double e = r[depth].close;
   for(int i = depth - 1; i >= 1; i--) e = a * r[i].close + (1.0 - a) * e;
   return e;
}

void Ind_Bands(const MqlRates &r[], int period, double &mean, double &sd)
{
   double s = 0, s2 = 0;
   for(int i = 1; i <= period; i++) s += r[i].close;
   mean = s / period;
   for(int i = 1; i <= period; i++) { double d = r[i].close - mean; s2 += d * d; }
   sd = MathSqrt(s2 / period);
}

// Order flow: delta de agressao (compra - venda) usando flags do tick ou tick rule
void Ind_Flow(const MqlTick &t[], int n, double &flowAll, double &flowRec, double &micro)
{
   flowAll = 0; flowRec = 0; micro = 0;
   if(n < 2) return;
   double b = 0, s = 0, bR = 0, sR = 0, prev = 0, pRec = 0, pLast = 0;
   int recStart = (int)(n * 0.6);
   for(int i = 0; i < n; i++)
   {
      double p = TickPrice(t[i]);
      if(p <= 0) continue;
      double v = (t[i].volume_real > 0) ? t[i].volume_real : ((t[i].volume > 0) ? (double)t[i].volume : 1.0);
      bool fb = ((t[i].flags & TICK_FLAG_BUY) != 0);
      bool fs = ((t[i].flags & TICK_FLAG_SELL) != 0);
      int d = 0;
      if(fb && !fs) d = 1;
      else if(fs && !fb) d = -1;
      else if(prev > 0)
      {
         if(p > prev) d = 1;
         else if(p < prev) d = -1;
      }
      if(d > 0)      { b += v; if(i >= recStart) bR += v; }
      else if(d < 0) { s += v; if(i >= recStart) sR += v; }
      prev = p;
      if(i >= recStart && pRec == 0) pRec = p;
      pLast = p;
   }
   if(b + s > 0)   flowAll = (b - s) / (b + s);
   if(bR + sR > 0) flowRec = (bR - sR) / (bR + sR);
   if(pRec > 0 && pLast > 0) micro = pLast - pRec;
}

//====================================================================
// BLOCO 3 - SISTEMA DE PREVISAO (regressao logistica online)
//   Fluxo honesto: 1) trava previsao  2) vela fecha  3) valida  4) so entao aprende
//====================================================================
double Clip(double v, double lim)
{
   if(v >  lim) return  lim;
   if(v < -lim) return -lim;
   return v;
}

double Sigmoid(double z)
{
   z = Clip(z, 30.0);
   return 1.0 / (1.0 + MathExp(-z));
}

double ModelProb(int k, const double &x[])
{
   double z = 0;
   for(int j = 0; j < NF; j++) z += g_model[k].w[j] * x[j];
   return Sigmoid(z);
}

bool BuildFeatures(int k, double &x[], double &price, double &openP, datetime &bt)
{
   MqlRates r[];
   if(!GetRates(g_tf[k], BARS_NEEDED, r)) return false;
   price = PriceNow();
   if(price <= 0) return false;

   double atr = Ind_ATR(r, 14, 1);
   atr = MathMax(atr, _Point);

   bt    = r[0].time;
   openP = r[0].open;

   MqlTick tk[];
   int n = FetchTicks(r[0].time, tk);
   double fAll, fRec, micro;
   Ind_Flow(tk, n, fAll, fRec, micro);

   double mean, sd;
   Ind_Bands(r, 20, mean, sd);
   double ema8  = Ind_EMA(r, 8, 80);
   double ema21 = Ind_EMA(r, 21, 80);
   double rsi   = Ind_RSI(r, 14, 1);

   double hi = MathMax(r[0].high, price);
   double lo = MathMin(r[0].low,  price);
   double rng = hi - lo;
   double rr1 = r[1].high - r[1].low;

   x[0]  = 1.0;
   x[1]  = Clip((price - r[0].open) / atr, 3.0);
   x[2]  = fAll;
   x[3]  = fRec;
   x[4]  = Clip((r[1].close - r[1].open) / atr, 3.0);
   x[5]  = Clip((rsi - 50.0) / 25.0, 3.0);
   x[6]  = Clip((ema8 - ema21) / atr, 3.0);
   x[7]  = (sd > 0) ? Clip((price - mean) / sd / 2.0, 3.0) : 0.0;
   x[8]  = (rr1 > 0) ? ((r[1].close - r[1].low) / rr1 - 0.5) * 2.0 : 0.0;
   x[9]  = Clip((r[1].close - r[4].close) / atr / 2.0, 3.0);
   x[10] = Clip(micro / atr * 2.0, 3.0);
   x[11] = (rng > 0) ? ((price - lo) / rng * 2.0 - 1.0) : 0.0;
   return true;
}

bool LockPrediction(int k, datetime barOpen)
{
   double x[NF];
   double price, openP;
   datetime bt;
   if(!BuildFeatures(k, x, price, openP, bt)) return false;
   if(bt != barOpen) return false;

   double p = ModelProb(k, x);
   g_pred[k].active    = true;
   g_pred[k].barTime   = bt;
   g_pred[k].dir       = (p >= 0.5) ? 1 : -1;
   g_pred[k].prob      = p;
   g_pred[k].conf      = MathMax(p, 1.0 - p);
   g_pred[k].openPrice = openP;
   g_pred[k].lockPrice = price;
   ArrayCopy(g_pred[k].x, x);
   return true;
}

void Learn(int k, const double &x[], int y)
{
   double p   = ModelProb(k, x);
   double lr  = MathMax(0.01, 0.15 / (1.0 + (double)g_model[k].n / 100.0));
   double err = (double)y - p;
   for(int j = 0; j < NF; j++)
   {
      double reg = (j == 0) ? 0.0 : 0.0005 * g_model[k].w[j];
      g_model[k].w[j] += lr * err * x[j] - lr * reg;
   }
   g_model[k].n++;
}

void LogPrediction(int k, datetime bt, int dir, double conf, double o, double c, bool hit)
{
   string f = g_folder + "\\previsoes_" + g_tfName[k] + ".csv";
   int h = FileOpen(f, FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_SHARE_READ | FILE_SHARE_WRITE, ';');
   if(h == INVALID_HANDLE) return;
   if(FileSize(h) == 0) FileWrite(h, "vela", "previsao", "confianca", "abertura", "fechamento", "resultado");
   FileSeek(h, 0, SEEK_END);
   FileWrite(h, TimeToString(bt, TIME_DATE | TIME_SECONDS), (dir > 0 ? "ALTA" : "BAIXA"),
             DoubleToString(conf, 4), DoubleToString(o, _Digits), DoubleToString(c, _Digits),
             (hit ? "ACERTO" : "ERRO"));
   FileClose(h);
}

void EvaluatePrediction(int k, datetime curBar)
{
   MqlRates b;
   if(!GetBar(g_tf[k], g_pred[k].barTime, b))
   {
      if((long)(curBar - g_pred[k].barTime) > 3 * PeriodSeconds(g_tf[k]))
         g_pred[k].active = false;
      return;
   }

   int y = -1;
   if(b.close > b.open)      y = 1;
   else if(b.close < b.open) y = 0;

   double x[NF];
   ArrayCopy(x, g_pred[k].x);
   int    dir  = g_pred[k].dir;
   double conf = g_pred[k].conf;
   g_pred[k].active = false;

   if(y < 0) { g_last[k] = 0; return; }   // vela neutra (doji exato): ignorada

   bool hit = ((dir > 0 && y == 1) || (dir < 0 && y == 0));

   g_model[k].total++;
   if(hit) g_model[k].hits++;
   if(conf >= CONF_LEVEL)
   {
      g_model[k].totalC++;
      if(hit) g_model[k].hitsC++;
   }
   g_model[k].ring[g_model[k].ringPos] = hit ? 1 : 0;
   g_model[k].ringPos = (g_model[k].ringPos + 1) % RING_SIZE;
   if(g_model[k].ringCnt < RING_SIZE) g_model[k].ringCnt++;
   g_last[k] = hit ? 1 : -1;

   Learn(k, x, y);          // aprende somente depois de validar
   SaveModel(k);
   LogPrediction(k, b.time, dir, conf, b.open, b.close, hit);
}

void Engine()
{
   datetime now = TimeCurrent();
   for(int k = 0; k < NTF; k++)
   {
      datetime bo = iTime(g_sym, g_tf[k], 0);
      if(bo == 0) continue;

      if(g_pred[k].active && bo > g_pred[k].barTime)
         EvaluatePrediction(k, bo);

      if(!g_pred[k].active && g_attempt[k] != bo)
      {
         double el = (double)(now - bo) / (double)PeriodSeconds(g_tf[k]);
         if(el >= LOCK_FRAC)
         {
            if(el > LOCK_MAX) g_attempt[k] = bo;
            else if(LockPrediction(k, bo)) g_attempt[k] = bo;
         }
      }
   }
   PanelUpdate();
}

//====================================================================
// BLOCO 4
//====================================================================

//====================================================================
// BLOCO 5
//====================================================================

//====================================================================
// BLOCO 6
//====================================================================

//====================================================================
// BLOCO 7
//====================================================================

//====================================================================
// BLOCO 8
//====================================================================

//====================================================================
// BLOCO 9
//====================================================================

//====================================================================
// BLOCO 10 - PAINEL DE STATUS
//====================================================================
#define PX_TF      18
#define PX_PREV    52
#define PX_PROB    125
#define PX_TIME    180
#define PX_TOTAL   270
#define PX_HIT     335
#define PX_REC     395
#define PX_CONF    460
#define PX_LAST    545
#define PY_TITLE   26
#define PY_SUB     44
#define PY_HEAD    70
#define PY_ROWS    94
#define PY_SUM     212
#define PY_F1      238
#define PY_F2      254
#define PY_F3      270

void PLabel(string name, int x, int y, string text, color clr, int size = 9)
{
   string n = PANEL_PREFIX + name;
   if(ObjectFind(0, n) < 0)
   {
      ObjectCreate(0, n, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, n, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, n, OBJPROP_ANCHOR, ANCHOR_LEFT_UPPER);
      ObjectSetInteger(0, n, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, n, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, n, OBJPROP_FONTSIZE, size);
      ObjectSetString(0, n, OBJPROP_FONT, "Consolas");
   }
   ObjectSetInteger(0, n, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, n, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, n, OBJPROP_COLOR, clr);
   ObjectSetString(0, n, OBJPROP_TEXT, text);
}

string Pct(long h, long t)
{
   if(t <= 0) return "--";
   return DoubleToString(100.0 * (double)h / (double)t, 1) + "%";
}

color RateColor(long h, long t)
{
   if(t < 30) return clrSilver;
   double r = 100.0 * (double)h / (double)t;
   if(r >= 55.0) return clrLime;
   if(r >= 50.0) return clrGold;
   return clrTomato;
}

string MMSS(long s)
{
   if(s < 0) s = 0;
   return StringFormat("%02d:%02d", (int)(s / 60), (int)(s % 60));
}

void PanelCreate()
{
   string bg = PANEL_PREFIX + "BG";
   if(ObjectFind(0, bg) < 0) ObjectCreate(0, bg, OBJ_RECTANGLE_LABEL, 0, 0, 0);
   ObjectSetInteger(0, bg, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, bg, OBJPROP_XDISTANCE, 8);
   ObjectSetInteger(0, bg, OBJPROP_YDISTANCE, 18);
   ObjectSetInteger(0, bg, OBJPROP_XSIZE, 615);
   ObjectSetInteger(0, bg, OBJPROP_YSIZE, 275);
   ObjectSetInteger(0, bg, OBJPROP_BGCOLOR, C'18,22,30');
   ObjectSetInteger(0, bg, OBJPROP_BORDER_TYPE, BORDER_FLAT);
   ObjectSetInteger(0, bg, OBJPROP_COLOR, C'70,80,100');
   ObjectSetInteger(0, bg, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, bg, OBJPROP_HIDDEN, true);

   PLabel("TITLE", 18, PY_TITLE, "RRFS PREVISOR  |  direcao do fechamento da vela", clrWhite, 10);
   PLabel("SUB",   18, PY_SUB,   "Ativo: " + g_sym + "   (somente previsao, sem operacoes)", clrSilver);
   color hc = C'120,170,255';
   PLabel("H1", PX_TF,    PY_HEAD, "TF",        hc);
   PLabel("H2", PX_PREV,  PY_HEAD, "Previsao",  hc);
   PLabel("H3", PX_PROB,  PY_HEAD, "Prob",      hc);
   PLabel("H4", PX_TIME,  PY_HEAD, "Tempo",     hc);
   PLabel("H5", PX_TOTAL, PY_HEAD, "Amostras",  hc);
   PLabel("H6", PX_HIT,   PY_HEAD, "Acerto",    hc);
   PLabel("H7", PX_REC,   PY_HEAD, "Ult.100",   hc);
   PLabel("H8", PX_CONF,  PY_HEAD, "Confiante", hc);
   PLabel("H9", PX_LAST,  PY_HEAD, "Ultimo",    hc);
   g_lastPanel = 0;
   PanelUpdate();
}

void PanelUpdate()
{
   uint t = GetTickCount();
   if(t - g_lastPanel < 500) return;
   g_lastPanel = t;

   datetime now = TimeCurrent();
   long gt = 0, gh = 0, gn = 0;

   for(int k = 0; k < NTF; k++)
   {
      int y = PY_ROWS + k * 22;
      datetime bo = iTime(g_sym, g_tf[k], 0);
      int per = PeriodSeconds(g_tf[k]);
      long rem = (long)bo + per - (long)now;

      string sPrev = "aguard.";
      color  cPrev = clrSilver;
      string sProb = "--";
      string sTime = "--";

      if(g_pred[k].active)
      {
         sPrev = (g_pred[k].dir > 0) ? "ALTA" : "BAIXA";
         cPrev = (g_pred[k].dir > 0) ? clrLime : clrTomato;
         sProb = DoubleToString(g_pred[k].conf * 100.0, 1) + "%";
         sTime = "fecha " + MMSS(rem);
      }
      else if(bo > 0)
      {
         long toLock = (long)bo + (long)(LOCK_FRAC * per) - (long)now;
         if(toLock > 0) sTime = "trava " + MMSS(toLock);
      }

      long tot = g_model[k].total, hit = g_model[k].hits;
      long rc = 0;
      for(int i = 0; i < g_model[k].ringCnt; i++) rc += g_model[k].ring[i];
      long rn = g_model[k].ringCnt;

      string sConf = Pct(g_model[k].hitsC, g_model[k].totalC);
      if(g_model[k].totalC > 0) sConf += " (" + IntegerToString((int)g_model[k].totalC) + ")";

      string sLast = "--";
      color  cLast = clrSilver;
      if(g_last[k] > 0)      { sLast = "ACERTO"; cLast = clrLime; }
      else if(g_last[k] < 0) { sLast = "ERRO";   cLast = clrTomato; }

      string id = IntegerToString(k);
      PLabel("R" + id + "a", PX_TF,    y, g_tfName[k], clrWhite);
      PLabel("R" + id + "b", PX_PREV,  y, sPrev, cPrev);
      PLabel("R" + id + "c", PX_PROB,  y, sProb, clrWhite);
      PLabel("R" + id + "d", PX_TIME,  y, sTime, clrSilver);
      PLabel("R" + id + "e", PX_TOTAL, y, IntegerToString((int)tot), clrWhite);
      PLabel("R" + id + "f", PX_HIT,   y, Pct(hit, tot), RateColor(hit, tot));
      PLabel("R" + id + "g", PX_REC,   y, Pct(rc, rn), RateColor(rc, rn));
      PLabel("R" + id + "h", PX_CONF,  y, sConf, RateColor(g_model[k].hitsC, g_model[k].totalC));
      PLabel("R" + id + "i", PX_LAST,  y, sLast, cLast);

      gt += tot; gh += hit; gn += g_model[k].n;
   }

   PLabel("SUMa", PX_TF,  PY_SUM, "GERAL", clrWhite);
   PLabel("SUMb", PX_TOTAL, PY_SUM, IntegerToString((int)gt), clrWhite);
   PLabel("SUMc", PX_HIT,   PY_SUM, Pct(gh, gt), RateColor(gh, gt));

   PLabel("F1", 18, PY_F1, "Pasta: MQL5/Files/" + g_folder, clrSilver);
   PLabel("F2", 18, PY_F2, "Previsao travada com " + IntegerToString((int)(LOCK_FRAC * 100)) + "% da vela | doji exato e ignorado", clrSilver);
   PLabel("F3", 18, PY_F3, "Validacao: previsao x fechamento real, depois aprende | Preco: " + (g_useLast ? "Last" : "Bid"), clrSilver);

   ChartRedraw(0);
}
//+------------------------------------------------------------------+
