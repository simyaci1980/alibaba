from django.core.management.base import BaseCommand
from urunler.admitad_client import AdmitadAPI
import json
import os
from django.conf import settings
import requests
import base64
from requests.auth import HTTPBasicAuth


class Command(BaseCommand):
    help = 'Save Admitad access token after authorization'

    def add_arguments(self, parser):
        parser.add_argument('code', type=str, help='Authorization code from callback URL')

    def handle(self, *args, **options):
        code = options['code']
        
        self.stdout.write('Authorization code alındı, token alınıyor...\n')
        
        # Read OAuth application credentials from environment
        from decouple import config
        client_id = config('ADMITAD_CLIENT_ID', default='')
        client_secret = config('ADMITAD_CLIENT_SECRET', default='')

        if not client_id or not client_secret:
            self.stdout.write(self.style.ERROR('ADMITAD_CLIENT_ID/ADMITAD_CLIENT_SECRET bulunamadı.'))
            self.stdout.write('Lütfen Admitad OAuth Uygulaması oluşturup client_id ve client_secret değerlerini .env dosyasına ekleyin.')
            self.stdout.write('Redirect URI: http://localhost:8000/callback ve scope: public_data statistics websites advcampaigns coupons deeplink')
            return
        
        self.stdout.write(f'Client ID: {client_id}')
        self.stdout.write(f'Client Secret: {client_secret[:10]}...')
        
        try:
            # Prefer HTTPBasicAuth to avoid header formatting issues
            self.stdout.write('HTTPBasicAuth ile istek hazırlanıyor')

            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
            }

            data = {
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': 'http://localhost:8000/callback',
                # Some OAuth servers accept client_id/secret in body; include as fallback
                'client_id': client_id,
                'client_secret': client_secret,
            }

            self.stdout.write('Token isteği gönderiliyor...')
            response = requests.post(
                'https://api.admitad.com/token/',
                headers=headers,
                data=data,
                auth=HTTPBasicAuth(client_id, client_secret),
            )
            self.stdout.write(f'Yanıt alındı: {response.status_code}')
            response.raise_for_status()
            token_data = response.json()
            token = token_data.get('access_token')
            
            if token:
                self.stdout.write(self.style.SUCCESS(f'\n✓ Access token başarıyla alındı!\n'))
                self.stdout.write(f'Token: {token[:30]}...\n')
                
                # Token'ı dosyaya kaydet
                token_file = os.path.join(settings.BASE_DIR, 'admitad_token.json')
                with open(token_file, 'w') as f:
                    json.dump(token_data, f)
                
                self.stdout.write(self.style.SUCCESS(f'\n✓ Token kaydedildi: {token_file}\n'))
                self.stdout.write('\nŞimdi ürünleri çekebilirsin:\n')
                self.stdout.write(self.style.SUCCESS('   python manage.py fetch_aliexpress_products\n'))
            else:
                self.stdout.write(self.style.ERROR('\n✗ Token response\'da bulunamadı\n'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n✗ Token alınamadı: {e}\n'))
            if hasattr(e, 'response') and e.response is not None:
                self.stdout.write(f'Response: {e.response.text}\n')
            self.stdout.write('Tekrar dene: python manage.py get_admitad_auth\n')
