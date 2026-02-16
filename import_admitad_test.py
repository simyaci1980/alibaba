"""
Admitad CSV'sinden ilk N ürünü veritabanına ekleyen script
"""
import csv
import django
import os
import sys
import random
import string

# Django setup
sys.path.append('c:/Users/ab111777/Desktop/alibaba')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'urun_karsilastirma.settings')
django.setup()

from urunler.models import Urun, Magaza, Fiyat

def generate_unique_code(length=5):
    """Benzersiz ürün kodu üret"""
    while True:
        code = ''.join(random.choices(string.digits, k=length))
        if not Urun.objects.filter(urun_kodu=code).exists():
            return code

def import_admitad_products(csv_file, max_products=20):
    """
    Admitad CSV'sinden ürünleri import et
    """
    # AliExpress mağazasını oluştur
    magaza, _ = Magaza.objects.get_or_create(
        isim='AliExpress',
        defaults={'web_adresi': 'https://www.aliexpress.com'}
    )
    
    added = 0
    updated = 0
    skipped = 0
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        
        for row in reader:
            if added + updated >= max_products:
                print(f"\n✓ {max_products} ürün işlendi. Durduruluyor.")
                break
            
            try:
                # Alanları al
                product_id = row.get('id', '')
                name = row.get('name', '')
                affiliate_url = row.get('url', '')
                category = row.get('category', '')
                currency = row.get('currencyId', 'USD')
                picture_url = row.get('picture', '')
                old_price = row.get('oldprice', '')
                price = row.get('price', '')
                
                # Boş kontrol
                if not name or not price:
                    skipped += 1
                    continue
                
                # Fiyatı float'a çevir
                try:
                    price_float = float(price)
                except:
                    skipped += 1
                    continue
                
                # Ürünü kontrol et (source_url'e göre)
                urun = None
                if affiliate_url:
                    # URL'den gerçek AliExpress URL'ini çıkar
                    source_url = None
                    if 'aliexpress.com/item/' in affiliate_url:
                        # URL decode et
                        import urllib.parse
                        decoded = urllib.parse.unquote(affiliate_url)
                        if 'ulp=' in decoded:
                            ulp_part = decoded.split('ulp=')[1]
                            if '&' in ulp_part:
                                ulp_part = ulp_part.split('&')[0]
                            if 'aliexpress.com/item/' in ulp_part:
                                # Item ID'yi çıkar
                                item_id = ulp_part.split('/item/')[1].split('.html')[0] if '.html' in ulp_part else ulp_part.split('/item/')[1].split('?')[0]
                                source_url = f"https://www.aliexpress.com/item/{item_id}.html"
                    
                    if source_url:
                        urun = Urun.objects.filter(source_url=source_url).first()
                
                # İsme göre kontrol
                if not urun:
                    urun = Urun.objects.filter(isim__iexact=name).first()
                
                if urun:
                    # Güncelle
                    urun.isim = name
                    urun.aciklama = f"Kategori: {category}"
                    urun.resim_url = picture_url or urun.resim_url
                    if not urun.urun_kodu:
                        urun.urun_kodu = generate_unique_code()
                    urun.save()
                    
                    # Fiyatı güncelle
                    Fiyat.objects.update_or_create(
                        urun=urun,
                        magaza=magaza,
                        defaults={
                            'fiyat': round(price_float, 2),
                            'para_birimi': currency,
                            'affiliate_link': affiliate_url,
                            'gonderim_ucreti': 0,
                            'gonderim_yerinden': 'Çin',
                            'gonderim_durumu': True
                        }
                    )
                    
                    updated += 1
                    print(f"🔄 Güncellendi: {name[:50]}... ({price_float} {currency})")
                else:
                    # Yeni ürün oluştur
                    urun_kodu = generate_unique_code()
                    urun = Urun.objects.create(
                        isim=name,
                        aciklama=f"Kategori: {category}",
                        resim_url=picture_url,
                        source_url=source_url if source_url else None,
                        urun_kodu=urun_kodu
                    )
                    
                    # Fiyat ekle
                    Fiyat.objects.create(
                        urun=urun,
                        magaza=magaza,
                        fiyat=round(price_float, 2),
                        para_birimi=currency,
                        affiliate_link=affiliate_url,
                        gonderim_ucreti=0,
                        gonderim_yerinden='Çin',
                        gonderim_durumu=True
                    )
                    
                    added += 1
                    print(f"✅ Eklendi: {name[:50]}... ({price_float} {currency})")
                    
            except Exception as e:
                print(f"❌ Hata: {e}")
                skipped += 1
    
    print(f"\n📊 Özet:")
    print(f"  ✅ Eklenen: {added}")
    print(f"  🔄 Güncellenen: {updated}")
    print(f"  ⏭️  Atlanan: {skipped}")
    print(f"  📦 Toplam: {added + updated}")

if __name__ == "__main__":
    csv_file = r"c:\Users\ab111777\Desktop\alibaba\Aliexpress WW Basic.2026-02-12 (1).csv"
    
    print("🚀 İlk 20 ürün ekleniyor...")
    print(f"📥 Kaynak: {csv_file}\n")
    
    import_admitad_products(csv_file, max_products=20)
    
    print("\n✅ Tamamlandı!")
    print("🌐 Siteyi kontrol edin: http://127.0.0.1:8000/")
