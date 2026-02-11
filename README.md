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

## SQLite3 Veritabanını GitHub'a Aktarma

Projede ürünleri veya veritabanı içeriğini doğrudan paylaşmak için db.sqlite3 dosyasını GitHub'a gönderebilirsiniz. Aşağıdaki adımları izleyin:

1. db.sqlite3 dosyanızda değişiklik yaptıysanız (ör. yeni ürün eklediniz), dosyanın güncel olduğundan emin olun.
2. Terminalde şu komutları çalıştırın:
   ```bash
   git add db.sqlite3
   git commit -m "Güncel veritabanı eklendi"
   git push
   ```
3. GitHub'da db.sqlite3 dosyanız güncel olarak saklanacaktır. Sunucuya (ör. PythonAnywhere) aktarmak için orada da `git pull` komutunu kullanın.

> Not: db.sqlite3 dosyasını paylaşmak, tüm veritabanı içeriğini (kullanıcılar, ürünler, vs.) herkese açık hale getirir. Gizli veri varsa dikkatli olun.

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

SONRA :

1. **CI/CD** - GitHub Actions ile otomatik deploy
2. 

## Lisans

Bu proje eğitim ve kişisel kullanım içindir.
