"""
Ürün açıklamalarındaki kategorileri Türkçeye çeviren Django management command
"""
from django.core.management.base import BaseCommand
from urunler.models import Urun
from deep_translator import GoogleTranslator
import time
import re

class Command(BaseCommand):
    help = 'Ürün açıklamalarındaki kategorileri Türkçeye çevirir'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Çevrilecek maksimum ürün sayısı'
        )

    def handle(self, *args, **options):
        limit = options['limit']
        
        translator = GoogleTranslator(source='auto', target='tr')
        
        # "Kategori: " içeren ürünleri al
        urunler = Urun.objects.filter(aciklama__contains='Kategori:')
        
        if limit:
            urunler = urunler[:limit]
        
        total = urunler.count()
        self.stdout.write(f"🚀 Toplam {total} ürün bulundu\n")
        
        translated = 0
        skipped = 0
        errors = 0
        
        for i, urun in enumerate(urunler, 1):
            try:
                aciklama = urun.aciklama
                
                # "Kategori: XYZ" formatını bul
                match = re.search(r'Kategori:\s*(.+)', aciklama)
                
                if not match:
                    skipped += 1
                    continue
                
                kategori = match.group(1).strip()
                
                # Zaten Türkçe mi?
                has_turkish = any(c in kategori for c in 'çğıöşüÇĞİÖŞÜ')
                
                if has_turkish:
                    self.stdout.write(f"{i}/{total} ⏭️  Atlandı (zaten Türkçe): {kategori[:40]}...")
                    skipped += 1
                    continue
                
                # Çevir
                if len(kategori) > 200:
                    kategori = kategori[:200]
                
                turkce_kategori = translator.translate(kategori)
                
                # Açıklamayı güncelle
                yeni_aciklama = re.sub(
                    r'Kategori:\s*(.+)',
                    f'Kategori: {turkce_kategori}',
                    aciklama
                )
                
                urun.aciklama = yeni_aciklama
                urun.save()
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{i}/{total} ✅ {kategori[:30]}... → {turkce_kategori[:30]}..."
                    )
                )
                translated += 1
                
                # Rate limit için bekleme
                if i % 10 == 0:
                    time.sleep(0.5)
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"{i}/{total} ❌ Hata: {e}")
                )
                errors += 1
                time.sleep(2)
        
        # Özet
        self.stdout.write("\n" + "="*50)
        self.stdout.write(self.style.SUCCESS(f"\n✅ Çevrilen: {translated}"))
        self.stdout.write(f"⏭️  Atlanan: {skipped}")
        self.stdout.write(f"❌ Hata: {errors}")
        self.stdout.write(f"📦 Toplam: {total}\n")
