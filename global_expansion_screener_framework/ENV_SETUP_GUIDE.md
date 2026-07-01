# Environment Setup Guide for Phase 1 Bhavcopy Strategy

## Quick Setup (5 minutes)

### 1️⃣ FRED API Key (Optional but Recommended)

**Get your free API key:**
```
https://fred.stlouisfed.org/docs/api/
1. Click "Request API Key"
2. Sign up with email
3. Copy your API key from the dashboard
```

**Add to environment:**

**Option A: Local .env file**
```bash
# Create ~/.claude_bhavcopy.env
echo "FRED_API_KEY=your_api_key_here" >> ~/.claude_bhavcopy.env
echo "SCREENER_EMAIL=your_email@example.com" >> ~/.claude_bhavcopy.env
echo "SCREENER_PASSWORD=your_password" >> ~/.claude_bhavcopy.env
```

**Option B: Add to shell profile (permanent)**
```bash
# Add to ~/.zshrc or ~/.bashrc
export FRED_API_KEY="your_api_key_here"
export SCREENER_EMAIL="your_email@example.com"
export SCREENER_PASSWORD="your_password"

# Then reload:
source ~/.zshrc
```

**Option C: Google Colab (recommended)**
```python
# Cell 1: Set environment variables
import os

os.environ['FRED_API_KEY'] = 'your_api_key_here'
os.environ['SCREENER_EMAIL'] = 'your_email@example.com'
os.environ['SCREENER_PASSWORD'] = 'your_password'

# Or from Google Secrets Manager (more secure)
from google.colab import userdata

os.environ['FRED_API_KEY'] = userdata.get('FRED_API_KEY')
os.environ['SCREENER_EMAIL'] = userdata.get('SCREENER_EMAIL')
os.environ['SCREENER_PASSWORD'] = userdata.get('SCREENER_PASSWORD')
```

---

### 2️⃣ Screener.in Login (Optional - Already Have?)

**You mentioned saved screener login in env** — great! Just confirm these are set:
```bash
echo $SCREENER_EMAIL
echo $SCREENER_PASSWORD
```

If not set, sign up at https://www.screener.in (free tier available)

---

### 3️⃣ Check Your Environment

**Verify everything is set:**
```bash
python3 -c "
import os
print('FRED_API_KEY:', 'SET' if os.getenv('FRED_API_KEY') else 'NOT SET')
print('SCREENER_EMAIL:', 'SET' if os.getenv('SCREENER_EMAIL') else 'NOT SET')
print('SCREENER_PASSWORD:', 'SET' if os.getenv('SCREENER_PASSWORD') else 'NOT SET')
"
```

---

## Complete Environment Variables Reference

| Variable | Purpose | Required | Where to Get |
|----------|---------|----------|--------------|
| `FRED_API_KEY` | Macro data from FRED | Optional | https://fred.stlouisfed.org/docs/api/ |
| `SCREENER_EMAIL` | Screener.in login | Optional | https://www.screener.in |
| `SCREENER_PASSWORD` | Screener.in login | Optional | https://www.screener.in |

---

## Phase 1 Data Sources & Costs

| Source | Data | Cost | API Key Needed |
|--------|------|------|----------------|
| **Bhavcopy** | 2,681 Indian stocks, 15 years | FREE | No |
| **yfinance** | 1,200 global stocks | FREE | No |
| **FRED** | Macro data (Fed Funds, GDP, inflation) | FREE | Optional* |
| **Screener.in** | Indian fundamentals | FREE | No (uses login) |
| **SEC EDGAR** | 8-K announcements | FREE | No |

*FRED has a free tier (120 requests/minute without API key, unlimited with key)

---

## Google Colab Setup (Copy-Paste Ready)

```python
# Cell 1: Environment Setup
import os
from google.colab import userdata

# Option A: Type your credentials here
os.environ['FRED_API_KEY'] = 'paste_your_fred_api_key_here'
os.environ['SCREENER_EMAIL'] = 'your_email@screener.in'
os.environ['SCREENER_PASSWORD'] = 'your_password'

# Option B: Use Google Secrets (more secure)
# 1. Go to Colab Secrets (🔑 icon on left)
# 2. Add FRED_API_KEY, SCREENER_EMAIL, SCREENER_PASSWORD
# Then uncomment:
# os.environ['FRED_API_KEY'] = userdata.get('FRED_API_KEY')
# os.environ['SCREENER_EMAIL'] = userdata.get('SCREENER_EMAIL')
# os.environ['SCREENER_PASSWORD'] = userdata.get('SCREENER_PASSWORD')

print("✅ Environment variables set")
```

---

## Verify Credentials Work

```python
# Cell 2: Test connections
import requests
import os

# Test FRED API
print("Testing FRED API...")
fred_key = os.getenv('FRED_API_KEY', '')
if fred_key:
    resp = requests.get(
        'https://api.stlouisfed.org/fred/series/observations',
        params={'series_id': 'DFF', 'api_key': fred_key}
    )
    print(f"  FRED: {resp.status_code} {'✅' if resp.status_code == 200 else '❌'}")
else:
    print("  FRED: Skipped (no API key)")

# Test Screener.in API
print("Testing Screener.in...")
session = requests.Session()
resp = session.post(
    'https://www.screener.in/api/auth/login',
    json={
        'email': os.getenv('SCREENER_EMAIL'),
        'password': os.getenv('SCREENER_PASSWORD')
    }
)
print(f"  Screener: {resp.status_code} {'✅' if resp.status_code == 200 else '❌'}")

# Test SEC EDGAR (always free)
print("Testing SEC EDGAR...")
resp = requests.get('https://data.sec.gov/submissions/CIK0000051143.json')
print(f"  SEC EDGAR: {resp.status_code} {'✅' if resp.status_code == 200 else '❌'}")

# Test Bhavcopy (always free)
print("Testing Bhavcopy...")
resp = requests.get(
    'https://archives.nseindia.com/content/historical/EQUITIES_02JUL2026.zip',
    timeout=5
)
print(f"  Bhavcopy: {resp.status_code} {'✅' if resp.status_code == 200 else '❌'}")
```

---

## Troubleshooting

### "FRED API rate limit"
- **Solution:** Register for free API key at fred.stlouisfed.org

### "Screener.in login failed"
- **Check:** Email and password are correct
- **Note:** Some corporate proxies may block screener.in
- **Fallback:** Skip if blocked; use yfinance for Indian fundamentals instead

### "Bhavcopy not reachable"
- **Cause:** May be NSE maintenance (rare)
- **Fallback:** All data is public; can download manually if script fails
- **Retry:** Automatic retry logic in code

### "Rate limiting on yfinance"
- **Solution:** Already handled with batching (30/batch, 2s delays)
- **Built-in:** Code includes intelligent retry logic

---

## Next Steps

1. **Set environment variables** (5 minutes)
2. **Verify credentials** (run test cell above)
3. **Copy Phase 1 code** from `PHASE_1_BHAVCOPY_STRATEGY.md`
4. **Run in Google Colab** (automatic, 5-7 days)
5. **Download results** and proceed to Phase 2

**All done!** 🚀
