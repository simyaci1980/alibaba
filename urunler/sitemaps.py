from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from .models import Urun


class StaticViewSitemap(Sitemap):
    priority = 1.0
    changefreq = 'daily'
    protocol = 'https'

    def items(self):
        return ['anasayfa', 'urun_listesi']

    def location(self, item):
        return reverse(item)


class UrunSitemap(Sitemap):
    priority = 0.8
    changefreq = 'daily'
    protocol = 'https'

    def items(self):
        return Urun.objects.filter(slug__isnull=False).exclude(slug='').order_by('-id')

    def location(self, item):
        return reverse('urun_detay', kwargs={'slug': item.slug})
