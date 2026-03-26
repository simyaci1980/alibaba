from django.core.management.base import BaseCommand, CommandError
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from urunler.models import Urun, Magaza, Fiyat


class Command(BaseCommand):
    help = "Check AliExpress product buyability by country with Playwright (TR/BR etc.)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--product-url',
            action='append',
            default=[],
            help='AliExpress product URL (repeatable)'
        )
        parser.add_argument(
            '--urun-id',
            type=int,
            action='append',
            default=[],
            help='Local Urun ID to test (repeatable)'
        )
        parser.add_argument(
            '--countries',
            type=str,
            default='TR,BR',
            help='Comma-separated country codes (default: TR,BR)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=3,
            help='If URL/ID not given, test latest N AliExpress(API) products (default: 3)'
        )
        parser.add_argument(
            '--timeout',
            type=int,
            default=30000,
            help='Per-page timeout ms (default: 30000)'
        )
        parser.add_argument(
            '--headful',
            action='store_true',
            help='Run browser in visible mode (default: headless)'
        )

    def _add_ship_to_country(self, url: str, country: str) -> str:
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query['shipToCountry'] = country
        query['gatewayAdapt'] = 'glo2tur'
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    def _collect_urls(self, options) -> list[str]:
        urls = []

        for u in options['product_url']:
            u = (u or '').strip()
            if u:
                urls.append(u)

        for urun_id in options['urun_id']:
            urun = Urun.objects.filter(id=urun_id).first()
            if urun and urun.source_url:
                urls.append(urun.source_url)

        if urls:
            return list(dict.fromkeys(urls))

        store = Magaza.objects.filter(isim='AliExpress (API)').first()
        if not store:
            return []

        limit = max(1, int(options['limit']))
        urun_ids = Fiyat.objects.filter(magaza=store).order_by('-id').values_list('urun_id', flat=True)

        seen = set()
        for uid in urun_ids:
            if uid in seen:
                continue
            seen.add(uid)
            urun = Urun.objects.filter(id=uid).first()
            if urun and urun.source_url:
                urls.append(urun.source_url)
            if len(urls) >= limit:
                break

        return urls

    def handle(self, *args, **options):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise CommandError(
                'Playwright not installed. Run: pip install playwright && python -m playwright install chromium'
            ) from exc

        country_codes = [c.strip().upper() for c in (options['countries'] or '').split(',') if c.strip()]
        if not country_codes:
            raise CommandError('No valid country codes. Example: --countries=TR,BR')

        urls = self._collect_urls(options)
        if not urls:
            raise CommandError('No product URL found. Provide --product-url or ensure AliExpress(API) products exist.')

        buy_selectors = [
            "button:has-text('Buy now')",
            "button:has-text('Buy Now')",
            "button:has-text('Satın Al')",
            "button:has-text('Comprar agora')",
            "button:has-text('Comprar ahora')",
            "button:has-text('Comprar')",
            "[role='button']:has-text('Buy now')",
            "[role='button']:has-text('Satın Al')",
            "[role='button']:has-text('Comprar agora')",
        ]

        blocked_phrases = [
            "can't be shipped",
            'cannot be shipped',
            'not available in your location',
            'item is unavailable',
            'no longer available',
            'temporarily unavailable',
            'üzgünüz',
            'bu ürün geçici olarak tedarik edilemiyor',
            'cannot be found',
        ]

        self.stdout.write(self.style.SUCCESS(f'Checking {len(urls)} URL(s) for countries: {", ".join(country_codes)}'))

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not options['headful'])
            context = browser.new_context(locale='en-US')
            page = context.new_page()
            page.set_default_timeout(options['timeout'])

            for idx, url in enumerate(urls, start=1):
                self.stdout.write(self.style.SUCCESS(f'\n[{idx}/{len(urls)}] {url}'))

                for country in country_codes:
                    test_url = self._add_ship_to_country(url, country)
                    status_label = 'UNKNOWN'
                    blocked_hits = []
                    buy_visible = False

                    try:
                        response = page.goto(test_url, wait_until='domcontentloaded')
                        status = response.status if response else 'N/A'

                        page.wait_for_timeout(1800)
                        content = page.content().lower()

                        for phrase in blocked_phrases:
                            if phrase in content:
                                blocked_hits.append(phrase)

                        for selector in buy_selectors:
                            try:
                                if page.locator(selector).first.is_visible(timeout=900):
                                    buy_visible = True
                                    break
                            except Exception:
                                continue

                        if buy_visible and not blocked_hits:
                            status_label = 'BUYABLE_LIKELY'
                        elif blocked_hits and not buy_visible:
                            status_label = 'BLOCKED_LIKELY'
                        elif buy_visible and blocked_hits:
                            status_label = 'MIXED_SIGNALS'
                        else:
                            status_label = 'UNSURE'

                        self.stdout.write(
                            f'  {country}: http={status} | result={status_label} | buy_button={buy_visible} | blocked_hits={blocked_hits[:2]}'
                        )
                    except Exception as exc:
                        self.stdout.write(self.style.ERROR(f'  {country}: ERROR {exc}'))

            context.close()
            browser.close()

        self.stdout.write(self.style.SUCCESS('\nDone.'))
