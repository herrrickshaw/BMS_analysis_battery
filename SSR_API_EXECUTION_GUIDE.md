# SSR API - Step-by-Step Execution Guide

**Time Required:** 10-15 minutes  
**Status:** Ready to execute

---

## 📋 Before You Start - Gather Your Info

You'll need ONE of these:

### Option A: Username + Password
```
Username: [your@email.com or username]
Password: [your SSR password]
```

### Option B: API Key
```
API Key: [32-64 character string from SSR account]
```

### Option C: Bearer Token
```
Bearer Token: [long JWT token from SSR account]
```

**👉 Have this information ready before starting!**

---

## 🚀 Step 1: Open Terminal

```bash
cd /Users/umashankar/api-data-integration
```

Verify you're in the right directory:
```bash
ls ssr_api_handler.py
# Should show: ssr_api_handler.py
```

---

## 🔐 Step 2: Run the Script

```bash
python3 ssr_api_handler.py
```

You'll see:
```
🔐 SSR Innovation Lab API Handler
======================================================================

🔑 Authentication Methods:
  1. Basic Auth (username + password)
  2. API Key
  3. Bearer Token
  4. Enter custom credentials

Select method (1-4):
```

---

## 🔑 Step 3: Choose Your Authentication Method

### If you have USERNAME + PASSWORD:
```
Select method (1-4): 1
Username: john.doe@example.com
Password: ••••••••••
```

### If you have API KEY:
```
Select method (1-4): 2
API Key: sk_live_abc123def456ghi789jkl
```

### If you have BEARER TOKEN:
```
Select method (1-4): 3
Bearer Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### If authentication type is unclear:
```
Select method (1-4): 4
# Will prompt you for more details
```

---

## ✅ Step 4: Wait for Authentication

The script will:
```
🔐 Attempting Basic Authentication...
  ✓ Authentication successful!
  ✓ Response contains 1000+ records
```

If you see ✅ **Authentication successful** → Continue to Step 5

If you see ❌ **Authentication failed** → Try different method or check credentials

---

## 📥 Step 5: Wait for Data Fetch

```
📥 Fetching data from SSR API...
  ✓ Fetched 1000 outlets
```

The script automatically:
- Connects to SSR API
- Downloads outlet data
- Processes each record
- Standardizes columns
- Validates coordinates

---

## ⚙️ Step 6: Processing

```
⚙️  Processing 1000 outlets...
  ✓ Processed 950 outlets
  ✓ States: 28
  ✓ Cities: 250+
```

The script:
- Removes invalid records
- Standardizes field names
- Validates coordinates
- Groups by location

---

## 💾 Step 7: Export

```
💾 Exporting to outlet_data_ssr/...
  ✓ CSV: outlet_data_ssr/ssr_outlets_20260624.csv
  ✓ GeoJSON: outlet_data_ssr/ssr_outlets_20260624.geojson
  ✓ JavaScript: outlet_data_ssr/ssr_outlets_20260624.js
  ✓ Statistics: outlet_data_ssr/ssr_outlets_stats_20260624.json
```

Files created:
- **CSV** - Open in Excel/Sheets
- **JSON** - Raw data format
- **GeoJSON** - Geographic format
- **JavaScript** - For web maps ⭐

---

## 🎉 Step 8: Verify Output

```bash
ls outlet_data_ssr/
```

Should show:
```
ssr_outlets_20260624_053600.csv
ssr_outlets_20260624_053600.geojson
ssr_outlets_20260624_053600.js
ssr_outlets_stats_20260624_053600.json
```

---

## 📊 Step 9: Check Statistics

```bash
cat outlet_data_ssr/ssr_outlets_stats_*.json
```

Should show:
```json
{
  "timestamp": "20260624_053600",
  "total_outlets": 950,
  "states": 28,
  "cities": 250,
  "source": "SSR Innovation Lab API"
}
```

---

## 📍 Step 10: Integrate with Maps

```bash
# Copy the JavaScript file to fuel pump map
cp outlet_data_ssr/ssr_outlets_*.js \
   ../fuel-pump-locations-map/locations-data.js

# Verify
ls ../fuel-pump-locations-map/locations-data.js
```

---

## 🧪 Step 11: Test in Browser

```bash
# Start the web server
cd ../fuel-pump-locations-map/
python3 -m http.server 8000
```

Open browser:
```
http://localhost:8000
```

Verify:
- ✅ Outlets appear on map
- ✅ Markers are clustered
- ✅ Zoom in/out works
- ✅ No console errors

**Check in browser console (F12):**
```
Press F12 → Console tab
Should be clean (no red errors)
```

---

## 💾 Step 12: Commit to GitHub

```bash
# Go to project root
cd /Users/umashankar

# Stage changes
git add api-data-integration/outlet_data_ssr/
git add fuel-pump-locations-map/locations-data.js

# Commit
git commit -m "Add SSR API outlet data integration"

# Push
git push origin main

# Verify
echo "Pushed successfully!"
```

---

## 🎯 Complete Checklist

- [ ] Gathered SSR credentials
- [ ] Opened terminal in api-data-integration/
- [ ] Ran: `python3 ssr_api_handler.py`
- [ ] Selected authentication method
- [ ] Entered credentials
- [ ] Authentication successful ✅
- [ ] Data fetched (outlets loaded)
- [ ] Processing complete
- [ ] Files exported to outlet_data_ssr/
- [ ] Verified statistics file
- [ ] Copied .js file to fuel-pump-locations-map/
- [ ] Started test server
- [ ] Opened http://localhost:8000 in browser
- [ ] Verified outlets appear on map
- [ ] Checked browser console (no errors)
- [ ] Committed to GitHub
- [ ] Pushed to GitHub

---

## ❌ Troubleshooting

### "Authentication failed: Status 401"
```
✓ Check username/password are correct
✓ Try API Key method instead
✓ Try Bearer Token method instead
✓ Verify no typos in credentials
```

### "ModuleNotFoundError: requests"
```bash
pip install requests pandas
python3 ssr_api_handler.py
```

### "Connection timeout"
```
✓ Check internet connection
✓ Try again (API may be temporarily down)
✓ Check https://api.ssrinnovationlab.com/ is accessible
```

### "Map not showing outlets"
```
✓ Hard refresh browser: Ctrl+Shift+R (or Cmd+Shift+R)
✓ Clear browser cache
✓ Check browser console (F12) for errors
✓ Verify file was copied correctly
```

### "No outlets loaded"
```
✓ Check statistics file
✓ Verify total_outlets is > 0
✓ Check that coordinates are present
```

---

## ⏱️ Time Breakdown

| Step | Time | What's Happening |
|------|------|------------------|
| Authentication | 1 min | Logging into SSR |
| Fetch | 2 min | Downloading data |
| Processing | 2 min | Standardizing data |
| Export | 1 min | Writing files |
| Verify | 1 min | Checking output |
| Integrate | 2 min | Copying to maps |
| Test | 2 min | Loading in browser |
| Commit | 1 min | Saving to GitHub |
| **TOTAL** | **12 min** | **Complete** |

---

## 🎯 Success = Outlets on Map

**If you see outlets clustered on the map → SUCCESS! ✅**

Then:
1. Commit to GitHub
2. Push to remote
3. Share portfolio update

---

## 📝 Example Session

```bash
$ cd api-data-integration/
$ python3 ssr_api_handler.py

🔐 SSR Innovation Lab API Handler
======================================================================

🔑 Authentication Methods:
  1. Basic Auth (username + password)
  2. API Key
  3. Bearer Token
  4. Enter custom credentials

Select method (1-4): 1
Username: john@example.com
Password: 

🔐 Attempting Basic Authentication...
  ✓ Authentication successful!
  ✓ Response contains 1000+ records

📥 Fetching data from SSR API...
  ✓ Fetched 1000 outlets

⚙️  Processing 1000 outlets...
  ✓ Processed 950 outlets
  ✓ States: 28
  ✓ Cities: 250+

💾 Exporting to outlet_data_ssr/...
  ✓ CSV: outlet_data_ssr/ssr_outlets_20260624.csv
  ✓ GeoJSON: outlet_data_ssr/ssr_outlets_20260624.geojson
  ✓ JavaScript: outlet_data_ssr/ssr_outlets_20260624.js
  ✓ Statistics: outlet_data_ssr/ssr_outlets_stats_20260624.json

📊 SSR API DATA SUMMARY
═════════════════════════════════════════════════════════════════
Total Outlets: 950
States: 28
Cities: 250+
═════════════════════════════════════════════════════════════════

✅ Success! Data exported to outlet_data_ssr/
```

---

## 🚀 Ready?

**Have your credentials?** Let's execute:

```bash
cd /Users/umashankar/api-data-integration
python3 ssr_api_handler.py
```

**Questions about credentials?** See `SSR_API_SETUP.md`

**All done?** Commit and push to GitHub!

---

**Last Updated:** June 24, 2026  
**Time to Complete:** 10-15 minutes  
**Status:** Ready to execute
