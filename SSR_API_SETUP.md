# SSR Innovation Lab API - Setup & Authentication

## 🔐 What You Need

To authenticate with SSR API, you'll need one of these:

### Option 1: Username & Password
```
Website: https://api.ssrinnovationlab.com/
Username: [your SSR username]
Password: [your SSR password]
```

### Option 2: API Key
```
Website: https://api.ssrinnovationlab.com/
Login to account settings → Generate API Key
Example: "abc123def456ghi789jkl"
```

### Option 3: Bearer Token
```
Website: https://api.ssrinnovationlab.com/
Login to account → Get Bearer Token
Example: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

## 📝 Quick Questions to Prepare

Before running the script, gather:

1. **Do you have an SSR account?**
   - If NO: Visit https://api.ssrinnovationlab.com/ and register
   - If YES: Proceed to next step

2. **What authentication method do you have?**
   - Basic Auth (username + password) - Most common
   - API Key (from account settings)
   - Bearer Token (from account)

3. **Do you know your credentials?**
   - Have them ready before running the script

---

## 🚀 Running the Script

```bash
cd api-data-integration/
python3 ssr_api_handler.py
```

You'll be prompted to:
1. **Select authentication method** (1-4)
2. **Enter your credentials** (username/password, API key, or token)
3. **Script automatically:**
   - Authenticates to SSR API
   - Fetches outlet data
   - Processes and standardizes data
   - Exports to multiple formats
   - Generates statistics

---

## 📂 Expected Output

After successful authentication:

```
outlet_data_ssr/
├── ssr_outlets_20260624_053600.csv       ← Spreadsheet
├── ssr_outlets_20260624_053600.json      ← JSON
├── ssr_outlets_20260624_053600.geojson   ← Geographic
├── ssr_outlets_20260624_053600.js        ← For maps ⭐
└── ssr_outlets_stats_20260624_053600.json ← Statistics
```

---

## ✅ Integration Checklist

- [ ] Have SSR credentials ready
- [ ] Run: `python3 ssr_api_handler.py`
- [ ] Select auth method (1-4)
- [ ] Enter credentials
- [ ] Verify: `ls outlet_data_ssr/`
- [ ] Check statistics file
- [ ] Copy `.js` file to fuel-pump-locations-map/
- [ ] Test in browser
- [ ] Commit to GitHub

---

## 🆘 Need SSR Credentials?

### If you have SSR account but forgot credentials:
1. Visit: https://api.ssrinnovationlab.com/
2. Click: "Forgot Password"
3. Reset password
4. Log in and generate API key (if preferred)

### If you don't have SSR account:
1. Visit: https://api.ssrinnovationlab.com/
2. Click: Register / Sign Up
3. Create account with email
4. Verify email
5. Log in
6. Go to: Settings → API Keys
7. Generate new API key
8. Copy and use in script

---

## 🔑 Common Credential Formats

### Basic Auth
```
Username: john.doe@example.com
Password: mypassword123
```

### API Key
```
Format: 32-64 character string
Example: "your_api_key_string_here_12345"
```

### Bearer Token
```
Format: JWT format (long string)
Example: "your_bearer_token_here_abc123..."
```

---

## 🎯 Step by Step

### Step 1: Get Credentials (5 minutes)
- [ ] Visit https://api.ssrinnovationlab.com/
- [ ] Log in (or register if needed)
- [ ] Get/generate credentials
- [ ] Copy to notepad

### Step 2: Run Authentication Script (2 minutes)
```bash
cd api-data-integration/
python3 ssr_api_handler.py
```

### Step 3: Provide Credentials (1 minute)
```
Select method (1-4): 1    # or your method
Username: [paste username]
Password: [paste password]
```

### Step 4: Verify Output (2 minutes)
```bash
ls outlet_data_ssr/
cat outlet_data_ssr/ssr_outlets_stats_*.json
```

### Step 5: Integrate with Maps (3 minutes)
```bash
cp outlet_data_ssr/ssr_outlets_LATEST.js \
   ../fuel-pump-locations-map/locations-data.js
```

### Step 6: Test in Browser (2 minutes)
```bash
cd ../fuel-pump-locations-map/
python3 -m http.server 8000
# Visit http://localhost:8000
```

---

## ⚠️ Troubleshooting

### "Authentication failed: Status 401"
- ❌ Wrong username/password
- ✅ Check credentials again
- ✅ Try different auth method

### "Got HTML response"
- ❌ API returned web page instead of JSON
- ✅ Verify credentials are correct
- ✅ Contact SSR support

### "Connection timeout"
- ❌ API server down or network issue
- ✅ Try again in a few minutes
- ✅ Check internet connection

### "Module not found: requests"
```bash
pip install requests pandas
```

---

## 📞 Getting Help

### SSR Support:
- **Website:** https://api.ssrinnovationlab.com/
- **Login:** To contact support

### Script Issues:
- Check: Python error messages
- Verify: Credentials format
- Try: Different auth method
- Contact: SSR support with error

---

## 🎯 Success Indicators

✅ You know your SSR credentials  
✅ You can run Python scripts  
✅ You have internet connection  
✅ You can access https://api.ssrinnovationlab.com/

---

**Ready? Let's start:**

```bash
cd api-data-integration/
python3 ssr_api_handler.py
```

Gather your SSR credentials and follow the prompts!
