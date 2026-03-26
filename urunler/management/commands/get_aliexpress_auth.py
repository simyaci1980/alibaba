from django.core.management.base import BaseCommand
from django.conf import settings
from urunler.aliexpress_api import AliExpressAPIConnector


class Command(BaseCommand):
    help = 'AliExpress Advanced API için OAuth yetkilendirme URL\'i oluştur'

    def add_arguments(self, parser):
        parser.add_argument(
            '--redirect-uri',
            type=str,
            default='http://localhost:8000/aliexpress/callback',
            help='AliExpress portal\'a kayıtlı callback URL (varsayılan: http://localhost:8000/aliexpress/callback)',
        )
        parser.add_argument(
            '--production',
            action='store_true',
            help='Canlı site redirect URI kullan (kolaybulexpres.com)',
        )

    def handle(self, *args, **options):
        app_key    = getattr(settings, 'ALIEXPRESS_APP_KEY', '')
        app_secret = getattr(settings, 'ALIEXPRESS_APP_SECRET', '')

        if not app_key or not app_secret:
            self.stdout.write(self.style.ERROR(
                '❌ ALIEXPRESS_APP_KEY veya ALIEXPRESS_APP_SECRET .env dosyasında tanımlı değil!'
            ))
            return

        if options['production']:
            redirect_uri = 'https://www.kolaybulexpres.com/aliexpress/callback'
        else:
            redirect_uri = options['redirect_uri']

        connector = AliExpressAPIConnector(app_key=app_key, app_secret=app_secret)
        auth_url  = connector.get_authorize_url(redirect_uri=redirect_uri)

        self.stdout.write(self.style.SUCCESS('\n' + '=' * 70))
        self.stdout.write(self.style.SUCCESS('ALİEXPRESS ADVANCED API OAUTH YETKİLENDİRME'))
        self.stdout.write(self.style.SUCCESS('=' * 70 + '\n'))

        self.stdout.write('1. Tarayıcında bu URL\'yi aç:\n')
        self.stdout.write(self.style.WARNING(f'   {auth_url}\n'))

        self.stdout.write('2. AliExpress hesabınla giriş yap ve uygulamayı onayla\n')

        self.stdout.write('3. Yönlendirildiğinde URL\'deki "code=" parametresini kopyala:\n')
        self.stdout.write(f'   Örnek: {redirect_uri}?code=ABC123XYZ&state=...\n')
        self.stdout.write('   Sadece ABC123XYZ kısmını kopyala\n')

        self.stdout.write('\n4a. Uygulamanı çalıştırıyorsan callback otomatik token kaydeder.\n')
        self.stdout.write('4b. Manuel kaydetmek için:\n')
        self.stdout.write(self.style.SUCCESS('    python manage.py save_aliexpress_token <CODE>\n'))

        self.stdout.write(f'\n📌 Redirect URI (portal\'a kayıtlı olmalı): {redirect_uri}')
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 70))
