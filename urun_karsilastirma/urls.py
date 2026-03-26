"""
URL configuration for urun_karsilastirma project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from urunler.sitemaps import StaticViewSitemap, UrunSitemap
from urunler.views import aliexpress_callback_view

sitemaps = {
    'static': StaticViewSitemap,
    'urunler': UrunSitemap,
}

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('urunler.urls')),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path('favicon.ico', RedirectView.as_view(url='/static/urunler/favicon.ico', permanent=True)),
    path('robots.txt', RedirectView.as_view(url='/static/robots.txt', permanent=True)),
    path('aliexpress/callback', aliexpress_callback_view, name='aliexpress_callback'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
