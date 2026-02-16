"""
Veritabanındaki ürünlerin isimlerini Türkçeye çeviren Django management command
"""
from django.core.management.base import BaseCommand
from urunler.models import Urun
from deep_translator import GoogleTranslator
import time

class Command(BaseCommand):
    help = 'Ürün isimlerini Türkçeye çevirir'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Çevrilecek maksimum ürün sayısı'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Zaten Türkçe olanları da yeniden çevir'
        )

    def handle(self, *args, **options):
        limit = options['limit']
        force = options['force']
        
        translator = GoogleTranslator(source='auto', target='tr')
        
        # Çevrilecek ürünleri al
        urunler = Urun.objects.all()
        
        if limit:
            urunler = urunler[:limit]
        
        total = urunler.count()
        self.stdout.write(f"🚀 Toplam {total} ürün bulundu\n")
        
        translated = 0
        skipped = 0
        errors = 0
        
        for i, urun in enumerate(urunler, 1):
            try:
                original_name = urun.isim
                
                # Zaten Türkçe mi kontrol et (basit: Türkçe karakter var mı?)
                has_turkish = any(c in original_name for c in 'çğıöşüÇĞİÖŞÜ')
                
                if has_turkish and not force:
                    self.stdout.write(f"{i}/{total} ⏭️  Atlandı (zaten Türkçe): {original_name[:50]}...")
                    skipped += 1
                    continue
                
                # Çevir
                if len(original_name) > 500:
                    original_name = original_name[:500]
                
                translated_name = translator.translate(original_name)
                
                # Güncelle
                urun.isim = translated_name
                urun.save()
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{i}/{total} ✅ {original_name[:40]}... → {translated_name[:40]}..."
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
