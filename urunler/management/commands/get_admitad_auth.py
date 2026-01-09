from django.core.management.base import BaseCommand
from urunler.admitad_client import AdmitadAPI


class Command(BaseCommand):
    help = 'Get Admitad authorization URL for user authorization'

    def handle(self, *args, **options):
        client = AdmitadAPI()
        
        auth_url = client.get_authorization_url()
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*70))
        self.stdout.write(self.style.SUCCESS('ADMITAD API AUTHORIZATION'))
        self.stdout.write(self.style.SUCCESS('='*70 + '\n'))
        
        self.stdout.write('1. Tarayıcında bu URL\'yi aç:\n')
        self.stdout.write(self.style.WARNING(f'   {auth_url}\n'))
        
        self.stdout.write('2. Admitad hesabınla giriş yap ve uygulamayı onayla\n')
        
        self.stdout.write('3. Yönlendirildiğinde URL\'deki "code=" parametresini kopyala\n')
        self.stdout.write('   Örnek: http://localhost:8000/callback?code=ABC123XYZ\n')
        self.stdout.write('   Sadece ABC123XYZ kısmını kopyala\n')
        
        self.stdout.write('\n4. Sonra şu komutu çalıştır:\n')
        self.stdout.write(self.style.SUCCESS('   python manage.py save_admitad_token <KOPYALADIGIN_CODE>\n'))
        
        self.stdout.write(self.style.SUCCESS('='*70))
