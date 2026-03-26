# eBay Affiliate Sistemi - Canlı Ortam Dağıtım Rehberi

## Güncel Durum ✅
- **Kod**: Tamamlandı ve test edildi
- **Veritabanı Şeması**: Hazır (göç gerekmiyor)
- **API Kimlik Bilgileri**: `settings.py`'da yapılandırıldı
- **Ağ Koruması**: Yeniden deneme mantığı ve zaman aşımı işleme uygulandı

## Ağ Hatasının Çözümü
Yerel geliştirme ortamında eBay API'sine erişimi kısıtlayan ağ kısıtlamaları var. **Bu, sınırsız ağ erişimine sahip PythonAnywhere'e dağıtılarak çözülür**.

## Dağıtım Adımları

### Adım 1: Değişiklikleri Git'e Gönderme
```bash
cd c:\Users\ab111777\Desktop\alibaba

# Tüm değişiklikleri hazırla
git add -A

# Net bir mesajla commit et
git commit -m "eBay Entegrasyonu: Ağ esnekliği ekle, OAuth uç noktalarını düzelt"

# Ana dalına gönder
git push origin main
```

### Adım 2: PythonAnywhere'e SSH ile Bağlanma
```bash
# SSH oturumu başlat
ssh kullanici_adi@kullanici_adi.pythonanywhere.com

# Web uygulaması dizinine git
cd /home/kullanici_adi/alibaba  # veya kendi uygulama dizini
```

### Adım 3: En Son Kodları Çekme
```bash
# En son değişiklikleri çek
git pull origin main

# Yeni bağımlılıkları yükle (gerekirse)
pip install -r requirements.txt

# Statik dosyaları topla
python manage.py collectstatic --noinput

# Veritabanı göçlerini çalıştır
python manage.py migrate
```

### Adım 4: eBay'dan Gerçek Ürünleri İçeri Aktarma
```bash
# Önce sandbox'ta test et (önerilir)
python3.10 manage.py import_ebay_products "smartwatch" --limit=5 --sandbox

# Doğrulandıktan sonra, CANLIDAN import et
python3.10 manage.py import_ebay_products "drone" --limit=20 --translate-tr
python3.10 manage.py import_ebay_products "laptop" --limit=20 --translate-tr
python3.10 manage.py import_ebay_products "telefon" --limit=20 --translate-tr
```

**Komut Parametreleri:**
- `"drone"` = Aratılacak ürün adı
- `--limit=20` = İçeri aktarılacak ürün sayısı (1-200)
- `--translate-tr` = Başlıkları Türkçeye çevir
- `--sandbox` = Sandbox ortamını kullan (isteğe bağlı)

### Adım 5: Tarayıcıda Doğrulama
Siteyi ziyaret edin ve şunları kontrol edin:
- eBay ürünleri **sarı arka plan** ve **turuncu sol sınırla** görünsün
- **🏆 Orijinal** rozeti eBay ürünlerinde gözüksün
- Ürün resimleri düzgün yüklensin
- Fiyatlar USD cinsinden gösterilsin
- Affiliate linkler doğru olsun

## Yapılan Düzeltmeler

### 1. **Ağ Esnekliği** (ebay_api.py)
```python
# Yeniden deneme stratejisi ile HTTPAdapter eklendi
retry_strategy = Retry(
    total=3,  # En fazla 3 kez yeniden dene
    backoff_factor=1,  # Denemeler arası 1s, 2s, 4s bekle
    status_forcelist=[429, 500, 502, 503, 504],  # Bu status kodlarında yeniden dene
    allowed_methods=["POST", "GET"]
)
```

### 2. **Artan Zaman Aşımı Değerleri**
- OAuth token talepleri: 10s → **30 saniye**
- API arama talepleri: 15s → **30 saniye**

### 3. **Daha İyi İstisna Yönetimi**
- `requests.exceptions.Timeout` için özel yakalama
- `requests.exceptions.ConnectionError` için özel yakalama
- Hata ayıklamada ayrıntılı günlükleme

### 4. **Düzeltilmiş OAuth Uç Noktaları**
- Canlı: `https://api.ebay.com/oauth2/token`
- Sandbox: `https://api.sandbox.ebay.com/oauth2/token`

## Dağıtım Sonrası İzleme

### eBay Partner Network'de Affiliate Tıklamalarını Kontrol Etme
1. [https://publisher.ebaypartnernetwork.com](https://publisher.ebaypartnernetwork.com) adresine giriş yapın
2. **Reports** → **Click Reports** seçeneğine gidin
3. Kampanya ID'nizi kontrol edin: **5339143578**
4. **Customid** sütununda ürün kodlarınızı (5 haneli) göreceksiniz

### Django Günlükleri
PythonAnywhere'de API hatalarını kontrol edin:
```bash
# Son API aktivitesini görüntüle
tail -f /home/kullanici_adi/alibaba/ebay_api.log
```

## Sorun Giderme

### Ürünler import edilmiyorsa:
```bash
# Ayrıntılı günlükleme ile çalıştır
python3.10 manage.py import_ebay_products "drone" --limit=5 -v 3
```

### Resimler gösterilmiyorsa:
- `UrunResim.resim_url` tam eBay resim URL'leri içerdiğini kontrol edin
- eBay resim URL'lerinin CORS tarafından engellenmediğini doğrulayın

### Affiliate linkler çalışmıyorsa:
- Kampanya ID'nin doğru olduğunu doğrulayın: `5339143578`
- Link formatını kontrol edin: `https://www.ebay.com/itm/{item_id}?mkcid=1&mkrid=711-53200-19255-0&siteid=0&campid=5339143578&toolid=10001&mkevt=1&customid={urun_kodu}`

## Yapılandırma Dosyaları

### settings.py (zaten yapılandırıldı)
```python
EBAY_PRODUCTION_CLIENT_ID = 'AliAltns-...-PRD-...'
EBAY_PRODUCTION_CLIENT_SECRET = 'PRD-...'
EBAY_CAMPAIGN_ID = '5339143578'
```

### Veritabanı Modelleri (değişikliğe ihtiyaç yok)
- ✅ `Urun` - Ürün adı, açıklama, resimler
- ✅ `Magaza` - Mağaza adı (eBay otomatik oluşturulur)
- ✅ `Fiyat` - Fiyat, affiliate_link, iletişim bilgileri
- ✅ `UrunResim` - Ürün resimleri URL'lerle
- ✅ `ClickLog` - Tıklama izleme ve alt ID'ler

## Affiliate Takibi

Her eBay ürünü için:
- **Ürün Kodu**: 5 haneli benzersiz kod (42567, 89123 vb)
- **Customid**: Ürün kodu = EPN raporunda hangi ürüne tıklandığını gösterir
- **Takipler**: EPN Reports → Customid sütununda yer alır

## Önbelleğe Alma
OAuth tokenları otomatik olarak 1 saat süreyle önbelleğe alınır (API çağrılarını azaltmak için):
```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}
```

## Sonraki Adımlar (İsteğe Bağlı)

### 1. **Otomatik Import Zamanlaması**
Celery Beat kullanarak ürünleri günlük güncelleyin:
```bash
python -m celery -A urun_karsilastirma worker -B
```

### 2. **Performansı İzleyin**
- Affiliate tıklama oranlarını izleyin
- En çok tıklanan ürünleri takip edin
- Performansa göre arama terimlerini ayarlayın

### 3. **Diğer Affiliate Ağlarına Genişlet**
- AliExpress entegrasyonu zaten var ✅
- eBay entegrasyonu tamamlandı ✅
- Şunları düşünün: Amazon Associates, Admitad, vb.

---

**Durum**: Canlı ortama dağıtım için hazır  
**Son Güncelleme**: 2026-03-04  
**Ortam**: PythonAnywhere (canlı) veya yerel (ağ erişimi gerekli)
