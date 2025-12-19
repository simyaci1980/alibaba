from django.urls import path
from . import views

urlpatterns = [
    path('', views.anasayfa, name='anasayfa'),
    path('urunler/', views.urun_listesi, name='urun_listesi'),
]
