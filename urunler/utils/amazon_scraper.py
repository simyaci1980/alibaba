import re
import requests
from bs4 import BeautifulSoup
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)


def translate_to_turkish(text: str) -> str:
    """Metni Türkçeye çevir."""
    if not text or len(text.strip()) == 0:
        return text
    
    try:
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source='auto', target='tr')
        
        # Uzun metinleri parçala (5000 karakter limiti)
        if len(text) > 4500:
            text = text[:4500]
        
        translated = translator.translate(text)
        return translated
    except Exception as e:
        logger.warning(f"Çeviri hatası: {e}, orijinal metin kullanılıyor")
        return text


def extract_asin(amazon_url: str) -> Optional[str]:
    """Amazon URL'sinden ASIN çıkar."""
    # ASIN patterns
    patterns = [
        r'/dp/([A-Z0-9]{10})',  # /dp/ASIN
        r'/gp/product/([A-Z0-9]{10})',  # /gp/product/ASIN
        r'ASIN[=:]([A-Z0-9]{10})',  # ASIN=ASIN
    ]
    
    for pattern in patterns:
        match = re.search(pattern, amazon_url)
        if match:
            return match.group(1)
    
    return None


def scrape_amazon_product(amazon_url: str) -> Optional[Dict]:
    """
    Amazon linkinden ürün bilgilerini scrape et.
    Pyppeteer'ı skip et, doğrudan Requests + BeautifulSoup kullan.
    
    Returns:
        {
            'title': str,
            'description': str,
            'image_url': str,
            'asin': str
        }
    """
    try:
        # ASIN'i al
        asin = extract_asin(amazon_url)
        if not asin:
            logger.error(f"ASIN bulunamadı: {amazon_url}")
            return None
        
        logger.info(f"Amazon scraping başlıyor: ASIN={asin}")
        
        # Doğrudan Requests ile yap
        try:
            result = _scrape_with_requests(amazon_url)
            if result:
                logger.info(f"✓ Başarılı: {result.get('title', 'N/A')}")
                return result
        except Exception as e:
            logger.error(f"Scraping hatası: {e}")
            return None
    
    except Exception as e:
        logger.error(f"Amazon scraping hatası: {e}")
        return None


def _scrape_with_requests(url: str) -> Optional[Dict]:
    """Requests + BeautifulSoup ile basit scraping."""
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ]
    
    for attempt, user_agent in enumerate(user_agents):
        try:
            headers = {
                'User-Agent': user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            logger.info(f"Scraping attempt {attempt+1}: {user_agent}")
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            result = _parse_amazon_html(soup, url)
            
            if result and result.get('title') and result.get('title') != f'Amazon Ürünü {extract_asin(url)}':
                logger.info(f"✓ Scraping başarılı")
                return result
        
        except Exception as e:
            logger.warning(f"Attempt {attempt+1} başarısız: {e}")
            if attempt < len(user_agents) - 1:
                import time
                time.sleep(1)  # Retry arasında bekle
    
    logger.error(f"Tüm scraping denemeleri başarısız: {url}")
    return None


def _parse_amazon_html(soup: BeautifulSoup, url: str) -> Optional[Dict]:
    """BeautifulSoup HTML'sini parse et."""
    asin = extract_asin(url)
    
    # Başlık - birden fazla selector dene
    title = ''
    title_selectors = [
        '#productTitle',
        'span#productTitle',
        'h1#title span',
        'h1 span',
        'h1',
    ]
    
    for selector in title_selectors:
        elem = soup.select_one(selector)
        if elem:
            title = elem.get_text(strip=True)[:200]
            if title and not title.startswith('$'):
                break
    
    if not title or title == f'Amazon Ürünü {asin}':
        # Metadata'dan al
        meta = soup.select_one('meta[name="title"]')
        if meta:
            title = meta.get('content', '')[:200]
    
    if not title:
        title = f'Amazon Ürünü {asin}'
    
    # Başlığı Türkçeye çevir
    title = translate_to_turkish(title)
    
    # Açıklama
    description = ''
    
    # Önce meta description'ı dene
    meta = soup.select_one('meta[name="description"]')
    if meta:
        description = meta.get('content', '')[:300]
    
    # Eğer yoksa og:description dene
    if not description:
        meta = soup.select_one('meta[property="og:description"]')
        if meta:
            description = meta.get('content', '')[:300]
    
    # Eğer hala yoksa, bullet points'dan al
    if not description:
        bullets = soup.select('#feature-bullets ul li')
        if bullets:
            description = ' '.join([li.get_text(strip=True) for li in bullets[:3]])[:300]
    
    if not description:
        description = 'Amazon kaliteli ürün'
    
    # Açıklamayı Türkçeye çevir
    description = translate_to_turkish(description)
    
    # Resim URL - birden fazla selector
    image_url = ''
    
    # Dinamik resim
    img = soup.select_one('img#landingImage')
    if img:
        src = img.get('src') or img.get('data-old-hires')
        if src:
            image_url = src
    
    # Eğer yoksa, feature image
    if not image_url:
        img = soup.select_one('img.a-dynamic-image')
        if img:
            src = img.get('src')
            if src:
                image_url = src
    
    # Eğer yoksa, og:image kullan
    if not image_url:
        meta = soup.select_one('meta[property="og:image"]')
        if meta:
            image_url = meta.get('content', '')
    
    # Temizle (eğer placeholder ise)
    if image_url and image_url.startswith('$'):
        image_url = ''
    
    # Eğer image_url boşsa, boş bırak (kullanıcı bilecek)
    
    return {
        'title': title,
        'description': description,
        'image_url': image_url,
        'asin': asin
    }


def validate_amazon_url(url: str) -> bool:
    """Amazon URL'sini doğrula."""
    amazon_patterns = [
        r'amazon\.com',
        r'amazon\.ca',
        r'amazon\.co\.uk',
        r'amazon\.de',
        r'amazon\.fr',
        r'amazon\.it',
        r'amazon\.es',
        r'amazon\.co\.jp',
        r'amazon\.in',
    ]
    
    for pattern in amazon_patterns:
        if re.search(pattern, url):
            return True
    
    return False

