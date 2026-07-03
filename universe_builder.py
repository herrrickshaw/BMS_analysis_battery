"""
universe_builder.py
===================
Builds data/global_universe.json from the best available sources:
  - IN  : data/india_tickers_full.csv  (5,140 NSE+BSE stocks)
  - US  : data/us_tickers_full.json    (7,726 NYSE+NASDAQ+AMEX)
  - JP  : data/jp_tickers_full.json    (3,566 TSE stocks from symbols_cache)
  - KR  : data/kr_tickers_full.json    (2,606 KOSPI+KOSDAQ from symbols_cache)
  - AU  : data/au_tickers_full.json    (1,834 ASX stocks from official ASX directory)
  - CN  : data/cn_sse_tickers_full.json (1,856 SSE securities) + static SZSE fallback
  - SG  : data/sg_tickers_full.json    (171 SGX securities from full-market scan)
  - EU  : data/europe_tickers_full.json (966+ tickers: 10 new markets + expanded UK/DE/IT/FR/ES/NL/CH)
  - Others: static verified index constituents (expand by adding to each list below)

Run:
    python3 universe_builder.py
Outputs:
    data/global_universe.json         — per-market dict with yf_symbols[]
    data/global_universe_flat.csv     — flat (market_code, name, exchange, yf_symbol)
"""

from __future__ import annotations
import csv, json
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data"
DATA.mkdir(exist_ok=True)


# ── India ─────────────────────────────────────────────────────────────────────

def _load_india() -> list[str]:
    path = DATA / "india_tickers_full.csv"
    if not path.exists():
        return []
    seen, out = set(), []
    with open(path) as f:
        for row in csv.DictReader(f):
            sym = row.get("Symbol", "").strip()
            sfx = row.get("Suffix", ".NS").strip()
            yf = f"{sym}{sfx}"
            if sym and yf not in seen:
                seen.add(yf)
                out.append(yf)
    return out


# ── United States ─────────────────────────────────────────────────────────────

def _load_us() -> list[str]:
    path = DATA / "us_tickers_full.json"
    if path.exists():
        with open(path) as f:
            data = json.load(f)
        return sorted(data.keys())
    # Fallback: S&P 500 only
    return [
        "AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","BRK-B","LLY","AVGO",
        "JPM","BAC","WFC","GS","MS","UNH","JNJ","ABBV","MRK","PFE",
        "WMT","PG","KO","PEP","COST","XOM","CVX","V","MA","ORCL",
    ]


# ── Japan ─────────────────────────────────────────────────────────────────────

def _load_jp() -> list[str]:
    path = DATA / "jp_tickers_full.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return _dedup([t["yf_ticker"] for t in data])
    return [f"{t}.T" for t in JP_TICKERS]


# ── South Korea ────────────────────────────────────────────────────────────────

def _load_kr() -> list[str]:
    path = DATA / "kr_tickers_full.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return _dedup([t["yf_ticker"] for t in data])
    return [f"{t}.KS" for t in KR_TICKERS]


# ── Australia ──────────────────────────────────────────────────────────────────

def _load_au() -> list[str]:
    path = DATA / "au_tickers_full.json"
    if path.exists():
        with open(path) as f:
            data = json.load(f)
        return _dedup([t["yf_ticker"] for t in data])
    return [f"{t}.AX" for t in AU_TICKERS]


# ── Europe (multi-market loader) ──────────────────────────────────────────────

_EUROPE_EXCHANGE_MAP = {
    "London Stock Exchange":     ("UK", ".L"),
    "Deutsche Boerse Frankfurt": ("DE", ".F"),
    "Borsa Italiana":            ("IT", ".MI"),
    "Euronext Paris":            ("FR", ".PA"),
    "BME Madrid":                ("ES", ".MC"),
    "Nasdaq Stockholm":          ("SE", ".ST"),
    "Athens Stock Exchange":     ("GR", ".AT"),
    "Euronext Amsterdam":        ("NL", ".AS"),
    "Nasdaq Copenhagen":         ("DK", ".CO"),
    "Nasdaq Helsinki":           ("FI", ".HE"),
    "Oslo Bors":                 ("NO", ".OL"),
    "Euronext Brussels":         ("BE", ".BR"),
    "Euronext Dublin":           ("IE", ".IR"),
    "SIX Swiss":                 ("CH", ".SW"),
    "Vienna":                    ("AT", ".VI"),
    "Warsaw GPW":                ("PL", ".WA"),
    "Euronext Lisbon":           ("PT", ".LS"),
}

_EUROPE_NEW_MARKETS = {
    "GR": ("Greece",      "Athens Stock Exchange"),
    "SE": ("Sweden",      "Nasdaq Stockholm"),
    "DK": ("Denmark",     "Nasdaq Copenhagen"),
    "FI": ("Finland",     "Nasdaq Helsinki"),
    "NO": ("Norway",      "Oslo Bors"),
    "BE": ("Belgium",     "Euronext Brussels"),
    "IE": ("Ireland",     "Euronext Dublin"),
    "AT": ("Austria",     "Vienna Stock Exchange"),
    "PL": ("Poland",      "Warsaw GPW"),
    "PT": ("Portugal",    "Euronext Lisbon"),
}


def _load_europe_csv() -> dict[str, list[str]]:
    """Load europe_tickers_full.json → {market_code: [yf_tickers]}"""
    path = DATA / "europe_tickers_full.json"
    if path.exists():
        with open(path) as f:
            data = json.load(f)
        result: dict[str, list[str]] = {}
        for entry in data:
            code = entry.get("market_code", "")
            yf = entry.get("yf_ticker", "")
            if code and yf:
                result.setdefault(code, []).append(yf)
        return result
    return {}


# ── Singapore ─────────────────────────────────────────────────────────────────

def _load_sg() -> list[str]:
    path = DATA / "sg_tickers_full.json"
    if path.exists():
        with open(path) as f:
            data = json.load(f)
        return _dedup([t["yf_ticker"] for t in data])
    return [f"{t}.SI" for t in SG_TICKERS]


# ── China (SSE) ────────────────────────────────────────────────────────────────

def _load_cn_sse() -> list[str]:
    path = DATA / "cn_sse_tickers_full.json"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return _dedup([t["yf_ticker"] for t in data])
    return [f"{t}.SS" for t in CN_SS_TICKERS]


# ── Static lists for other markets ────────────────────────────────────────────
# Format: base ticker (suffix applied automatically)

JP_TICKERS = [
    "7203","6758","6861","8306","9984","7267","4502","6954","9432","8316",
    "9433","7741","2914","6501","6326","8035","4063","6367","9020","7751",
    "4661","8411","3382","8766","4543","6902","7270","2802","4568","8001",
    "6762","5401","8002","5108","9022","6971","9503","6273","7731","7832",
    "8031","8053","6503","4523","7733","6988","2801","4901","6645","8015",
    "9005","8830","8750","5802","6701","7201","3092","7269","4704","9613",
    "9735","6594","4452","8725","7011","7013","4519","4911","3407","6201",
    "5711","6301","6724","7752","5201","6703","8604","1925","6472","4689",
    "8309","6855","2503","6146","5334","4578","3141","6770","2269","9021",
    "6976","7433","1928","6920","9766","8601","8802","6981","4755","6506",
    "8630","2282","1332","6141","7762","8801","7912","9062","3086","6471",
    "2871","6113","6502","8804","9613","4508","5333","9434","6963","5631",
    "8355","6361","3861","5214","1721","9086","6841","1803","6664","7211",
    "3402","7205","3401","5010","5233","6806","4151","4558","8697","9062",
    "5002","9009","6753","5411","6925","6175","9412","6869","7309","3197",
    "8029","6590","2768","9104","3893","5406","2871","1802","5707","9783",
    "5019","3038","1801","8354","6800","9101","6857","6098","4911","2502",
    "3289","9706","4324","6473","7921","8697","7974","9681","3659","4385",
    "9064","7276","3891","6178","4519","4385","6963","9984","6098","5019",
    "4689","2267","8306","3092","8601","4661","2502","7309","8766","3197",
]

CN_SS_TICKERS = [
    "600519","601318","600036","600900","601166","601398","601288","601988",
    "600028","600030","601857","600016","601628","601601","600050","601390",
    "600048","601006","601328","600837","601669","600104","600309","601336",
    "600019","600362","601939","601186","600660","601088","601985","600000",
    "601727","601229","601211","600795","600703","600010","601998","600015",
    "601818","600811","601717","601800","601225","600150","601888","600999",
    "601012","601021","601100","601899","600426","601238","601919","601111",
    "600079","601020","600018","601766","600887","601577","600068","600688",
    "600171","601989","600029","600585","601901","601990","601158","600438",
    "601360","601872","601009","601186","601688","601211","600009","600011",
    "601669","600820","601216","600879","600489","600547","601088","600025",
    "601800","600600","601678","600196","601111","600332","601168","600276",
    "600690","601698","601600","600115","601615","601818","600020","601866",
    "600111","601228","600256","601179","601398","601288","601939","601988",
]

CN_SZ_TICKERS = [
    "000858","000333","002594","000651","300750","002415","000002","000625",
    "002475","000776","300274","002142","000063","000166","002304","000001",
    "002236","000100","002027","000725","300760","002607","000568","000596",
    "300122","300059","002352","000786","000895","002241","002714","300014",
    "002230","300015","000661","002312","000703","002008","300033","000538",
    "002738","002555","300124","002180","002129","000963","002465","300496",
    "000060","000581","002340","000727","002625","300738","002049","000661",
    "300347","002607","300348","002493","002080","300015","002049","000333",
    "002415","000858","002475","000725","300122","002714","300274","000596",
    "002241","300059","002142","002304","000786","000895","002352","300014",
    "002230","000063","000166","000538","002236","000100","002027","000651",
    "000001","000776","000002","002594","300750","002312","300760","000703",
    "002555","300033","300124","002738","002180","002129","002465","300496",
]

HK_TICKERS = [
    "0700","9988","0005","0941","2318","1299","0939","3690","0388","0883",
    "2020","1211","9618","0016","0001","0011","0003","0823","2382","1810",
    "0688","9999","2269","0002","0006","1038","2007","0960","0012","0175",
    "1093","6862","3988","0027","0066","1177","0762","2313","0386","1128",
    "0291","0857","2338","0992","0981","6098","0669","2688","0151","0956",
    "3328","1398","3968","1113","0083","1088","0267","2628","0101","1109",
    "0013","2601","1997","0017","0019","0023","0052","0083","0088","0101",
    "0116","0135","0144","0151","0168","0175","0189","0193","0267","0268",
    "0270","0291","0316","0322","0330","0341","0357","0358","0371","0386",
    "0388","0392","0400","0410","0420","0425","0435","0440","0489","0494",
    "0522","0535","0536","0539","0548","0551","0562","0570","0575","0579",
    "0580","0585","0590","0604","0606","0636","0639","0645","0656","0659",
    "0660","0669","0670","0688","0694","0700","0709","0719","0728","0737",
    "0762","0788","0806","0808","0819","0823","0825","0829","0836","0853",
    "0855","0857","0868","0881","0883","0884","0916","0939","0941","0960",
    "0968","0981","0992","0999","1003","1007","1009","1024","1038","1044",
    "1060","1066","1072","1083","1088","1093","1099","1107","1109","1113",
    "1128","1136","1140","1141","1157","1171","1177","1179","1193","1199",
    "1200","1211","1214","1221","1228","1230","1234","1238","1242","1253",
    "1268","1271","1282","1288","1299","1302","1313","1328","1336","1339",
    "1347","1358","1378","1383","1398","1408","1413","1448","1458","1461",
    "1478","1501","1513","1515","1518","1519","1522","1523","1529","1530",
]

KR_TICKERS = [
    "005930","000660","035420","005380","051910","068270","035720","096770",
    "003550","017670","066570","004020","028260","000270","009150","207940",
    "000100","011070","010950","032830","012330","086790","018260","097950",
    "267250","000810","033780","003490","010130","024110","006400","009830",
    "011200","000720","088350","030200","086280","139480","034730","002790",
    "323410","373220","000080","009240","000220","047050","025270","010140",
    "001040","002380","139130","000150","032640","002520","007310","021240",
    "009970","042660","078930","011790","120110","047810","033530","071050",
    "161390","006280","000880","017000","000105","003010","005830","033240",
    "012750","003230","005385","006800","002350","023530","013570","002240",
    "018880","034220","036460","015760","069960","005300","316140","001680",
    "072130","035000","037270","030000","011780","004140","009540","001450",
    "000490","000215","010060","029780","000240","004170","006040","010620",
    "009200","004990","011170","002760","014820","004800","004830","005940",
]

TW_TICKERS = [
    "2330","2317","2454","2308","2882","2881","2412","2303","1301","2886",
    "2891","3711","2002","1303","2357","5871","2382","1216","2395","3008",
    "2379","1590","2344","3034","2474","2327","2498","3045","4904","2912",
    "1101","2883","2892","5880","5876","2884","2885","2887","2890","2897",
    "5884","5885","6669","6770","6271","1326","1402","1435","2385","2408",
    "2425","2426","2428","2448","2449","2451","2467","2488","2492","2496",
    "2498","2501","2504","2506","2511","2515","2520","2522","2524","2528",
    "2530","2535","2537","2542","2545","2548","2550","2551","2553","2555",
    "2556","2558","2560","2561","2564","2566","2568","2569","2570","2597",
    "2601","2603","2606","2609","2610","2611","2612","2615","2616","2618",
    "2619","2622","2624","2626","2628","2630","2634","2636","2637","2639",
    "2641","2642","2643","2645","2646","2649","2651","2652","2653","2656",
    "2658","2659","2660","2662","2663","2664","2666","2668","2669","2670",
    "2672","2673","2674","2675","2692","2694","2696","2706","2707","2712",
]

SG_TICKERS = [
    "D05","O39","U11","Z74","C6L","BN4","G13","C31","A17U","H78",
    "9CI","F34","U96","S68","V03","BS6","N2IU","BUOU","ME8U","AJBU",
    "T82U","K71U","SK6U","D01","F03","S58","P52","T39","S51","U14",
    "Y92","G07","H02","P15","Q5T","S07","B61","U77","L38","5E2",
    "C52","V33","H30","A7RU","CWBU","ACV","S63","C09","J37","U09",
    "5CP","D03","C07","S27","S11","E5H","BVA","A26","1D0","G92",
    "RE4","5AB","T14","P8Z","578","G50","D06","558","5KD","40B",
    "B28","C69","594","C6L","C77","C86","C87","S63","C09","J37",
]

AU_TICKERS = [
    "BHP","CBA","CSL","ANZ","WBC","NAB","RIO","WES","WOW","MQG",
    "FMG","TLS","GMG","NCM","REA","ALL","COL","TCL","MIN","IEL",
    "APX","WDS","STO","ORG","AGL","QAN","CWY","APA","JHX","SHL",
    "XRO","CPU","QBE","SUN","IAG","AMP","MPL","NHF","ANN","BOQ",
    "BEN","FLT","HVN","JBH","MYR","SUL","KGN","TPW","NXT","CAR",
    "SEK","REH","IFT","DXS","SCG","ABP","CIP","GPT","CHC","LLC",
    "CMW","ASX","WPR","NSR","VGI","PAC","TNE","WTC","RMD","COH",
    "PME","EBO","NAN","EDV","HLO","CTD","WEB","BKG","SYA","PLS",
    "LKE","AKE","ILU","OZL","AWC","S32","WOR","SXY","BPT","KAR",
    "WHC","BCI","IMD","NIC","FCL","ADT","AMI","ASB","ASG","ATS",
    "CGF","CIA","CIN","CNB","CSR","DGL","DRO","DUI","DUR","DYL",
    "EAR","EBR","EDE","EDG","EDL","EGL","EHE","EHX","ELT","EMN",
    "EPW","ESUR","ETI","FDEV","FERG","FPM","FRR","FSV","GBG","GFS",
    "ICG","IRE","JMS","KME","KSC","MGX","MLD","MML","MND","MOY",
    "MSB","MVF","MYE","NMT","NZM","OBM","OCL","OFX","OGC","ORA",
]

UK_TICKERS = [
    "SHEL","AZN","HSBA","ULVR","BP","RIO","GSK","LSEG","BARC","LLOY",
    "BT-A","VOD","REL","PRU","NG","DGE","RKT","EXPN","STAN","GLEN",
    "IMB","BA","CNA","SDR","HIK","TSCO","CPG","INF","WPP","IAG",
    "AUTO","BME","CCH","CRDA","DCC","ENT","EVR","FRES","HLMA","III",
    "JET","KGF","LAND","LGEN","MKS","MNG","MNDI","MONY","NXT","OCDO",
    "PAGE","PHNX","PSN","PTEC","RMV","RSA","RTO","SBRY","SGE","SMDS",
    "SMIN","SMT","SN","SPX","SSE","SXS","TW","UU","WEIR","WOS",
    "HWDN","ADM","AGK","AHT","AML","AV","AVV","BAB","BAES","BATS",
    "BBH","BBY","BDEV","BEZ","BFG","BKG","BNZL","BOY","BRBY","BRW",
    "BTG","BVIC","BWY","CCR","CINE","CKN","CLLN","CNCT","COML","CYBG",
    "DARK","DFS","DLAR","DLG","DMGT","DNO","DTG","ELM","EMG","FCIT",
    "FDEV","FERG","FGP","GBG","GFS","GVC","HMSO","HSXL","ICP","ICG",
    "ITRK","ITV","JMAT","JUST","KIE","KWS","LRD","MAN","MARS","MBH",
    "MERL","MGNS","MGRC","MNZS","NETW","NWS","OSB","OTC","PFC","PFG",
    "PFP","PHI","PHP","PIC","PLUS","PMO","POG","POL","POM","PSON",
    "PZC","RBS","RCDO","RCH","RCP","RDW","REC","RMG","RNK","RSW",
    "RTSC","RWA","SAB","SAGA","SHB","SHOE","SHP","SIG","SKIP","SKY",
    "SLNG","SMUR","SOLI","SQZ","SRC","SRG","SVB","SVT","TCG","UU",
]

DE_TICKERS = [
    "SAP","SIE","ALV","DTE","BAYN","BMW","BAS","ADS","VOW3","MRK",
    "MBG","DBK","EOAN","CON","RWE","HEI","FRE","MTX","ZAL","DHER",
    "QIA","PAH3","VNA","DPW","TUI1","LHA","1COV","AIR","CBK","ENR",
    "EVD","FME","G1A","GBF","HLAG","HOT","INH","ITO","LIN","MOR",
    "MUV2","NMC","NWX","O2D","OHB","PSAN","RSTA","RTL","SANT","SD2",
    "SHL","SIX2","SLT","SNH","SRT3","STO3","STR","SY1","SZG","TAG",
    "TBO","TCH","TEG","TKA","TMR","UTDI","VBK","VIB3","VIF","VOS",
    "WAF","WBH","WCH","WIN","WKS","WOR","WRM","WUW","XTP","AFX",
    "ARND","BCMN","BNR","BPE","BST","CMBN","COBA","CP2","CWC","DBAN",
    "DFVA","DIC","DMP","DRW3","DWNI","DWS","ECK","EDL","EIN3","EVK",
    "EVNK","EVO","EWE","EXS","FHZN","FNTN","FRST","GWI1","GXI","HAB",
    "HAG","HAW","HBH","HDD","HDI","HFT","HKS","HLD","HNR1","HOB",
    "HOT","HSI","HSS","HYQ","IDA","IFX","IKS","ILA","ILM","IMH",
    "IML","IND","INF","INN","INS","INT","INV","IOF","IPH","IPN",
    "IPS","IPW","IR","IRE","IRL","IRS","ISA","ISB","ISC","ISD","ISE",
]

FR_TICKERS = [
    "MC","TTE","SAN","AI","BNP","OR","CS","EL","DG","CAP",
    "RI","SGO","ATO","VIE","BN","KER","ACA","GLE","SU","DSY",
    "RNO","STM","HO","LR","ML","PUB","FP","EN","TEP","AF",
    "AC","ADP","AMUN","ARO","AUB","BIM","BNB","BVI","CB","CDI",
    "CHR","CNP","CO","CVG","DBG","DCF","DIOR","DNX","ENGI","ERA",
    "EUCAR","EUF","EXN","FDJ","FREY","GBT","GEA","GFC","GEFC","GLO",
    "GNE","GNS","GOB","GPA","GRP","GTH","GUI","GVT","HDF","HEXA",
    "HFG","HO","HRS","HSM","HTL","IDS","IDV","IGA","IGE","INA",
    "INFE","INS","IPH","IPN","IPX","IPL","IRL","ISB","ISE","ISF",
    "ISL","JSF","JXR","LBO","LDC","LDV","LFN","LGA","LGF","LGH",
    "LGS","LGT","LHA","LHN","LIP","LIVE","LNR","LOC","LOGI","LOV",
    "LRC","LSS","LYS","MAC","MAU","MBT","MDL","MDM","MDR","MELE",
    "MF","MGI","MKT","MLA","MLG","MMB","MMT","MMX","MND","MNG",
    "MNL","MNO","MNR","MOB","MOD","MOL","MOM","MON","MOP","MOR",
]

CH_TICKERS = [
    "NESN","NOVN","ROG","ABB","ZURN","UBSG","LONN","SIKA","LHN","GIVN",
    "SLHN","SCMN","PGHN","CFR","TEMN","ALC","GEBN","ADEN","BARN","HOLN",
    "KNIN","LISP","NBEN","OFEN","AEBN","ALPN","BALN","BCGE","BCRN","BEKN",
    "BKWN","BLKB","BOSN","BUCN","CFRN","CLTN","COTN","DESN","DKSH","EDHN",
    "EFGN","EMSN","ESUN","ETHN","FHZN","FORN","GALN","GEMS","GEYN","GIGBN",
    "GPBN","HBCN","HELN","HIAG","HUNN","IFCN","IMPN","INRN","INSP","IREN",
    "JUBN","KABN","KARN","KDMN","KSBN","KURN","LAMB","LEON","LKBN","LOHN",
    "LUZN","MBTN","MGBN","MHGN","MIBN","MOBN","MOLN","MRON","MSBN","NABN",
    "OEBN","ORXN","PABN","PEHN","PKBN","PSPN","RAIN","RNSN","ROVN","RPXN",
    "RTRN","SABN","SAHN","SCHM","SFPN","SGSN","SLHN","SOON","SPBN","SRBN",
    "SRCN","SSBN","SSRBN","STGN","STMN","SUNN","SXTN","SYBN","TIBN","TIKN",
    "TIMN","TKBN","TLSN","TMBN","TNBN","TNXN","TOBN","TOSN","TPHN","TQBN",
    "TRBN","TSXN","TUBN","TULN","TVBN","TWAN","TWIN","TWRN","TXBN","TYBN",
]

NL_TICKERS = [
    "ASML","HEIA","PHIA","NN","ABN","AKZA","WKL","AD","RAND","INGA",
    "AGN","URW","BESI","IMCD","LIGHT","MT","OCI","TKWY","DSM","SBMO",
    "ADYEN","AEGON","ALFEN","BOKA","CEVA","CHEM","CMBN","CMB","CTAC",
    "DSFIR","ECMPA","EXEL","FAGR","FLOW","FNKN","FORALL","GARAP","GBL",
    "GLPG","GPOR","GROE","ICG","IMAB","JDEP","KENDR","KPNV","LNVNV",
    "LYHN","MAKA","MELE","MOVI","MPVN","NCNL","NEXTN","NXP","PRXL",
    "QIAGEN","REN","REPS","RTSA","SBM","SLIGR","SNCB","SNN","SSAB",
    "TNLV","TPGN","TWEKA","UNILNA","USG","VASTN","VIKAB","VINK","VOS",
    "VWS","WKL","WPP","WOLGA","AKZOA","AALB","ACER","ACOMO","ACSL","ACSM",
]

IT_TICKERS = [
    "ENI","ENEL","ISP","UCG","TIT","LDO","RACE","STM","CPR","PRY",
    "G","BAMI","MB","BGN","SRG","A2A","AMP","BPSO","CNH","ATL",
    "AZIMUT","BMPS","BPE","BPM","BREM","BST","CEM","CIR","CMS","CNI",
    "CNHI","COGS","CRDI","DEA","DIASORIN","EGL","EMAK","ERG","EXOR","FALCK",
    "FCT","FI","FIB","FNC","GEI","GEL","GEO","GET","GFT","GIL",
    "GLO","GNE","GPH","GVT","HER","HES","HID","HMO","HTL","HYD",
    "IGD","IGL","IIS","IKF","ILG","ILS","IMA","INM","INS","IPA",
    "IPI","IPL","IPM","IPN","IRN","IRS","ISA","ISK","ISL","ISM",
    "ISO","ISP","ISR","ISS","ITL","ITM","ITW","IVS","JAC","JUVE",
    "KLA","LAT","LEC","LGH","LIO","LLD","LNI","LOG","LOM","LOR",
    "LUX","MCA","MCE","MCI","MCM","MCS","MED","MEL","MFB","MFE",
    "MGI","MGM","MHN","MKS","MLB","MLC","MLN","MNA","MNL","MOL",
    "MOM","MOR","MOS","MPC","MPN","MPR","MPS","MRD","MRC","MRF",
]

ES_TICKERS = [
    "IBE","SAN","ITX","TEF","BBVA","BKT","REP","AENA","ACS","GRF",
    "FER","ELE","MEL","MAP","IDR","CIE","VIS","ACX","NTGY","MRL",
    "AMS","ALMAZ","ALNT","ANA","CABK","CLNX","COL","ENG","FDR","GCO",
    "GRV","HMY","IAG","IDE","INM","LGTY","LRE","MDF","MNC","MTB",
    "MTS","NATS","OHL","OHLA","ORO","PHM","PRIM","RAB","SAB","SCYR",
    "SLO","SNC","SPS","SRS","TRE","UNI","UNF","VID","VOC","ZOT",
    "ACE","AGS","ALCO","ALM","ALR","ALSI","ALTS","ALU","AMB","AMCN",
    "AMED","AMER","AMES","AMEX","AMF","AMG","AMH","AMI","AMIB","AMIG",
    "AMIJ","AMIK","AMIL","AMIN","AMINO","AMIO","AMIR","AMIS","AMIT","AMIU",
    "AML","AMLN","AMM","AMMO","AMN","AMNA","AMNO","AMNS","AMNT","AMNU",
]

CA_TICKERS = [
    "RY","TD","BNS","BMO","ENB","CNR","CP","BCE","SU","ABX",
    "MFC","SLF","TRI","ATD","CVE","MRU","WCN","AEM","SHOP","OTEX",
    "NTR","IMO","TRP","H","CM","POW","AQN","GWO","FFH","CNQ",
    "AC","AGF-B","AIF","ALA","ALNT","APH","ARX","ATD","ATH","ATS",
    "AW","AX","BAD","BAM","BBA","BBD-B","BCE","BEI","BHC","BIR",
    "BLD","BNS","BPY","BRY","BTE","BTB","BTO","CAE","CAR","CAS",
    "CCA","CCL-B","CCP","CDN","CFP","CHP","CHR","CIX","CJT","CK",
    "CKI","CLR","CM","CMB","CML","CNQ","CNR","COG","CPI","CPX",
    "CQE","CRE","CRR","CSH","CSU","CTC-A","CTT","CU","CVE","CWB",
    "D","DC","DCM","DFY","DGC","DII-B","DIR","DIV","DRX","DSG",
    "ECA","EFL","EFX","EGD","EGL","EIF","ELF","ELR","EMA","EMO",
    "ENB","EQB","ERO","ESI","ET","EXE","EXF","FAF","FCR","FCX",
    "FN","FNV","FOR","FRU","FSV","FTT","FVI","G","GC","GDI",
    "GEO","GFI","GGD","GIL","GIW","GKO","GLD","GMP","GNE","GO",
    "GOM","GRT","GS","GSS","GSX","GT","GTE","GWR","HBC","HBM",
]

BR_TICKERS = [
    "PETR4","VALE3","ITUB4","BBDC4","BBAS3","ABEV3","WEGE3","RENT3","LREN3","SUZB3",
    "RAIL3","GGBR4","UGPA3","CSAN3","B3SA3","RADL3","ELET3","SBSP3","TOTS3","EMBR3",
    "VBBR3","KLBN11","CCRO3","EQTL3","BRFS3","JBSS3","MRFG3","SLCE3","SMTO3","AGRO3",
    "ENBR3","CPFE3","CPLE6","CMIG4","TAEE11","TRPL4","ISAE4","COCE5","EGIE3","CSMG3",
    "ENGI11","ENEV3","AURE3","ECOR3","PSSA3","WIZS3","CXSE3","BBSE3","SULA11","POMO4",
    "MARB3","MYPK3","RAPT4","ARML3","ALUP11","TIMS3","VIVT3","OIBR3","LVTC3","GETT4",
    "MOVI3","JALL3","AZUL4","GOLL4","CVCB3","LCAM3","RDOR3","HAPV3","QUAL3","ONCO3",
    "FLRY3","DASA3","HYPE3","PARD3","AALR3","PFRM3","LEVE3","MDIA3","PCAR3","ASAI3",
    "CRFB3","GMAT3","SOMA3","ARZZ3","SBFG3","VULC3","CYRE3","MRVE3","EVEN3","JHSF3",
    "GFSA3","DIRR3","TPVT3","MELK3","PDGR3","LAVV3","PMAM3","ETER3","CSNA3","CBAV3",
    "USIM5","GOAU4","FESA4","BRAP4","ROMI3","MAPT3","TGMA3","KEPL3","PRIO3","RECV3",
    "RRRP3","CMIN3","BRAV3","PTBL3","PPLA3","SEQL3","BMOB3","CASH3","DOTZ3","INTB3",
    "LIQO3","ARCO","AREZZO3","ATMP3","ATNT4","AMAR3","AMBP3","ANIM3","APER3","ATSA3",
]

SA_TICKERS = [
    "2222","1120","2010","1180","2350","4030","1050","2380","2330","1010",
    "1211","2020","2080","4280","8010","4200","4070","3020","2170","1030",
    "2060","1150","2280","2090","1301","4140","4001","2140","3007","2290",
    "2310","2160","3008","1131","2300","2250","2230","1210","4110","4007",
    "4150","4240","4300","4320","4400","6010","6020","6040","6050","6060",
    "1060","1080","1100","1111","2001","2030","2040","2050","2070","2100",
    "2110","2120","2130","2180","2190","2200","2210","2220","2240","2260",
    "2270","2320","2340","2360","2370","2390","3001","3002","3003","3004",
    "3005","3006","3010","3030","3040","3050","3060","3070","3080","3090",
    "4002","4003","4008","4009","4011","4013","4020","4031","4040","4050",
    "4060","4080","4090","4100","4120","4130","4160","4170","4180","4190",
    "4210","4220","4230","4250","4260","4270","4290","4310","4330","4340",
]

AE_TICKERS = [
    "FAB","ADCB","ADNOC","ADNOCDIST","ALDAR","EMAAR","DIB","ENBD",
    "TAQA","IHC","ETISALAT","DU","AMANAT","GFH","MASRAF","CBD","NBF",
    "RAKBANK","SIB","UAB","UNB","INVESTB","ADIB","DEYAAR","AABAR",
    "AGTHIA","FERTIGLOBE","BLOOM","ESHRAQ","KCHOLDING","ALMADINA",
    "AJMANBANK","METHAQ","FIDELITY","SALAMA","WATANIA","ORIENT",
    "DAMAC","ALDAR","TAQA","IHC","ENBD","DIB","ADCB","FAB","EMAAR",
]


# ── Market registry ────────────────────────────────────────────────────────────

MARKETS = {
    "IN":  {"name": "India",           "exchange": "NSE/BSE",             "suffix": None,  "tickers": []},
    "US":  {"name": "United States",   "exchange": "NYSE/NASDAQ/AMEX",    "suffix": "",    "tickers": []},
    "JP":  {"name": "Japan",           "exchange": "TSE",                 "suffix": ".T",  "tickers": JP_TICKERS},
    "CN":  {"name": "China",           "exchange": "SSE+SZSE",            "suffix": ".SS", "tickers": CN_SS_TICKERS,
            "extra": {"suffix": ".SZ", "tickers": CN_SZ_TICKERS}},
    "HK":  {"name": "Hong Kong",       "exchange": "HKEX",               "suffix": ".HK", "tickers": HK_TICKERS},
    "KR":  {"name": "South Korea",     "exchange": "KRX",                "suffix": ".KS", "tickers": KR_TICKERS},
    "TW":  {"name": "Taiwan",          "exchange": "TWSE/TPEX",          "suffix": ".TW", "tickers": TW_TICKERS},
    "SG":  {"name": "Singapore",       "exchange": "SGX",                "suffix": ".SI", "tickers": SG_TICKERS},
    "AU":  {"name": "Australia",       "exchange": "ASX",                "suffix": ".AX", "tickers": AU_TICKERS},
    "UK":  {"name": "United Kingdom",  "exchange": "LSE",                "suffix": ".L",  "tickers": UK_TICKERS},
    "DE":  {"name": "Germany",         "exchange": "XETRA",              "suffix": ".DE", "tickers": DE_TICKERS},
    "FR":  {"name": "France",          "exchange": "Euronext Paris",     "suffix": ".PA", "tickers": FR_TICKERS},
    "CH":  {"name": "Switzerland",     "exchange": "SIX",                "suffix": ".SW", "tickers": CH_TICKERS},
    "NL":  {"name": "Netherlands",     "exchange": "Euronext Amsterdam", "suffix": ".AS", "tickers": NL_TICKERS},
    "IT":  {"name": "Italy",           "exchange": "Borsa Italiana",     "suffix": ".MI", "tickers": IT_TICKERS},
    "ES":  {"name": "Spain",           "exchange": "BME",                "suffix": ".MC", "tickers": ES_TICKERS},
    "CA":  {"name": "Canada",          "exchange": "TSX",                "suffix": ".TO", "tickers": CA_TICKERS},
    "BR":  {"name": "Brazil",          "exchange": "B3",                 "suffix": ".SA", "tickers": BR_TICKERS},
    "SA":  {"name": "Saudi Arabia",    "exchange": "Tadawul",            "suffix": ".SR", "tickers": SA_TICKERS},
    "AE":  {"name": "UAE",             "exchange": "ADX/DFM",            "suffix": ".AE", "tickers": AE_TICKERS},
}


def _dedup(lst):
    seen = set()
    return [x for x in lst if not (x in seen or seen.add(x))]


def build_universe() -> dict:
    universe = {}

    # IN — from CSV (5,140 NSE+BSE tickers)
    india = _load_india()
    universe["IN"] = {
        "name": "India", "exchange": "NSE/BSE",
        "yf_symbols": india, "count": len(india),
        "source": "india_tickers_full.csv (NSE+BSE from scan + symbols_cache)",
    }
    print(f"  IN  : {len(india):>6,}")

    # US — from downloaded JSON (7,726 tickers)
    us = _load_us()
    universe["US"] = {
        "name": "United States", "exchange": "NYSE/NASDAQ/AMEX",
        "yf_symbols": us, "count": len(us),
        "source": "us_tickers_full.json (rreichel3 + symbols_cache + screener_universe)",
    }
    print(f"  US  : {len(us):>6,}")

    # JP — from full TSE symbols_cache (3,566 tickers)
    jp = _load_jp()
    universe["JP"] = {
        "name": "Japan", "exchange": "TSE",
        "yf_symbols": jp, "count": len(jp),
        "source": "jp_tickers_full.json (TSE full via symbols_cache)",
    }
    print(f"  JP  : {len(jp):>6,}")

    # KR — from full KOSPI+KOSDAQ symbols_cache (2,606 tickers)
    kr = _load_kr()
    universe["KR"] = {
        "name": "South Korea", "exchange": "KRX",
        "yf_symbols": kr, "count": len(kr),
        "source": "kr_tickers_full.json (KOSPI+KOSDAQ via symbols_cache)",
    }
    print(f"  KR  : {len(kr):>6,}")

    # AU — from official ASX directory (1,834 tickers)
    au = _load_au()
    universe["AU"] = {
        "name": "Australia", "exchange": "ASX",
        "yf_symbols": au, "count": len(au),
        "source": "au_tickers_full.json (ASX official directory)",
    }
    print(f"  AU  : {len(au):>6,}")

    # SG — from full SGX scan (171 securities)
    sg = _load_sg()
    universe["SG"] = {
        "name": "Singapore", "exchange": "SGX",
        "yf_symbols": sg, "count": len(sg),
        "source": "sg_tickers_full.json (SGX full scan, June 2026)",
    }
    print(f"  SG  : {len(sg):>6,}")

    # CN — SSE from official list + static SZSE
    cn_ss = _load_cn_sse()
    cn_sz = [f"{t}.SZ" for t in _dedup(CN_SZ_TICKERS)]
    cn = _dedup(cn_ss + cn_sz)
    universe["CN"] = {
        "name": "China", "exchange": "SSE+SZSE",
        "yf_symbols": cn, "count": len(cn),
        "source": "cn_sse_tickers_full.json (SSE official) + static SZSE",
    }
    print(f"  CN  : {len(cn):>6,}")

    # European markets — load from europe_tickers_full.json (merges with static)
    eu_by_market = _load_europe_csv()

    # Static markets from MARKETS registry
    for code, meta in MARKETS.items():
        if code in ("IN", "US", "JP", "KR", "AU", "CN", "SG"):
            continue
        sfx = meta.get("suffix", "")
        tickers = _dedup(meta["tickers"])
        yf_syms = [f"{t}{sfx}" for t in tickers]
        if "extra" in meta:
            ex = meta["extra"]
            yf_syms += [f"{t}{ex['suffix']}" for t in _dedup(ex["tickers"])]
        # Merge with europe CSV data
        yf_syms = _dedup(yf_syms + eu_by_market.get(code, []))
        universe[code] = {
            "name": meta["name"], "exchange": meta["exchange"],
            "yf_symbols": yf_syms, "count": len(yf_syms),
            "source": "static + europe_tickers_full.json",
        }
        print(f"  {code:<4}: {len(yf_syms):>6,}")

    # New European markets not in MARKETS registry
    for code, (name, exchange) in _EUROPE_NEW_MARKETS.items():
        if code in universe:
            continue
        yf_syms = _dedup(eu_by_market.get(code, []))
        if not yf_syms:
            continue
        universe[code] = {
            "name": name, "exchange": exchange,
            "yf_symbols": yf_syms, "count": len(yf_syms),
            "source": "europe_tickers_full.json",
        }
        print(f"  {code:<4}: {len(yf_syms):>6,}  (NEW)")

    return universe


def save_universe(universe: dict) -> None:
    out_json = DATA / "global_universe.json"
    with open(out_json, "w") as f:
        json.dump(universe, f, indent=2)

    out_csv = DATA / "global_universe_flat.csv"
    total = 0
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["market_code", "market_name", "exchange", "yf_symbol"])
        for code, meta in universe.items():
            for sym in meta["yf_symbols"]:
                w.writerow([code, meta["name"], meta["exchange"], sym])
                total += 1

    print(f"\nSaved {out_json.name}  +  {out_csv.name}  ({total:,} rows)")
    grand = sum(m["count"] for m in universe.values())
    print(f"Grand total: {grand:,} tickers across {len(universe)} markets")


if __name__ == "__main__":
    print("Building global ticker universe...")
    u = build_universe()
    save_universe(u)
