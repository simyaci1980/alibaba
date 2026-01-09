"""
AliExpress ürünlerinin affiliate_link'ini Admitad deeplink'e çevir
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'urun_karsilastirma.settings')
django.setup()

from urunler.models import Fiyat, Magaza
from urunler.utils.deeplink import build_admitad_deeplink
from decouple import config

base_link = config('ADMITAD_BASE_LINK', default='')
if not base_link:
    print("❌ ADMITAD_BASE_LINK bulunamadı!")
    exit(1)

print(f"✓ Base Link: {base_link}\n")

# AliExpress mağazasındaki tüm fiyatlar
aliexpress = Magaza.objects.get(isim='AliExpress')
fiyatlar = Fiyat.objects.filter(magaza=aliexpress)

print(f"📦 Toplam {fiyatlar.count()} AliExpress ürünü bulundu\n")

duzeltilen = 0
for fiyat in fiyatlar:
    # Eğer link zaten rzekl.com ise atla
    if 'rzekl.com' in fiyat.affiliate_link:
        print(f"⏭️  Ürün {fiyat.urun.id}: Zaten deeplink")
        continue
    
    # Direkt AliExpress linki ise deeplink'e çevir
    if 'aliexpress.com' in fiyat.affiliate_link:
        old_link = fiyat.affiliate_link[:80]
        
        # Yeni deeplink oluştur
        new_link = build_admitad_deeplink(
            base_link=base_link,
            product_url=fiyat.affiliate_link,
            subid='admin'
        )
        
        fiyat.affiliate_link = new_link
        fiyat.save()
        
        print(f"✅ Ürün {fiyat.urun.id}: {old_link}... → rzekl.com deeplink")
        duzeltilen += 1

print(f"\n{'='*60}")
print(f"✅ {duzeltilen} ürün düzeltildi!")
print(f"{'='*60}")
