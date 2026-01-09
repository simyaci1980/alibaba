from django.core.management.base import BaseCommand
from urunler.admitad_client import AdmitadAPI


class Command(BaseCommand):
    help = 'Create Admitad deeplink for a product URL (requires campaign_id and website_id)'

    def add_arguments(self, parser):
        parser.add_argument('url', type=str, help='Product URL to convert')
        parser.add_argument('--campaign', type=int, default=6115, help='Admitad campaign ID (default: 6115 AliExpress)')
        parser.add_argument('--website', type=int, required=True, help='Admitad website ID')

    def handle(self, *args, **options):
        url = options['url']
        campaign_id = options['campaign']
        website_id = options['website']

        api = AdmitadAPI()
        deeplink, attempts = api.create_deeplink(
            url=url, campaign_id=campaign_id, website_id=website_id, debug=True
        )

        if deeplink:
            self.stdout.write(self.style.SUCCESS('\n✓ Deeplink created:'))
            self.stdout.write(self.style.SUCCESS(deeplink))
        else:
            self.stdout.write(self.style.ERROR('\n✗ Deeplink creation failed.'))
            for attempt in attempts:
                auth = attempt.get('auth', 'Unknown')
                status = attempt.get('status')
                self.stdout.write(f"- [{auth}] {attempt.get('method').upper()} {attempt.get('url')} -> {status}")
                # Show short body for quick diagnostics
                body = (attempt.get('body') or '').strip()
                if body:
                    body_preview = body[:300] + ('...' if len(body) > 300 else '')
                    self.stdout.write(f"  body: {body_preview}")
            self.stdout.write('Kontrol: access token süresi, website ID ve campaign ID doğru mu?')
