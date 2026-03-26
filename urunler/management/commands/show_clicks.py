from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from urunler.models import ClickLog
from django.db.models import Count, Q


class Command(BaseCommand):
    help = 'Gerçek zamanlı tıklama raporunu göster'

    def add_arguments(self, parser):
        parser.add_argument(
            '--minutes',
            type=int,
            default=60,
            help='Son X dakikalık tıklamaları göster (default: 60)'
        )
        parser.add_argument(
            '--channel',
            type=str,
            choices=['aliexpress', 'ebay', 'amazon', 'all'],
            default='all',
            help='Hangi kanalı filtrele'
        )
        parser.add_argument(
            '--watch',
            action='store_true',
            help='Sürekli izle (her 5 saniye yenile)'
        )

    def handle(self, *args, **options):
        minutes = options['minutes']
        channel = options['channel']
        watch = options['watch']

        def show_report():
            now = timezone.now()
            start_time = now - timedelta(minutes=minutes)

            # Filter by time
            clicks = ClickLog.objects.filter(timestamp__gte=start_time)

            # Filter by channel
            if channel != 'all':
                clicks = clicks.filter(link_type__contains=channel)

            # Statistics
            total = clicks.count()
            
            self.stdout.write(self.style.SUCCESS(f'\n{"─" * 70}'))
            self.stdout.write(self.style.SUCCESS(f'📊 TIKLAMA RAPORU - Son {minutes} dakika'))
            self.stdout.write(self.style.SUCCESS(f'{"─" * 70}'))
            self.stdout.write(f'⏱️  Tarih: {now:%H:%M:%S} | 📈 Toplam Tıklama: {total}')
            self.stdout.write(f'{"─" * 70}\n')

            if total == 0:
                self.stdout.write(self.style.WARNING('❌ Bu dönemde tıklama yok'))
                return

            # By channel
            by_channel = clicks.values('link_type').annotate(count=Count('id')).order_by('-count')
            
            self.stdout.write(self.style.SUCCESS('📍 Kanallara Göre:'))
            for item in by_channel:
                channel_name = item['link_type'].upper()
                count = item['count']
                emoji = '🖇️' if 'aliexpress' in item['link_type'] else '🛒' if 'ebay' in item['link_type'] else '🔗'
                self.stdout.write(f"  {emoji} {channel_name}: {count} tıklama")
            
            self.stdout.write()

            # By product (if any)
            by_product = clicks.filter(urun__isnull=False).values('urun__isim').annotate(count=Count('id')).order_by('-count')[:5]
            
            if by_product:
                self.stdout.write(self.style.SUCCESS('🎁 En Çok Tıklanan Ürünler:'))
                for i, item in enumerate(by_product, 1):
                    self.stdout.write(f"  {i}. {item['urun__isim'][:50]} - {item['count']} tıklama")
                self.stdout.write()

            # Recent clicks
            recent = clicks.select_related('urun', 'user').order_by('-timestamp')[:5]
            
            self.stdout.write(self.style.SUCCESS('⚡ Son Tıklamalar:'))
            for click in recent:
                user_info = click.user.username if click.user else 'Anonim'
                urun_info = f" ({click.urun.isim[:30]})" if click.urun else ""
                time_diff = (now - click.timestamp).total_seconds()
                
                if time_diff < 60:
                    time_str = f'{int(time_diff)}s önce'
                elif time_diff < 3600:
                    time_str = f'{int(time_diff/60)}m önce'
                else:
                    time_str = f'{int(time_diff/3600)}h önce'
                
                self.stdout.write(f"  ✓ {click.link_type.upper()} {urun_info} - {time_str}")
            
            self.stdout.write(self.style.SUCCESS(f'\n{"─" * 70}\n'))

        if watch:
            import time
            try:
                while True:
                    show_report()
                    print("⏳ 5 saniye içinde yenileniyor... (Çıkmak için CTRL+C)")
                    time.sleep(5)
            except KeyboardInterrupt:
                self.stdout.write(self.style.SUCCESS('\n✓ İzleme durduruldu'))
        else:
            show_report()
