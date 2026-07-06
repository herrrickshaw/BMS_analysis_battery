# 📋 Setup & Requirements Guide
**Complete installation and verification instructions**

---

## Overview

This document covers:
1. **Requirements** — All Python dependencies
2. **Local Setup** — Installing on your machine
3. **Google Colab** — Quick verification in the cloud
4. **Docker** — Container setup (optional)
5. **Troubleshooting** — Common issues and solutions

---

## Part 1: Requirements Overview

### Core Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `numpy` | ≥1.21.0 | Numerical computing |
| `pandas` | ≥1.3.0 | Data manipulation |
| `yfinance` | ≥0.1.70 | Market data (OHLCV + fundamentals) |
| `nsepython` | ≥0.3.4 | NSE India data |
| `requests` | ≥2.26.0 | HTTP requests |
| `beautifulsoup4` | ≥4.9.3 | Web scraping |
| `jinja2` | ≥3.0.0 | HTML templates |
| `matplotlib` | ≥3.4.0 | Plotting |
| `plotly` | ≥5.0.0 | Interactive charts |

**Total size:** ~500MB on disk

**Installation time:** 2-5 minutes on good connection

---

## Part 2: Local Setup

### Option A: macOS / Linux

#### 1. Create Virtual Environment

```bash
# Navigate to project directory
cd /Users/umashankar

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# You should see (venv) in your prompt
```

#### 2. Upgrade pip

```bash
pip install --upgrade pip setuptools wheel
```

#### 3. Install Requirements

```bash
# Install all dependencies
pip install -r requirements.txt

# Verify installation (should take 30-60 seconds)
pip list | grep -E "numpy|pandas|yfinance|jinja2"
```

#### 4. Test Installation

```bash
# Test Python imports
python3 << 'EOF'
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime

print("✅ All imports successful!")
print(f"NumPy: {np.__version__}")
print(f"Pandas: {pd.__version__}")

# Quick test: fetch Apple stock
apple = yf.Ticker("AAPL")
hist = apple.history(period="1d")
print(f"✅ yfinance working! Latest AAPL close: ${hist['Close'][-1]:.2f}")
EOF
```

**Expected output:**
```
✅ All imports successful!
NumPy: 1.21.5
Pandas: 1.3.5
✅ yfinance working! Latest AAPL close: $150.23
```

#### 5. Verify System Scripts

```bash
# Make morning routine executable
chmod +x /Users/umashankar/morning_ocaml_routine.sh

# Test it
/Users/umashankar/morning_ocaml_routine.sh

# Should show output and create files
ls -la /Users/umashankar/DAILY_SCREENING_REPORT.html
```

---

### Option B: Windows

#### 1. Create Virtual Environment

```bash
# Navigate to project directory
cd C:\Users\YourUsername\path\to\project

# Create virtual environment
python -m venv venv

# Activate it (choose based on shell)
venv\Scripts\activate.bat          # Command Prompt
venv\Scripts\Activate.ps1          # PowerShell
```

#### 2. Upgrade pip

```bash
python -m pip install --upgrade pip
```

#### 3. Install Requirements

```bash
pip install -r requirements.txt
```

#### 4. Test Installation

```bash
python << 'EOF'
import numpy as np
import pandas as pd
import yfinance as yf

print("✅ All imports successful!")
EOF
```

---

### Option C: Docker (Optional)

Create `Dockerfile`:

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Set up for morning routine
RUN chmod +x morning_ocaml_routine.sh

# Default command
CMD ["python", "-c", "print('✅ Container ready')"]
```

Build and run:

```bash
# Build image
docker build -t stock-screener .

# Run container
docker run -it stock-screener

# Or run morning routine in container
docker run -v $(pwd):/app stock-screener ./morning_ocaml_routine.sh
```

---

## Part 3: Google Colab Verification

### Quick Verification (5 minutes)

1. **Open Colab notebook:**
   - Go to [colab.research.google.com](https://colab.research.google.com)
   - Click "New notebook"
   - Or upload `COLAB_QUICK_CHECK.ipynb`

2. **Run verification:**
   - Click "Runtime" → "Run all"
   - Wait for all cells to execute
   - Should complete in 5-10 minutes

3. **Check results:**
   - Look for "✅ VERIFICATION COMPLETE"
   - Should show India and USA screens working
   - Sample stocks scored and ranked

### What the Notebook Tests

```
✅ Dependency installation
✅ Python imports
✅ Screen class definitions
✅ India screen logic
✅ USA screen logic
✅ Sample stock scoring
✅ Report generation
✅ Output formatting
```

### Copy Files to Colab

If you want to run your production code in Colab:

```python
# Upload to Colab
from google.colab import files
uploaded = files.upload()  # Upload your Python files

# Or mount Google Drive
from google.colab import drive
drive.mount('/content/drive')

# Then import your modules
import sys
sys.path.insert(0, '/content/drive/My Drive/your_project')
from daily_mailer_universal_integrated import IndiaOptimizedScreen
```

---

## Part 4: Installation Verification Checklist

### ✅ Minimum Requirements Met

```bash
# Check Python version (should be 3.9+)
python3 --version
# Output: Python 3.10.0

# Check pip is installed
pip --version
# Output: pip 21.2.4

# Check virtual environment (if using)
which python
# Output: /Users/username/.venv/bin/python

# Check installed packages
pip list | wc -l
# Should show 30+ packages installed
```

### ✅ Core Packages Installed

```bash
# Verify each critical package
python3 -c "import numpy; print(f'✅ NumPy {numpy.__version__}')"
python3 -c "import pandas; print(f'✅ Pandas {pandas.__version__}')"
python3 -c "import yfinance; print(f'✅ yfinance {yfinance.__version__}')"
python3 -c "import jinja2; print(f'✅ Jinja2 {jinja2.__version__}')"
```

### ✅ Market Data Access

```bash
# Test fetching real data
python3 << 'EOF'
import yfinance as yf
import nsepython as nse

# Test yfinance
apple = yf.Ticker("AAPL")
print(f"✅ yfinance: AAPL close = ${apple.info['currentPrice']:.2f}")

# Test NSE (might require VPN in some regions)
try:
    nse_data = nse.nse_eq(symbol="RELIANCE")
    print(f"✅ NSE: RELIANCE price = ₹{nse_data['price']}")
except:
    print("⚠️ NSE access may require VPN (expected in some regions)")
EOF
```

---

## Part 5: Requirements File Details

### What's Included

The `requirements.txt` file includes:

**Tier 1: Essential (MUST HAVE)**
- numpy, pandas, scipy — numerical computing
- yfinance — market data
- requests — HTTP
- jinja2 — HTML generation

**Tier 2: Important (STRONGLY RECOMMENDED)**
- nsepython — NSE India data
- beautifulsoup4 — web scraping
- matplotlib, plotly — visualization
- APScheduler — task scheduling

**Tier 3: Optional (NICE TO HAVE)**
- cassandra-driver — database (only if using Cassandra)
- selenium — browser automation
- pytest — testing
- jupyter — notebooks

### Installing Only Essentials

If you want minimal installation (much faster):

```bash
pip install numpy pandas scipy yfinance requests jinja2
```

This gives you 80% functionality in 50% time.

### Installing for Production

```bash
# Full production installation
pip install -r requirements.txt

# Add cassandra for database support
pip install cassandra-driver

# Add selenium for SEBI scraping
pip install selenium
```

---

## Part 6: Troubleshooting

### Issue: `ModuleNotFoundError: No module named 'yfinance'`

**Solution:**
```bash
# Make sure virtual environment is activated
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate     # Windows

# Then install
pip install yfinance
```

### Issue: `pip: command not found`

**Solution:**
```bash
# Use python -m pip instead
python3 -m pip install -r requirements.txt
```

### Issue: `nsepython` gives errors on macOS

**Solution:**
```bash
# nsepython has issues on macOS, use yfinance instead for India data
# The system gracefully falls back to yfinance automatically
```

### Issue: Slow installation

**Solution:**
```bash
# Install in parallel
pip install --use-deprecated=legacy-resolver -r requirements.txt

# Or skip optional packages
pip install numpy pandas scipy yfinance requests jinja2
```

### Issue: `Permission denied` when running script

**Solution:**
```bash
# Make script executable
chmod +x /Users/umashankar/morning_ocaml_routine.sh

# Then run it
./morning_ocaml_routine.sh
```

### Issue: Colab notebook won't run

**Solution:**
```python
# Run this in first cell
!pip install -q numpy pandas yfinance requests beautifulsoup4 jinja2

# Then run the rest
```

---

## Part 7: System Requirements

### Minimum

- **OS:** macOS 10.13+, Linux (any), Windows 10+
- **Python:** 3.9+
- **RAM:** 2GB
- **Disk:** 1GB
- **Network:** Internet connection for data

### Recommended

- **OS:** macOS 11+ or Linux (Ubuntu 20.04+)
- **Python:** 3.10 or 3.11
- **RAM:** 4GB+
- **Disk:** 2GB
- **Network:** High-speed internet (>1 Mbps)

### Not Supported

- Python < 3.9
- Windows 7 or older
- Raspberry Pi (insufficient memory)
- WSL1 (use WSL2 instead)

---

## Part 8: Quick Start Summary

### 30-Second Setup

```bash
# 1. Activate virtual environment
source venv/bin/activate

# 2. Install requirements
pip install -r requirements.txt

# 3. Make script executable
chmod +x morning_ocaml_routine.sh

# 4. Test
./morning_ocaml_routine.sh

# ✅ Done! Script will run daily at 08:00 AM
```

### 5-Minute Verification

1. Open `COLAB_QUICK_CHECK.ipynb` in Google Colab
2. Click "Runtime" → "Run all"
3. Wait for execution
4. Check output for "✅ VERIFICATION COMPLETE"
5. System is ready!

---

## Part 9: Environment Variables (Optional)

Create `.env` file for credentials:

```bash
# .env file
BROKER_API_KEY=your_key_here
BROKER_SECRET=your_secret_here
EMAIL_FROM=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
```

Then in Python:

```python
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("BROKER_API_KEY")
```

---

## Part 10: Verification Checklist

- [ ] Python 3.9+ installed
- [ ] Virtual environment created
- [ ] `pip install -r requirements.txt` completed
- [ ] All imports test successfully
- [ ] yfinance can fetch data
- [ ] Script is executable
- [ ] Google Colab notebook runs
- [ ] Morning routine generates output files
- [ ] Crontab entry added for automation

---

## Next Steps

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Verify with Colab:**
   - Open `COLAB_QUICK_CHECK.ipynb`
   - Run all cells
   - Confirm "✅ VERIFICATION COMPLETE"

3. **Deploy locally:**
   ```bash
   chmod +x morning_ocaml_routine.sh
   crontab -e
   # Add: 0 8 * * 1-5 /Users/umashankar/morning_ocaml_routine.sh
   ```

4. **Monitor:**
   ```bash
   tail -50 /Users/umashankar/logs/morning_routine_*.log
   open /Users/umashankar/DAILY_SCREENING_REPORT.html
   ```

---

## Support & Documentation

- **Quick Start:** `QUICK_START.md`
- **Setup Guide:** `MORNING_ROUTINE_SETUP.md`
- **Deployment:** `DEPLOYMENT_CHECKLIST.md`
- **System Overview:** `INTEGRATED_SYSTEM_SUMMARY.md`
- **Colab Notebook:** `COLAB_QUICK_CHECK.ipynb`

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-07-06 | Initial release |

---

**Status:** ✅ Production Ready

Installation should take 2-5 minutes. Verification with Colab takes 5-10 minutes.

