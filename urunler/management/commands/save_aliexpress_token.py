import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from urunler.aliexpress_api import AliExpressAPIConnector


class Command(BaseCommand):
    help = 'AliExpress OAuth kodunu access_token ile değiş tokuş edip kaydeder'

    def add_arguments(self, parser):
        parser.add_argument(
            'code',
            type=str,
            help='Callback URL\'den alınan authorization code',
        )
        parser.add_argument(
            '--redirect-uri',
            type=str,
            default='http://localhost:8000/aliexpress/callback',
            help='Portal\'a kayıtlı redirect URI (varsayılan: http://localhost:8000/aliexpress/callback)',
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
            raise CommandError('ALIEXPRESS_APP_KEY veya ALIEXPRESS_APP_SECRET bulunamadı!')

        code = options['code']

        if options['production']:
            redirect_uri = 'https://www.kolaybulexpres.com/aliexpress/callback'
        else:
            redirect_uri = options['redirect_uri']

        self.stdout.write(f'🔄 Token exchange yapılıyor...')
        self.stdout.write(f'   Code       : {code[:20]}...')
        self.stdout.write(f'   Redirect URI: {redirect_uri}')

        connector  = AliExpressAPIConnector(app_key=app_key, app_secret=app_secret)
        token_data = connector.exchange_code_for_token(code=code, redirect_uri=redirect_uri)

        if not token_data:
            raise CommandError(
                'Token exchange başarısız!\n'
                '  • Code süresi dolmuş olabilir (genellikle 10 dakika)\n'
                '  • Redirect URI portal kayıtlısıyla eşleşmiyor olabilir\n'
                '  Yeni code almak için: python manage.py get_aliexpress_auth'
            )

        token_file = Path(settings.BASE_DIR) / 'aliexpress_token.json'
        with open(token_file, 'w', encoding='utf-8') as f:
            json.dump(token_data, f, indent=2, ensure_ascii=False)

        access_token  = token_data.get('access_token', '')
        refresh_token = token_data.get('refresh_token', '')
        expires_in    = token_data.get('expires_in', 'Bilinmiyor')

        self.stdout.write(self.style.SUCCESS(f'\n✅ Token kaydedildi: {token_file}'))
        self.stdout.write(f'   Access Token : {access_token[:20]}...')
        self.stdout.write(f'   Refresh Token: {refresh_token[:20]}...' if refresh_token else '   Refresh Token: -')
        self.stdout.write(f'   Expires In   : {expires_in} saniye')
        self.stdout.write('\nAdvanced API testi için:')
        self.stdout.write(self.style.SUCCESS('   python test_advanced_api.py'))
