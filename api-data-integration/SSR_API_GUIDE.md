# SSR Innovation Lab API Integration Guide

Access retail outlet data from SSR Innovation Lab API with authentication.

**API:** https://api.ssrinnovationlab.com/api/test/18/

## 🔐 Authentication Methods

### Method 1: Basic Auth (username + password)
```bash
python3 ssr_api_handler.py
# Select option 1
# Enter username and password
```

### Method 2: API Key
```bash
python3 ssr_api_handler.py
# Select option 2
# Enter API key
```

### Method 3: Bearer Token
```bash
python3 ssr_api_handler.py
# Select option 3
# Enter token
```

### Method 4: Custom Headers
```bash
python3 ssr_api_handler.py
# Select option 4
# Choose header type
```

---

## 🔑 Getting Credentials

### If you have SSR account:
1. Log in to: https://api.ssrinnovationlab.com/
2. Find your credentials:
   - **Username/Password** - Account login
   - **API Key** - API section
   - **Bearer Token** - Token section

### If you don't have account:
1. Visit: https://api.ssrinnovationlab.com/
2. Click: Register/Sign Up
3. Create account
4. Generate API key in settings
5. Copy key and use in script

---

## 📝 Quick Start

```bash
cd api-data-integration/

# Run interactive authentication
python3 ssr_api_handler.py

# Select your auth method (1-4)
# Enter credentials when prompted
# Script fetches and processes data
```

**Output files generated:**
- `outlet_data_ssr/ssr_outlets_YYYYMMDD.csv` - Tabular
- `outlet_data_ssr/ssr_outlets_YYYYMMDD.geojson` - Geographic
- `outlet_data_ssr/ssr_outlets_YYYYMMDD.js` - For maps
- `outlet_data_ssr/ssr_outlets_stats_YYYYMMDD.json` - Statistics

---

## 🧪 Testing Authentication

```python
# Quick test in Python
import requests

# Basic Auth
response = requests.get(
    'https://api.ssrinnovationlab.com/api/test/18/',
    auth=('username', 'password')
)
print(response.status_code)
print(response.json())

# API Key
headers = {'X-API-Key': 'YOUR_API_KEY'}
response = requests.get(
    'https://api.ssrinnovationlab.com/api/test/18/',
    headers=headers
)
print(response.json())

# Bearer Token
headers = {'Authorization': 'Bearer YOUR_TOKEN'}
response = requests.get(
    'https://api.ssrinnovationlab.com/api/test/18/',
    headers=headers
)
print(response.json())
```

---

## 🔧 Script Features

### Automatic Features:
✅ Handles multiple auth methods  
✅ Column name standardization  
✅ Coordinate validation  
✅ Multiple export formats  
✅ Automatic retry logic  
✅ Error handling

### Export Formats:
- **CSV** - Spreadsheet compatible
- **JSON** - Structured data
- **GeoJSON** - Geographic features
- **JavaScript** - Web map integration
- **Statistics** - Coverage metadata

---

## 📊 Expected Output

If authentication successful:
```
✓ Authentication successful!
✓ Response contains 1000+ records
✓ Fetched 1000 outlets
✓ Processed 950 outlets
✓ States: 28
✓ Cities: 250+
✓ Export complete!
```

---

## ❌ Troubleshooting

### "Authentication failed: Status 401"
- Check username/password are correct
- Verify API key is valid
- Try different auth method
- Contact SSR for credential help

### "Got HTML response (still not JSON)"
- API may not require authentication (unlikely)
- Try adding more authentication headers
- Contact SSR support

### "SSL Certificate Error"
```bash
# If certificate issues:
# (Not recommended, but for testing)
python3 -c "import requests; requests.get('url', verify=False)"
```

### "Connection Timeout"
- API server may be down
- Check your internet connection
- Try again in a few minutes

### "Unknown response format"
- API may return data in `data` or `outlets` field
- Script auto-detects, but may need adjustment
- Check raw API response

---

## 📋 Common Credentials

If SSR provided test credentials:

```
Website: https://api.ssrinnovationlab.com/
Username: [Contact SSR for credentials]
Password: [Contact SSR for credentials]
API Key: [Contact SSR for credentials]
Bearer Token: [Contact SSR for credentials]
```

---

## 🔄 Process Flow

```
Enter Credentials
      ↓
[ssr_api_handler.py]
      ↓
Authenticate → Fetch → Process → Export
      ↓
[outlet_data_ssr/]
├─ CSV
├─ JSON
├─ GeoJSON
├─ JavaScript ⭐
└─ Statistics
```

---

## 💾 Integration with Maps

```bash
# Copy JavaScript to fuel map
cp outlet_data_ssr/ssr_outlets_LATEST.js \
   ../fuel-pump-locations-map/locations-data.js

# Test
cd ../fuel-pump-locations-map/
python3 -m http.server 8000
# Visit http://localhost:8000
```

---

## 🚀 Full Integration (5 steps)

1. **Get credentials from SSR**
   - Register at: https://api.ssrinnovationlab.com/
   - Get API key or token

2. **Run authentication script**
   ```bash
   python3 ssr_api_handler.py
   ```

3. **Verify output generated**
   ```bash
   ls outlet_data_ssr/
   ```

4. **Integrate with maps**
   ```bash
   cp outlet_data_ssr/ssr_outlets_LATEST.js \
      ../fuel-pump-locations-map/locations-data.js
   ```

5. **Test and commit**
   ```bash
   cd ../fuel-pump-locations-map/
   python3 -m http.server 8000
   # Test in browser
   git add .
   git commit -m "Add SSR API outlet data"
   git push
   ```

---

## 🆘 Need Help?

### SSR Support:
- **Website:** https://api.ssrinnovationlab.com/
- **Contact:** [Check website for support]

### Common Questions:
- **Q: No API key yet?** Register and create one in account settings
- **Q: Which auth method?** Ask SSR which they support
- **Q: Wrong credentials?** Double-check spelling and spaces
- **Q: Still failing?** Contact SSR support with error message

---

## 📈 What You'll Get

Depends on SSR dataset size:
- Location coordinates (latitude/longitude)
- Outlet names and companies
- Cities and states
- Multiple export formats
- Ready-to-map data

---

**Status:** Ready with authentication support  
**Last Updated:** June 24, 2026
