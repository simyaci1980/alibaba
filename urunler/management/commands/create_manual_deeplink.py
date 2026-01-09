from django.core.management.base import BaseCommand
from decouple import config
from urunler.utils.deeplink import build_admitad_deeplink


class Command(BaseCommand):
    help = 'Create deeplink using a known Admitad base affiliate link (no API call)'

    def add_arguments(self, parser):
        parser.add_argument('url', type=str, help='Product URL to convert')
        parser.add_argument('--subid', type=str, default=None, help='Optional subid for tracking')
        parser.add_argument('--base', type=str, default=None, help='Base affiliate link (overrides env ADMITAD_BASE_LINK)')

    def handle(self, *args, **options):
        product_url = options['url']
        subid = options['subid']
        base_link = options['base'] or config('ADMITAD_BASE_LINK', default='')

        if not base_link:
            self.stdout.write(self.style.ERROR('ADMITAD_BASE_LINK is missing. Provide --base or set in .env'))
            return

        try:
            deeplink = build_admitad_deeplink(base_link=base_link, product_url=product_url, subid=subid)
            self.stdout.write(self.style.SUCCESS('\n✓ Deeplink created:'))
            self.stdout.write(self.style.SUCCESS(deeplink))
        except Exception as e:
            self.stdout.write(self.style.ERROR('\n✗ Failed to build deeplink'))
            self.stdout.write(str(e))
