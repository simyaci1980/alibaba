from django.contrib.sitemaps import Sitemap
from django.conf import settings
from django.urls import reverse
from urllib.parse import urlparse
from .models import Urun


class BaseSitemap(Sitemap):
    """Always emit sitemap URLs using configured canonical base URL."""

    def get_urls(self, page=1, site=None, protocol=None):
        base_url = str(getattr(settings, 'SITE_BASE_URL', '')).strip()
        if base_url:
            parsed = urlparse(base_url)
            forced_domain = parsed.netloc
            forced_protocol = parsed.scheme or 'https'
            if forced_domain:
                site = type('SiteObj', (), {'domain': forced_domain, 'name': forced_domain})()
                protocol = forced_protocol

        return super().get_urls(page=page, site=site, protocol=protocol)


class StaticViewSitemap(BaseSitemap):
    priority = 1.0
    changefreq = 'daily'
    protocol = 'https'

    def items(self):
        return ['anasayfa', 'urun_listesi']

    def location(self, item):
        return reverse(item)


class UrunSitemap(BaseSitemap):
    priority = 0.8
    changefreq = 'daily'
    protocol = 'https'

    def items(self):
        return Urun.objects.exclude(durum__iexact='Pasif').filter(slug__isnull=False).exclude(slug='').order_by('-id')

    def location(self, item):
        return reverse('urun_detay', kwargs={'slug': item.slug})
