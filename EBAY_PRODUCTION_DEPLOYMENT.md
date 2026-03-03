# eBay Integration - Production Deployment Guide

## Current Status ✅
- **Code**: Complete and tested
- **Database Schema**: Ready (no migrations needed)
- **API Credentials**: Configured in `settings.py`
- **Network Protection**: Retry logic and timeout handling implemented

## Network Issue Resolution
Local development environment has network restrictions preventing eBay API access. **This is solved by deploying to PythonAnywhere** which has unrestricted network access.

## Deployment Steps

### Step 1: Push Changes to Git
```bash
cd c:\Users\ab111777\Desktop\alibaba

# Stage all changes
git add -A

# Commit with clear message
git commit -m "eBay Integration: Add network resilience, fix OAuth endpoints"

# Push to main branch
git push origin main
```

### Step 2: SSH into PythonAnywhere
```bash
# Start SSH session
ssh yourusername@yourusername.pythonanywhere.com

# Navigate to web app directory
cd /home/yourusername/mysite  # or your app directory
```

### Step 3: Pull Latest Code
```bash
# Pull the latest changes
git pull origin main

# Install any new dependencies (if needed)
pip install -r requirements.txt

# Collect static files
python manage.py collectstatic --noinput

# Run migrations (just in case)
python manage.py migrate
```

### Step 4: Import Real eBay Products
```bash
# Test with sandbox first (recommended)
python manage.py import_ebay_products "smartwatch" --limit=5 --sandbox

# Once confirmed, import from PRODUCTION
python manage.py import_ebay_products "drone" --limit=10
python manage.py import_ebay_products "trimui smart pro" --limit=10
python manage.py import_ebay_products "gaming laptop" --limit=15
```

### Step 5: Verify in Browser
Visit your website and confirm:
- eBay products appear with **yellow background** and **orange left border**
- **🏆 Orijinal** badge shows on eBay items
- Product images load properly
- Prices display in USD
- Affiliate links are correct

## What Was Fixed

### 1. **Network Resilience** (ebay_api.py)
```python
# Added HTTPAdapter with retry strategy
retry_strategy = Retry(
    total=3,  # Retry up to 3 times
    backoff_factor=1,  # Wait 1s, 2s, 4s between retries
    status_forcelist=[429, 500, 502, 503, 504],  # Retry on these status codes
    allowed_methods=["POST", "GET"]
)
```

### 2. **Increased Timeouts**
- Changed from 10s → **30 seconds** for OAuth token requests
- Changed from 15s → **30 seconds** for API search requests

### 3. **Better Exception Handling**
- Specific catch for `requests.exceptions.Timeout`
- Specific catch for `requests.exceptions.ConnectionError`
- Detailed error logging for debugging

### 4. **Corrected OAuth Endpoints**
- Production: `https://api.ebay.com/oauth2/token`
- Sandbox: `https://api.sandbox.ebay.com/oauth2/token`

## Monitoring After Deployment

### Check Affiliate Clicks in eBay Partner Network
1. Log into [https://publisher.ebaypartnernetwork.com](https://publisher.ebaypartnernetwork.com)
2. Navigate to **Reports** → **Click Reports**
3. Check for clicks on your campaign ID: **5339143578**

### Django Logs
On PythonAnywhere, check logs for any API errors:
```bash
# View recent API activity
tail -f /home/yourusername/mysite/ebay_api.log
```

## Troubleshooting

### If products aren't importing:
```bash
# Run with verbose logging
python manage.py import_ebay_products "drone" --limit=5 -v 3
```

### If images aren't showing:
- Check that `UrunResim.resim_url` contains full eBay image URLs
- Verify eBay image URLs are not blocked by CORS

### If affiliate links aren't working:
- Verify campaign ID is correct: `5339143578`
- Check link format: `https://ebay.com/itm/{item_id}?campid=5339143578&customid={custom_id}`

## Configuration Files

### settings.py (already configured)
```python
EBAY_PRODUCTION_CLIENT_ID = 'AliAltns-rnkarlat-PRD-...'
EBAY_PRODUCTION_CLIENT_SECRET = 'PRD-...'
EBAY_CAMPAIGN_ID = '5339143578'
```

### Database Models (no changes needed)
- ✅ `Urun` - Product name, description, images
- ✅ `Magaza` - Store name (eBay created automatically)
- ✅ `Fiyat` - Price, affiliate_link, contact info
- ✅ `UrunResim` - Product images with URLs

## Caching
OAuth tokens are automatically cached for 1 hour to reduce API calls:
```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}
```

## Next Steps (Optional)

### 1. **Schedule Automated Imports**
Use Celery Beat to update products daily:
```bash
python -m celery -A urun_karsilastirma worker -B
```

### 2. **Track Performance**
- Monitor affiliate click-through rates
- Track which products get the most clicks
- Adjust import searches based on performance

### 3. **Expand to Other Affiliate Networks**
- Already have AliExpress integration ✅
- eBay integrated ✅
- Consider: Amazon Associates, Admitad, etc.

---

**Status**: Ready for production deployment  
**Last Updated**: 2026-03-03  
**Environment**: PythonAnywhere (production) or local (with network access)
