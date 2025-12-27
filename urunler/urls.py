
from django.urls import path
from . import views

urlpatterns = [
    path('', views.anasayfa, name='anasayfa'),
    path('urunler/', views.urun_listesi, name='urun_listesi'),
    path('amazon-redirect/', views.amazon_redirect, name='amazon_redirect'),
    path('aliexpress-redirect/', views.aliexpress_redirect, name='aliexpress_redirect'),
    path('urun-affiliate-redirect/<int:urun_id>/', views.urun_affiliate_redirect, name='urun_affiliate_redirect'),
]
