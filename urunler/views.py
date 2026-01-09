from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Q, Case, When, IntegerField
from .models import Urun, ClickLog, Yorum
from .forms import YorumForm





def anasayfa(request):
	"""Ana sayfa - ürün listesi ve yorumlar"""
	search_query = request.GET.get('q', '').strip()
	
	if search_query:
		# Arama yapılıyorsa - ürün ismine göre filtrele
		urunler = Urun.objects.prefetch_related('fiyatlar__magaza').filter(
			Q(isim__icontains=search_query) | Q(aciklama__icontains=search_query)
		).annotate(
			# Tam eşleşme öncelikli sıralama
			relevance=Case(
				When(isim__iexact=search_query, then=1),
				When(isim__istartswith=search_query, then=2),
				When(isim__icontains=search_query, then=3),
				default=4,
				output_field=IntegerField()
			)
		).order_by('relevance', 'isim')
	else:
		# Arama yoksa tüm ürünleri göster
		urunler = Urun.objects.prefetch_related('fiyatlar__magaza').all()
	
	yorumlar = Yorum.objects.filter(onayli=True).order_by('-eklenme_tarihi')[:10]
	form = YorumForm(request.POST or None)
	if request.method == 'POST' and form.is_valid():
		form.save()
		form = YorumForm()
	return render(request, 'urunler/anasayfa.html', {
		'urunler': urunler,
		'yorumlar': yorumlar,
		'form': form,
		'search_query': search_query,
	})


def urun_listesi(request):
	"""Ürün listesi sayfası"""
	urunler = Urun.objects.prefetch_related('fiyatlar__magaza').all()
	return render(request, 'urunler/urun_listesi.html', {'urunler': urunler})


def amazon_redirect(request):
	"""Amazon affiliate redirect with logging"""
	ClickLog.objects.create(
		user=request.user if request.user.is_authenticated else None,
		link_type='amazon',
		timestamp=timezone.now()
	)
	return redirect('https://www.amazon.com/b?node=53629917011&linkCode=ll2&tag=kolaybulekspr-20&linkId=8150ea1ccd7fe92bfd1f94652a6d69e4&language=en_US&ref_=as_li_ss_tl')


def aliexpress_redirect(request):
	"""AliExpress affiliate redirect with logging"""
	ClickLog.objects.create(
		user=request.user if request.user.is_authenticated else None,
		link_type='aliexpress',
		timestamp=timezone.now()
	)
	return redirect('https://rzekl.com/g/1e8d11449462ceef436f16525dc3e8/')


def urun_affiliate_redirect(request, urun_id):
	"""Ürün affiliate redirect - her ürün için kendi linki"""
	urun = get_object_or_404(Urun, id=urun_id)
	# İlk fiyatın affiliate linkini al
	fiyat = urun.fiyatlar.first()
	if not fiyat:
		return redirect('/')  # Fiyat yoksa ana sayfaya yönlendir
	
	ClickLog.objects.create(
		user=request.user if request.user.is_authenticated else None,
		link_type='urun_affiliate',
		urun=urun
	)
	return redirect(fiyat.affiliate_link)
