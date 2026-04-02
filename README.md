# Yerelde Sanal Ortam (Virtual Environment) Oluşturma

Projeyi izole bir ortamda çalıştırmak için sanal ortam kullanmanız önerilir. Windows için komutlar:

```bash
python -m venv .venv
.venv\Scripts\activate
```

Linux/Mac için:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

# Ürün Karşılaştırma Platformu (Django)

Bu proje, farklı mağazalardaki ürünlerin fiyatlarını karşılaştırabileceğiniz ve affiliate linklerle gelir elde edebileceğiniz bir Django tabanlı web uygulamasıdır.

## Ana Takip Dosyası

Güncel operasyon adımları için önce `OPERASYON_MERKEZI.md` dosyasını takip edin.

## Özellikler

- Ürün ekleme, mağaza ekleme
- Her ürün için birden fazla mağazadan fiyat ve affiliate linki ekleyebilme
- Ana sayfada ürünlerin ve mağazalara göre fiyatlarının listelenmesi
- Responsive ve modern arayüz
- Medya (resim) ve statik dosya yönetimi
  - Başlık, fiyat, resim otomatik çekme
  - İsteğe bağlı manuel fiyat girebilme
  - Affiliate link otomatik oluşturma

## CSV'den Toplu Ürün Ekleme

Chrome uzantısı ile çektiğiniz ürünleri CSV olarak kaydedip, aşağıdaki komutla Django'ya toplu olarak ekleyebilirsiniz:

```bash
python manage.py import_csv_products chrome_eklenti/urunler.csv
```

Bu komut, CSV dosyasındaki ürünleri veritabanına ekler, fiyatı otomatik olarak 1.65 ile çarpar ve affiliate link oluşturur.

## Canlı Site

**Durum:** Site şu an PythonAnywhere'de çalışıyor (https://kolaybulexpres.pythonanywhere.com)
**Deployment:** `PYTHONANYWHERE_DEPLOYMENT.md` dosyasındaki adımları takip edin.

## SQLite Politikası (Güncel)

- `db.sqlite3` GitHub'a gönderilmez.
- Canlı veritabanı repo dışında tutulur.
- Kod güncellemesi `git pull --ff-only` ile yapılır, veritabanı dosyası bu akıştan etkilenmez.

---

## Kurulum

1. Sanal ortam oluşturun ve aktifleştirin:

   ```bash
   python -m venv .venv
   .venv\Scripts\Activate.ps1  # Windows
   source .venv/bin/activate    # Linux/Mac
   ```
2. Gerekli paketleri yükleyin:

   ```bash
   pip install -r requirements.txt
   ```
3. `.env` dosyası oluşturun (`.env.example`'dan kopyalayın):

   ```bash
   cp .env.example .env
   ```

   Sonra `.env` dosyasındaki değerleri doldurun:

   ```
   ADMITAD_CLIENT_ID=your_client_id
   ADMITAD_CLIENT_SECRET=your_client_secret
   ADMITAD_ACCESS_TOKEN=your_access_token
   ADMITAD_REFRESH_TOKEN=your_refresh_token
   SECRET_KEY=your-django-secret-key
   ```
4. Veritabanı migrasyonlarını çalıştırın:

   ```bash
   python manage.py migrate
   ```
5. Yönetici hesabı oluşturun:

   ```bash
   python manage.py createsuperuser
   ```
6. Geliştirme sunucusunu başlatın:

   ```bash
   python manage.py runserver
   ```

## Klasör Yapısı

- `urunler/` : Uygulama ana dizini (modeller, görünümler, şablonlar)
- `urunler/models.py` : Ürün, Mağaza ve Fiyat modelleri
- `urunler/views.py` : Ana sayfa ve ürün listesi görünümleri
- `urunler/templates/urunler/` : HTML şablonları (anasayfa, base)
- `static/` : Statik dosyalar (CSS, görseller)
- `media/` : Yüklenen ürün resimleri

## Kullanım

- Yönetici panelinden ürün, mağaza ve fiyat ekleyin.
- Ana sayfada ürünler ve mağazalara göre fiyatlar listelenir.
- Kullanıcılar mağaza butonlarına tıklayarak affiliate link üzerinden yönlendirilir.

## Admitad API Kullanımı

### Token Alma (İlk Kurulum)

1. Authorization URL oluştur:

   ```bash
   python manage.py get_admitad_auth
   ```
2. Tarayıcıda açılan URL'yi onayla ve `code` parametresini al
3. Token'ı kaydet:

   ```bash
   python manage.py save_admitad_token <CODE>
   ```

### Website ID Öğrenme (Deeplink için gerekli)

```bash
python manage.py list_admitad_websites
```

### Deeplink Oluşturma (AliExpress kampanya 6115)

```bash
python manage.py create_admitad_deeplink <PRODUCT_URL> --website <WEBSITE_ID> --campaign 6115
```

### Deeplink (API olmadan, base link ile)

Admitad panelindeki "Derin bağlantı oluşturucu"da görünen taban linkinizi `.env`'e ekleyin:

```
ADMITAD_BASE_LINK=https://rzekl.com/g/1e8d11449462ceef436f16525dc3e8/
```

Sonra komutu çalıştırın:

```bash
python manage.py create_manual_deeplink "https://www.aliexpress.com/item/100500...html" --subid aa
```

İsterseniz `--base` ile linki doğrudan da verebilirsiniz:

```bash
python manage.py create_manual_deeplink "<PRODUCT_URL>" --base "https://rzekl.com/g/xxxx/" --subid aa
```

### AliExpress Ürün Çekme (Yakında)

```bash
python manage.py fetch_aliexpress_products --category electronics --limit 50
```

## Önemli Notlar

### Credential'lar

- **Client ID/Secret:** Admitad API ayarlarından alındı
- **Access Token:** 7 gün geçerli (604800 saniye)
- **Refresh Token:** Kalıcı, token yenileme için kullanılır
- **AliExpress Campaign ID:** 6115

### Güvenlik

- `.env` dosyası Git'e ASLA commit edilmez (`.gitignore`'da)
- `admitad_token.json` ve credential dosyaları Git'e gitmez
- PythonAnywhere'de `.env` manuel oluşturulmalı

### PythonAnywhere Deploy

1. GitHub'dan kod çek
2. `.env` dosyasını manuel oluştur ve credential'ları ekle
3. `python manage.py migrate`
4. `python manage.py collectstatic`
5. Web app'i reload et

## Nasıl Kullanılır

### Otomatik Ürün Ekleme (Admin Paneli)

1. Admin paneline giriş yapın: `http://localhost:8000/admin`
2. Sol menüde "Ürünler" → "Ürün Ekle" yerine **"Ürün (Yönet)" sekmesine tıklayın**
3. "**Ürünler**" sayfasının en üstünde "**AliExpress Linkinden Ürün Ekle**" butonuna tıklayın
4. Açılan forma:
   - **AliExpress URL:** Eklemek istediğiniz ürünün linkini yapıştırın (örn: `https://www.aliexpress.com/item/...`)
   - **Takip Kodu (İsteğe Bağlı):** Admitad'da ürünü takip etmek için benzersiz kod girin (örn: "kulaklık", "saat")
   - **Fiyat (İsteğe Bağlı):** Sistem otomatik fiyat çekmeye çalışacaksa boş bırakın. Çekilemezse burada manuel girin (örn: 45.99)
5. "**Ürün Ekle**" butonuna tıklayın
6. Sistem otomatik olarak:
   - ✅ Ürün başlığını çeker
   - ✅ Fiyatı otomatik çekmeye çalışır (başarısız durumda fallback: 199.99 TL)
   - ✅ Resim URL'sini kaydeder
   - ✅ Admitad API'den affiliate link oluşturur
   - ✅ Veritabanına kaydeder

**Bilgi:** Fiyat çekilemezse **199.99 TL** varsayılan atanır. Sonra ürün detaylarına giderek fiyatı düzenleyebilirsiniz.

### Manuel Ürün Ekleme

Admin panelinde "Ürün Ekle" (+ buton) ile klasik şekilde ürün ekleyebilirsiniz, sonra fiyat ve resim ekleyebilirsiniz.

- **Ürün Getiri Komutları (Geliştirme)**

  ```bash
  # Commandes satırından 10 ürünü getir (eski yöntem - önerilmez)
  python manage.py fetch_aliexpress_products --count 10
  ```

## Notlar

- Affiliate linklerinizi mağaza eklerken veya fiyat eklerken ilgili alana girin.
- Geliştirme ortamında medya dosyalarını sunmak için ayarlar yapılmıştır.
- Resim URL'leri kaydedilir, resim dosyaları indirilmez (alan tasarrufu).
- AliExpress'te gösterilen fiyat aynen kaydedilir (gümrük/vergi müşteriye aittir).

## Geliştirme Durumu

- ✅ Temel Django yapısı
- ✅ Ürün, Mağaza, Fiyat modelleri
- ✅ Çoklu resim desteği
- ✅ Kullanıcı yorumları
- ✅ Tıklama loglama
- ✅ Admitad API OAuth2 entegrasyonu
- ✅ Admin panelinden otomatik ürün ekleme (link üzerinden)
- ✅ Otomatik başlık, resim, açıklama çekme
- ✅ Otomatik affiliate link oluşturma
- ✅ Manuel fiyat override seçeneği
- ✅ PythonAnywhere deployment hazır
- ⏳ Otomatik fiyat güncelleme (scheduler)
- ⏳ JavaScript rendering ile fiyat çekme (Selenium/Playwright)

## eBay Affiliate Ürünleri Canlıya Ekleme (PythonAnywhere)

**Amaç:** eBay'dan ürünleri otomatik olarak çekip, EPN (eBay Partner Network) affiliate linklerini ekleyerek canlı siteye yayınlamak.

### Adım 1: Kodları Çekme
```bash
cd ~/alibaba
git pull origin main
```

### Adım 2: eBay Ürünlerini İçeri Aktarma

Aşağıdaki komutu PythonAnywhere bash konsolunda çalıştırın:

```bash
python3.10 manage.py import_ebay_products "laptop" --limit=20 --translate-tr
```

**Parametre Açıklaması:**
- `"laptop"` = Aratılacak ürün adı (drone, telefon, bilgisayar, vb olabilir)
- `--limit=20` = Kaç ürün import edilecek (1-200 arası, varsayılan: 20)
- `--translate-tr` = Ürün başlıkları otomatik Türkçeye çevrilsin

**Örnek komutlar:**
```bash
# 10 drone ürünü
python3.10 manage.py import_ebay_products "drone" --limit=10 --translate-tr

# 50 telefon ürünü
python3.10 manage.py import_ebay_products "telefon" --limit=50 --translate-tr

# 100 Gaming ürünü
python3.10 manage.py import_ebay_products "gaming" --limit=100 --translate-tr
```

### Adım 3: Web Uygulamasını Yeniden Başlatma
PythonAnywhere → **Web** sekmesi → **Reload** (yeşil düğme)

### Adım 4: Sonuç

- Ürünler **5 haneli benzersiz kod** ile kaydedilir (ör: `42567`)
- Her ürün **EPN affiliate linki** alır (`campid=5339143578` ile)
- **customid** parametresi ürün koduna eşit olur
- EPN raporunda hangi ürüne tıklandığını görebilirsiniz

### Affiliate Takibi

eBay Partner Network dashboard'ında:
- **Customid** = Ürün kodunuz (42567, 89123, vb)
- **Reports** → Tıklamaları ve dönüşümleri görebilirsiniz

---

## AliExpress API Entegrasyonu

**Durum:** ✅ Aktif ve çalışıyor  
**API Tipi:** AliExpress Portals API (Affiliates API)  
**Kimlik Doğrulama:** MD5 Signature

### Ön Gereksinimler

1. **AliExpress Portals hesabı** oluşturun: https://portals.aliexpress.com
2. **App Key** ve **App Secret** alın
3. `.env` dosyasına ekleyin:

```env
ALIEXPRESS_APP_KEY=528840
ALIEXPRESS_APP_SECRET=your_app_secret_here
```

### API Bağlantısını Test Etme

Önce API'nin çalıştığından emin olun:

```bash
python test_aliexpress_api.py
```

**Beklenen Çıktı:**
```
============================================================
AliExpress Portals API Integration Test
============================================================

✓ App Key: 528840
✓ App Secret: mOfqET9Rse...

[1] Searching for 'wireless headphones' (limit: 5)...
------------------------------------------------------------
✓ API Response received

✓ Found 5 products:
============================================================

[1] AI Translation Headphones True Wireless Earbuds...
    Product ID: 1005010796035063
    Price: 15.96 USD
    ...
✓ AliExpress API Connection Test PASSED
```

### AliExpress Ürünlerini Veritabanına Ekleme

#### Temel Kullanım

```bash
python manage.py import_aliexpress_products "arama_terimi" --limit=SAYI
```

#### 📋 Örnek Komutlar

**1. 5 Ürün Test İmportu (Önerilen Başlangıç):**
```bash
python manage.py import_aliexpress_products "wireless headphones" --limit=5
```

**2. Laptop Ürünleri:**
```bash
python manage.py import_aliexpress_products "laptop" --limit=20
```

**3. Drone Ürünleri:**
```bash
python manage.py import_aliexpress_products "drone" --limit=15
```

**4. Smart Watch Ürünleri:**
```bash
python manage.py import_aliexpress_products "smart watch" --limit=10
```

**5. Gaming Mouse:**
```bash
python manage.py import_aliexpress_products "gaming mouse" --limit=25
```

#### 🎯 Gelişmiş Parametreler

**Fiyat Filtresi ile:**
```bash
# 50-200 USD arası ürünler
python manage.py import_aliexpress_products "drone" --limit=10 --min-price=50 --max-price=200
```

**Tracking ID ile (Affiliate Takibi):**
```bash
python manage.py import_aliexpress_products "laptop" --limit=20 --tracking-id=mylaptops2024
```

**Kombine Kullanım:**
```bash
python manage.py import_aliexpress_products "mechanical keyboard" \
  --limit=30 \
  --min-price=30 \
  --max-price=150 \
  --tracking-id=keyboards_march
```

#### 📊 Komut Parametreleri

| Parametre | Açıklama | Zorunlu | Örnek |
|-----------|----------|---------|-------|
| `search_query` | Arama terimi | ✅ Evet | `"wireless headphones"` |
| `--limit` | Ürün sayısı (max: 50) | ❌ Hayır | `--limit=20` |
| `--min-price` | Min fiyat (USD) | ❌ Hayır | `--min-price=10` |
| `--max-price` | Max fiyat (USD) | ❌ Hayır | `--max-price=100` |
| `--tracking-id` | Takip kodu | ❌ Hayır | `--tracking-id=myid` |

#### 🎬 İmport İşlemi Çıktısı

```bash
$ python manage.py import_aliexpress_products "wireless headphones" --limit=5

✓ Using AliExpress Portals API
Searching for: "wireless headphones" (limit: 5)
✓ Found 5 products
Processing...
  ✓ Created: Danny Gen4 V1 TWS Bluetooth 5.4 Earphone...
  ✓ Created: AI Translation Headphones True Wireless...
  ✓ Created: Choice Lenovo LP7 OWS Wireless Bluetooth...
  ✓ Created: MSAI T23 AI Translator Earbuds...
  ✓ Created: Q16S AI Translation Real Time Translator...

=== IMPORT SUMMARY ===
✓ Successfully imported: 5
Total processed: 5
```

### İmport Edilen Ürünleri Kontrol Etme

```bash
python check_aliexpress_products.py
```

**Beklenen Çıktı:**
```
======================================================================
ALIEXPRESS IMPORTED PRODUCTS
======================================================================

✓ AliExpress Store: https://www.aliexpress.com

✓ Found 5 wireless/audio products

[1] Q16S AI Translation Real Time Translator Earbuds...
    Product Code: 37967
    Price: 32.69 USD
    Store: AliExpress
    Affiliate: https://s.click.aliexpress.com/...
    Image: ✓
    
[2] MSAI T23 AI Translator Earbuds...
    Product Code: 50069
    Price: 20.20 USD
    ...
```

### 🗄️ Veritabanı Yapısı

AliExpress ürünleri şu şekilde kaydedilir:

**Mağaza (Magaza):**
- `isim`: "AliExpress"
- `web_adresi`: "https://www.aliexpress.com/"

**Ürün (Urun):**
- `isim`: Ürün başlığı (max 200 karakter)
- `urun_kodu`: 5 haneli benzersiz kod (örn: `37967`)
- `ana_baslik`: Tam ürün başlığı
- `alt_baslik`: Kategori + indirim bilgisi
- `etiketler`: Otomatik oluşturulan etiketler
- `ozellikler`: Kategori, ID, indirim, komisyon vb.
- `resim_url`: Ürün görseli URL
- `source_url`: Orijinal AliExpress URL (duplicate kontrolü)

**Fiyat (Fiyat):**
- `fiyat`: Ürün fiyatı (USD)
- `para_birimi`: "USD"
- `affiliate_link`: AliExpress promotion link
- `gonderim_ucreti`: 0 (genelde ücretsiz)
- `gonderim_yerinden`: "Çin"

**Resim (UrunResim):**
- `resim_url`: Ürün görseli (URL olarak kaydedilir, indirilmez)

### 🔐 Özellikler

✅ **Duplicate Control** - Aynı ürün tekrar eklenmez (`source_url` kontrolü)  
✅ **Otomatik Etiketleme** - Kategori + başlık kelimelerinden  
✅ **Affiliate Link** - Her ürün için promotion link oluşturulur  
✅ **Benzersiz Kod** - 5 haneli unique product code  
✅ **Resim URL** - Görseller URL olarak kaydedilir (disk alanı tasarrufu)  
✅ **Error Handling** - Hatalı ürünler atlanır, import devam eder  
✅ **Retry Mechanism** - API hataları için 3 deneme  

### 🚀 PythonAnywhere'de Kullanım

**1. SSH/Bash Konsolunda:**
```bash
cd ~/alibaba
source .venv/bin/activate  # Varsa
python3.10 manage.py import_aliexpress_products "laptop" --limit=20
```

**2. Credentials'ları Kontrol Edin:**
```bash
# .env dosyasında olmalı
cat .env | grep ALIEXPRESS
```

**3. Web App'i Reload Edin:**
PythonAnywhere → **Web** → **Reload** ✅

### 📈 API Limitleri

- **Max ürün/istek:** 50
- **Request signature:** MD5 hash
- **Response format:** JSON
- **Pagination:** `page_no` parametresi ile

### 🆚 eBay vs AliExpress Karşılaştırma

| Özellik | eBay API | AliExpress API |
|---------|----------|----------------|
| **Authentication** | OAuth 2.0 | MD5 Signature |
| **Max/Request** | 200 ürün | 50 ürün |
| **Para Birimi** | USD | USD |
| **Fiyat Filtresi** | ✅ Var | ✅ Var |
| **Affiliate Sistem** | EPN (Campaign ID) | Promotion Links |
| **Kargo Bilgisi** | Detaylı | Genelde Çin |
| **Durum** | ✅ Aktif | ✅ Aktif |

### ⚠️ Sorun Giderme

**1. "Signature does not conform" Hatası:**
```bash
# .env dosyasındaki credentials'ları kontrol edin
echo $ALIEXPRESS_APP_KEY
echo $ALIEXPRESS_APP_SECRET
```

**2. "No products found" Uyarısı:**
- Farklı arama terimi deneyin
- Daha düşük limit ayarlayın
- Fiyat filtrelerini kaldırın

**3. "Failed to fetch products":**
- İnternet bağlantınızı kontrol edin
- `test_aliexpress_api.py` ile test edin
- API credentials'larınızı doğrulayın

### 📚 Daha Fazla Bilgi

- **API Docs:** https://developers.aliexpress.com/
- **Portals:** https://portals.aliexpress.com/
- **Test Script:** `test_aliexpress_api.py`
- **Connector Code:** `urunler/aliexpress_api.py`
- **Management Command:** `urunler/management/commands/import_aliexpress_products.py`

SONRA :

1. **CI/CD** - GitHub Actions ile otomatik deploy
2. 

## Lisans

Bu proje eğitim ve kişisel kullanım içindir.
