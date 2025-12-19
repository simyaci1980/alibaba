# Ürün Karşılaştırma Platformu (Django)

Bu proje, farklı mağazalardaki ürünlerin fiyatlarını karşılaştırabileceğiniz ve affiliate linklerle gelir elde edebileceğiniz bir Django tabanlı web uygulamasıdır.

## Özellikler
- Ürün ekleme, mağaza ekleme
- Her ürün için birden fazla mağazadan fiyat ve affiliate linki ekleyebilme
- Ana sayfada ürünlerin ve mağazalara göre fiyatlarının listelenmesi
- Responsive ve modern arayüz
- Medya (resim) ve statik dosya yönetimi

## Kurulum
1. Gerekli paketleri yükleyin:
   ```bash
   pip install -r requirements.txt
   ```
2. Veritabanı migrasyonlarını çalıştırın:
   ```bash
   python manage.py migrate
   ```
3. Yönetici hesabı oluşturun:
   ```bash
   python manage.py createsuperuser
   ```
4. Geliştirme sunucusunu başlatın:
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

## Notlar
- Affiliate linklerinizi mağaza eklerken veya fiyat eklerken ilgili alana girin.
- Geliştirme ortamında medya dosyalarını sunmak için ayarlar yapılmıştır.

## Lisans
Bu proje eğitim ve kişisel kullanım içindir.
