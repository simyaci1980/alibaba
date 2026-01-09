import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'urun_karsilastirma.settings')
django.setup()

from urunler.models import Urun, Fiyat, ClickLog
from django.db.models import Count

print("=" * 60)
print("📊 PROJE DURUM RAPORU")
print("=" * 60)

# Ürün sayısı
urun_count = Urun.objects.count()
print(f"\n📦 Ürün Sayısı: {urun_count}")

# Fiyat sayısı
fiyat_count = Fiyat.objects.count()
print(f"💰 Fiyat Kaydı: {fiyat_count}")

# Tıklama istatistikleri
click_count = ClickLog.objects.count()
print(f"🖱️  Toplam Tıklama: {click_count}")

# Tıklama türlerine göre
click_types = ClickLog.objects.values('link_type').annotate(count=Count('id'))
print("\n📈 Tıklama Türleri:")
for ct in click_types:
    print(f"   - {ct['link_type']}: {ct['count']}")

# Son eklenen ürün
latest_urun = Urun.objects.order_by('-id').first()
if latest_urun:
    print(f"\n🆕 Son Eklenen Ürün: {latest_urun.isim}")

# Vergi çarpanı bilgisi
print(f"\n🧮 Vergi Çarpanı: 1.65 (Gümrük + KDV)")

print(f"\n💾 Veritabanı: db.sqlite3")

print("\n" + "=" * 60)
