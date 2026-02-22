from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Q, Case, When, IntegerField
from .models import Urun, ClickLog, Yorum
from .forms import YorumForm





def anasayfa(request):
	"""Ana sayfa - ürün listesi ve yorumlar"""
	search_query = request.GET.get('q', '').strip()
	
	if search_query:
		# Arama yapılıyorsa - ürün ismine veya urun_kodu'na göre filtrele
		urunler = Urun.objects.prefetch_related('fiyatlar__magaza').filter(
			Q(isim__icontains=search_query) |
			Q(aciklama__icontains=search_query) |
			Q(urun_kodu__iexact=search_query) |
			Q(urun_kodu__icontains=search_query)
		).annotate(
			# Tam eşleşme öncelikli sıralama
			relevance=Case(
				When(isim__iexact=search_query, then=1),
				When(isim__istartswith=search_query, then=2),
				When(isim__icontains=search_query, then=3),
				When(urun_kodu__iexact=search_query, then=0),
				default=4,
				output_field=IntegerField()
			)
		).order_by('relevance', 'isim')
	else:
		# Arama yoksa tüm ürünleri göster
		gonderim_yeri = request.GET.get('gonderim_yeri', '').strip()
		urunler = list(Urun.objects.prefetch_related('fiyatlar__magaza').all())
		if gonderim_yeri:
			gonderim_yeri_lower = gonderim_yeri.strip().lower()
			urunler = [
				u for u in urunler
				if any(
					f.gonderim_yerinden and f.gonderim_yerinden.strip().lower() == gonderim_yeri_lower
					for f in u.fiyatlar.all()
				)
			]
		numarali = {u.sira: u for u in urunler if u.sira and u.sira > 0}
		sifirli = [u for u in urunler if not u.sira or u.sira == 0]
		sifirli_sorted = sorted(sifirli, key=lambda u: -u.id)
		max_sira = max(list(numarali.keys()) + [0])
		urunler_sirali = []
		sifirli_idx = 0
		for i in range(1, max_sira+1):
			if i in numarali:
				urunler_sirali.append(numarali[i])
			else:
				if sifirli_idx < len(sifirli_sorted):
					urunler_sirali.append(sifirli_sorted[sifirli_idx])
					sifirli_idx += 1
		urunler_sirali += sifirli_sorted[sifirli_idx:]
		urunler = urunler_sirali
	
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
	urunler = list(Urun.objects.prefetch_related('fiyatlar__magaza').all())
	numarali = {u.sira: u for u in urunler if u.sira and u.sira > 0}
	sifirli = [u for u in urunler if not u.sira or u.sira == 0]
	sifirli_sorted = sorted(sifirli, key=lambda u: -u.id)
	max_sira = max(list(numarali.keys()) + [0])
	urunler_sirali = []
	sifirli_idx = 0
	for i in range(1, max_sira+1):
		if i in numarali:
			urunler_sirali.append(numarali[i])
		else:
			if sifirli_idx < len(sifirli_sorted):
				urunler_sirali.append(sifirli_sorted[sifirli_idx])
				sifirli_idx += 1
	urunler_sirali += sifirli_sorted[sifirli_idx:]
	urunler = urunler_sirali
	return render(request, 'urunler/urun_listesi.html', {'urunler': urunler})


def amazon_redirect(request):
	"""Amazon affiliate redirect with logging"""
	ClickLog.objects.create(
		user=request.user if request.user.is_authenticated else None,
		link_type='amazon',
		subid='navbar',
		timestamp=timezone.now()
	)
	return redirect('https://www.amazon.com/b?node=53629917011&linkCode=ll2&tag=kolaybulekspr-20&linkId=8150ea1ccd7fe92bfd1f94652a6d69e4&language=en_US&ref_=as_li_ss_tl')


def aliexpress_redirect(request):
	"""AliExpress affiliate redirect with logging"""
	ClickLog.objects.create(
		user=request.user if request.user.is_authenticated else None,
		link_type='aliexpress',
		subid='navbar',
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
