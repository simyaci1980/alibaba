
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import django
import csv

# Django ayarlarını yükle
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'urun_karsilastirma.settings')
django.setup()

from urunler.models import Urun

# Çıktı dosyası yolu
csv_path = os.path.join(os.path.dirname(__file__), 'urunler_export.csv')

# Ürünleri çek
urunler = Urun.objects.all()

# CSV'ye yaz
with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
    writer = csv.writer(csvfile)
    # Başlık satırı
    writer.writerow(['isim', 'aciklama', 'resim', 'resim_url', 'urun_kodu', 'urun_url', 'affiliate_link'])
    for urun in urunler:
        # Ürün detay URL'si (örnek: /urunler/{urun.id}/)
        urun_url = f"/urunler/{urun.id}/"
        # İlk fiyat kaydının affiliate_link'i (varsa)
        affiliate_link = ''
        fiyat = urun.fiyatlar.first()
        if fiyat:
            affiliate_link = fiyat.affiliate_link
        writer.writerow([
            urun.isim,
            urun.aciklama,
            urun.resim.url if urun.resim else '',
            urun.resim_url or '',
            urun.urun_kodu or '',
            urun_url,
            affiliate_link
        ])

print(f"{urunler.count()} ürün başarıyla {csv_path} dosyasına yazıldı.")
