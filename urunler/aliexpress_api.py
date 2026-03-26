"""
AliExpress Portals API Integration Module
Handles product search and affiliate link generation
Based on AliExpress Open Platform (Portals API)
"""

import requests
import json
import time
import hashlib
import hmac
from typing import Dict, List, Optional
from django.core.cache import cache
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class AliExpressAPIConnector:
    """AliExpress Portals API Connector"""
    
    # AliExpress API Endpoints
    # https://developers.aliexpress.com/en/doc.htm
    API_URL = "https://api-sg.aliexpress.com/sync"
    
    def __init__(self, app_key: str, app_secret: str):
        """
        Initialize AliExpress API Connector
        
        Args:
            app_key: AliExpress App Key (from Portals)
            app_secret: AliExpress App Secret
        """
        self.app_key = app_key
        self.app_secret = app_secret
        
        # Setup session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST", "GET"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
    
    def _sign_request(self, params: Dict) -> str:
        """
        Sign API request with MD5
        AliExpress signature format: appsecretkey1value1key2value2...appsecret
        
        Args:
            params: Request parameters
            
        Returns:
            Signature string
        """
        # Sort parameters by key (excluding 'sign')
        sorted_params = sorted([(k, v) for k, v in params.items() if k != 'sign'])
        
        # Build string: appsecret + key1value1key2value2... + appsecret
        sign_string = self.app_secret + ''.join([f'{k}{v}' for k, v in sorted_params]) + self.app_secret
        
        # MD5 hash and uppercase
        signature = hashlib.md5(sign_string.encode('utf-8')).hexdigest().upper()
        
        return signature
    
    def search_products(
        self,
        keywords: str = None,
        category_id: str = None,
        page_no: int = 1,
        page_size: int = 20,
        sort: str = "default",
        min_price: float = None,
        max_price: float = None,
        tracking_id: str = None,
        ship_to_country: str = None,
        ship_from_country: str = None,
        **kwargs
    ) -> Optional[Dict]:
        """
        Search products using AliExpress Portals API
        
        API Method: aliexpress.affiliate.product.query
        
        Args:
            keywords: Search keywords
            category_id: Category ID
            page_no: Page number (1-based)
            page_size: Results per page (1-50, default: 20)
            sort: Sort order (default, price_asc, price_desc, etc.)
            min_price: Minimum price filter (USD)
            max_price: Maximum price filter (USD)
            tracking_id: Your tracking/sub ID (REQUIRED for affiliate links)
            ship_to_country: Country code (e.g., 'TR' for Turkey)
            ship_from_country: Filter by shipping from country (e.g., 'TR' for Turkey warehouse)
            
        Returns:
            API response dict or None if failed
        """
        try:
            # Build request parameters
            params = {
                'app_key': self.app_key,
                'timestamp': str(int(time.time() * 1000)),
                'sign_method': 'md5',
                'format': 'json',
                'v': '2.0',
                'method': 'aliexpress.affiliate.product.query',
            }
            
            # Add search parameters
            if keywords:
                params['keywords'] = keywords
            if category_id:
                params['category_ids'] = category_id
            
            params['page_no'] = str(page_no)
            params['page_size'] = str(min(page_size, 50))  # Max 50
            
            if sort:
                params['sort'] = sort
            if min_price:
                params['min_price'] = str(min_price)
            if max_price:
                params['max_price'] = str(max_price)
            
            # Add tracking ID (required for affiliate links)
            if tracking_id:
                params['tracking_id'] = tracking_id
            elif 'tracking_id' in kwargs:
                params['tracking_id'] = kwargs['tracking_id']
            
            # Layer-1 filter: API-side ship-to-country prefilter
            # NOTE: This is only a coarse filter; final availability is verified in browser.
            if ship_to_country:
                params['shipToCountry'] = ship_to_country
                logger.info(f"Added shipToCountry prefilter: {ship_to_country}")
            
            # NOTE: ship_from_country not supported by API - causes timeout
            # Keeping parameter for future API updates
            # if ship_from_country:
            #     params['ship_from_country'] = ship_from_country
            
            # Generate signature
            params['sign'] = self._sign_request(params)
            
            # Log request parameters for debugging
            logger.info(f"API Request params: {', '.join([f'{k}={v}' for k, v in params.items() if k != 'sign'])}")
            
            # Make API request
            response = self.session.get(
                self.API_URL,
                params=params,
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"AliExpress API error (HTTP {response.status_code}): {response.text}")
                return None
            
            data = response.json()
            
            # Log API response structure for debugging
            if 'aliexpress_affiliate_product_query_response' in data:
                resp_result = data.get('aliexpress_affiliate_product_query_response', {}).get('resp_result', {})
                if isinstance(resp_result, str):
                    import json
                    resp_result = json.loads(resp_result)
                result_count = len(resp_result.get('result', {}).get('products', {}).get('product', []))
                logger.info(f"API returned {result_count} products")
            
            # Check for API errors
            if 'error_response' in data:
                error = data['error_response']
                logger.error(f"AliExpress API error: {error.get('msg', 'Unknown error')}")
                return None
            
            return data
            
        except requests.exceptions.Timeout:
            logger.error(f"AliExpress search timed out for keywords '{keywords}'")
            return None
        except requests.exceptions.ConnectionError:
            logger.error("Failed to connect to AliExpress API")
            return None
        except Exception as e:
            logger.error(f"AliExpress search failed: {str(e)}")
            return None
    
    def get_product_details(self, product_id: str, **kwargs) -> Optional[Dict]:
        """
        Get detailed product information
        
        API Method: aliexpress.affiliate.productdetail.get
        
        Args:
            product_id: AliExpress product ID
            
        Returns:
            Product details dict or None
        """
        try:
            params = {
                'app_key': self.app_key,
                'timestamp': str(int(time.time() * 1000)),
                'sign_method': 'md5',
                'format': 'json',
                'v': '2.0',
                'method': 'aliexpress.affiliate.productdetail.get',
                'product_ids': product_id,
            }
            
            # Add tracking ID if provided
            if 'tracking_id' in kwargs:
                params['tracking_id'] = kwargs['tracking_id']
            
            # Generate signature
            params['sign'] = self._sign_request(params)
            
            # Make request
            response = self.session.get(
                self.API_URL,
                params=params,
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"Product details error (HTTP {response.status_code})")
                return None
            
            data = response.json()
            
            if 'error_response' in data:
                error = data['error_response']
                logger.error(f"Product details error: {error.get('msg', 'Unknown')}")
                return None
            
            return data
            
        except Exception as e:
            logger.error(f"Get product details failed: {str(e)}")
            return None
    
    def generate_affiliate_link(
        self, 
        product_url: str,
        tracking_id: str = None,
        **kwargs
    ) -> Optional[str]:
        """
        Generate affiliate tracking link
        
        API Method: aliexpress.affiliate.link.generate
        
        Args:
            product_url: Original product URL
            tracking_id: Your tracking/sub ID
            
        Returns:
            Affiliate link or None
        """
        try:
            params = {
                'app_key': self.app_key,
                'timestamp': str(int(time.time() * 1000)),
                'sign_method': 'md5',
                'format': 'json',
                'v': '2.0',
                'method': 'aliexpress.affiliate.link.generate',
                'source_values': product_url,
                'promotion_link_type': '0',  # 0=default, 2=social media
            }
            
            if tracking_id:
                params['tracking_id'] = tracking_id
            
            # Generate signature
            params['sign'] = self._sign_request(params)
            
            # Make request
            response = self.session.get(
                self.API_URL,
                params=params,
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"Affiliate link generation error (HTTP {response.status_code})")
                return None
            
            data = response.json()
            
            if 'error_response' in data:
                error = data['error_response']
                logger.error(f"Affiliate link error: {error.get('msg', 'Unknown')}")
                return None
            
            # Extract promotion link
            result = data.get('aliexpress_affiliate_link_generate_response', {})
            resp_result = result.get('resp_result', {})
            
            if isinstance(resp_result, str):
                resp_result = json.loads(resp_result)
            
            result_list = resp_result.get('result', {}).get('promotion_links', [])
            
            if result_list and len(result_list) > 0:
                return result_list[0].get('promotion_link')
            
            return None
            
        except Exception as e:
            logger.error(f"Generate affiliate link failed: {str(e)}")
            return None
    
    def parse_search_results(self, response: Dict) -> List[Dict]:
        """
        Parse search response and extract relevant product data
        
        Returns:
            List of product dicts
        """
        products = []
        
        try:
            # Navigate through response structure
            result = response.get('aliexpress_affiliate_product_query_response', {})
            resp_result = result.get('resp_result', {})
            
            # resp_result might be a JSON string
            if isinstance(resp_result, str):
                resp_result = json.loads(resp_result)
            
            # Get products list
            products_data = resp_result.get('result', {}).get('products', {}).get('product', [])
            
            for item in products_data:
                # Extract all available fields from API response
                parsed_product = {
                    # Basic Info
                    'product_id': item.get('product_id'),
                    'title': item.get('product_title'),
                    'product_url': item.get('product_detail_url'),
                    'promotion_link': item.get('promotion_link'),
                    
                    # Pricing
                    'price': float(item.get('target_sale_price', 0)),
                    'original_price': float(item.get('target_original_price', 0)),
                    'currency': item.get('target_sale_price_currency', 'USD'),
                    'discount': item.get('discount', '0'),
                    
                    # Commission
                    'commission_rate': item.get('commission_rate', '0'),
                    
                    # Images
                    'image_url': item.get('product_main_image_url'),
                    'product_small_image_urls': item.get('product_small_image_urls', {}).get('string', []) if item.get('product_small_image_urls') else [],
                    
                    # Category
                    'category_id': item.get('first_level_category_id'),
                    'category_name': item.get('first_level_category_name'),
                    'second_level_category_id': item.get('second_level_category_id'),
                    'second_level_category_name': item.get('second_level_category_name'),
                    
                    # Seller/Shop
                    'shop_url': item.get('shop_url'),
                    'shop_id': item.get('shop_id'),
                    'seller_id': item.get('seller_id'),
                    
                    # Ratings & Sales
                    'rating': item.get('evaluate_rate', '0'),
                    'orders': item.get('volume', 0),
                    'hot_product_commission_rate': item.get('hot_product_commission_rate'),
                    'lastest_volume': item.get('lastest_volume', 0),
                    
                    # Shipping & Delivery
                    'delivery_time': item.get('delivery_time'),  # Tahmini teslimat süresi (gün)
                    'ship_from_country': item.get('ship_from_country'),  # Gönderildiği ülke
                    'ship_to_country': item.get('ship_to_country'),  # Gönderilebilen ülke
                    'shipping_info': item.get('shipping_info'),
                    'estimated_delivery_date': item.get('estimated_delivery_date'),
                    
                    # Product Details
                    'product_video_url': item.get('product_video_url'),
                    'target_app_sale_price': item.get('target_app_sale_price'),
                    'target_original_price_currency': item.get('target_original_price_currency'),
                    
                    # Platform specific
                    'platform_product_type': item.get('platform_product_type'),
                    'relevant_market_commission_rate': item.get('relevant_market_commission_rate'),
                    
                    # Extra metadata (tüm kalan alanları sakla)
                    '_raw_data': {k: v for k, v in item.items() if k not in [
                        'product_id', 'product_title', 'product_detail_url', 'promotion_link',
                        'target_sale_price', 'target_original_price', 'target_sale_price_currency',
                        'discount', 'commission_rate', 'product_main_image_url', 'product_small_image_urls',
                        'first_level_category_id', 'first_level_category_name', 'second_level_category_id',
                        'second_level_category_name', 'shop_url', 'shop_id', 'seller_id', 'evaluate_rate',
                        'volume', 'hot_product_commission_rate', 'lastest_volume', 'delivery_time',
                        'ship_from_country', 'ship_to_country', 'shipping_info', 'estimated_delivery_date',
                        'product_video_url', 'target_app_sale_price', 'target_original_price_currency',
                        'platform_product_type', 'relevant_market_commission_rate'
                    ]}
                }
                
                products.append(parsed_product)
            
            return products
            
        except Exception as e:
            logger.error(f"Failed to parse search results: {str(e)}")
            return []
    
    def check_product_shipping(
        self,
        product_id: str,
        ship_to_country: str = 'TR',
        target_sale_price: float = None,
        target_currency: str = 'USD',
        target_language: str = 'EN',
        sku_id: str = '0',
        tax_rate: str = '0',
        **kwargs
    ) -> Optional[Dict]:
        """
        Check if product can ship to specific country
        
        API Method: aliexpress.affiliate.product.shipping.get
        
        Args:
            product_id: AliExpress product ID
            ship_to_country: Country code (e.g., 'TR' for Turkey)
            target_sale_price: Product price (required by API for shipping calculation)
            target_currency: Currency code for pricing (default: 'USD')
            target_language: Language code (default: 'EN')
            **kwargs: Additional parameters (sku_id, tracking_id, etc.)
            
        Returns:
            Shipping info dict with structure:
            {
                'can_ship': bool,           # True if product can ship to country
                'delivery_days': str,        # Estimated delivery days (e.g., "10-20")
                'shipping_fee': float,       # Shipping cost (USD)
                'error': str                 # Error message if API fails
            }
        """
        try:
            # Validate required parameters
            if target_sale_price is None:
                logger.warning(f"Product {product_id}: target_sale_price is required for shipping check")
                return {
                    'can_ship': None,
                    'error': 'target_sale_price required'
                }
            
            params = {
                'app_key': self.app_key,
                'timestamp': str(int(time.time() * 1000)),
                'sign_method': 'md5',
                'format': 'json',
                'v': '2.0',
                'method': 'aliexpress.affiliate.product.shipping.get',
                'product_id': str(product_id),
                'ship_to_country': ship_to_country,
                'target_currency': target_currency,
                'target_sale_price': str(target_sale_price),
                'target_language': target_language,
                'sku_id': str(sku_id),
                'tax_rate': str(tax_rate),
            }
            
            # Optional: SKU ID override for variant-specific shipping
            if 'sku_id' in kwargs and kwargs['sku_id'] is not None:
                params['sku_id'] = str(kwargs['sku_id'])

            # Optional: tax_rate override (API now expects this field)
            if 'tax_rate' in kwargs and kwargs['tax_rate'] is not None:
                params['tax_rate'] = str(kwargs['tax_rate'])
            
            # Generate signature
            params['sign'] = self._sign_request(params)
            
            logger.debug(f"Checking shipping for product {product_id} to {ship_to_country}")
            
            # Make API request
            response = self.session.get(
                self.API_URL,
                params=params,
                timeout=30
            )
            
            if response.status_code != 200:
                logger.warning(f"Shipping check error (HTTP {response.status_code}) for product {product_id}")
                return {
                    'can_ship': None,
                    'error': f'HTTP {response.status_code}'
                }
            
            data = response.json()
            
            # Check for API errors
            if 'error_response' in data:
                error = data['error_response']
                error_msg = error.get('msg', 'Unknown error')
                logger.warning(f"Shipping API error for product {product_id}: {error_msg}")
                return {
                    'can_ship': None,
                    'error': error_msg
                }
            
            # Parse shipping response
            result = data.get('aliexpress_affiliate_product_shipping_get_response', {})
            resp_result = result.get('resp_result', {})
            
            if isinstance(resp_result, str):
                resp_result = json.loads(resp_result)
            
            # Some API responses only include resp_code/resp_msg without result payload.
            resp_code = resp_result.get('resp_code')
            resp_msg = resp_result.get('resp_msg')
            if resp_code and str(resp_code) != '200':
                return {
                    'can_ship': None,
                    'delivery_days': None,
                    'shipping_fee': None,
                    'shipping_method': None,
                    'error': f"resp_code={resp_code}" + (f", msg={resp_msg}" if resp_msg else "")
                }

            # Extract shipping info
            shipping_info = resp_result.get('result', {})
            
            if not shipping_info:
                logger.warning(f"No shipping info returned for product {product_id}")
                return {
                    'can_ship': False,
                    'error': 'No shipping info available'
                }
            
            # Check if shipping is available
            # API returns shipping methods if available, empty if not
            shipping_methods = shipping_info.get('aeop_freight_calculate_result_for_buyer_d_t_o_list', [])
            
            if not shipping_methods:
                logger.info(f"Product {product_id} cannot ship to {ship_to_country}")
                return {
                    'can_ship': False,
                    'delivery_days': None,
                    'shipping_fee': None,
                    'error': None
                }
            
            # Product CAN ship - extract details from first shipping method
            first_method = shipping_methods[0] if isinstance(shipping_methods, list) else shipping_methods
            
            return {
                'can_ship': True,
                'delivery_days': first_method.get('estimated_delivery_time', 'Unknown'),
                'shipping_fee': float(first_method.get('freight', {}).get('amount', 0)),
                'shipping_method': first_method.get('service_name', 'Standard'),
                'error': None
            }
            
        except requests.exceptions.Timeout:
            logger.warning(f"Shipping check timed out for product {product_id}")
            return {
                'can_ship': None,
                'error': 'Timeout'
            }
        except Exception as e:
            logger.error(f"Shipping check failed for product {product_id}: {str(e)}")
            return {
                'can_ship': None,
                'error': str(e)
            }

    # ─── OAuth 2.0 (Advanced API) ────────────────────────────────────────────

    OAUTH_AUTH_URL  = "https://oauth.aliexpress.com/authorize"
    OAUTH_TOKEN_URL = "https://oauth.aliexpress.com/token"
    ADVANCED_API_BASE = "https://api.aliexpress.com/v2/affiliate"

    def get_authorize_url(self, redirect_uri: str, state: str = "kolaybulexpres") -> str:
        """
        AliExpress Advanced API için kullanıcının ziyaret edeceği URL'i döndürür.
        Kullanıcı onayladıktan sonra redirect_uri?code=... şeklinde geri yönlendirilir.
        """
        from urllib.parse import urlencode
        params = {
            "response_type": "code",
            "app_key":   self.app_key,
            "client_id": self.app_key,
            "redirect_uri": redirect_uri,
            "state": state,
        }
        return f"{self.OAUTH_AUTH_URL}?{urlencode(params)}"

    def exchange_code_for_token(self, code: str, redirect_uri: str) -> Optional[Dict]:
        """
        Callback'ten alınan `code` parametresini access_token ile değiş tokuş eder.
        Başarılıysa {'access_token': ..., 'refresh_token': ..., 'expires_in': ...} döner.
        """
        try:
            response = self.session.post(
                self.OAUTH_TOKEN_URL,
                data={
                    "grant_type":    "authorization_code",
                    "code":          code,
                    "client_id":     self.app_key,
                    "client_secret": self.app_secret,
                    "redirect_uri":  redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            if response.status_code != 200:
                logger.error(f"Token exchange error (HTTP {response.status_code}): {response.text[:300]}")
                return None
            try:
                data = response.json()
            except Exception:
                logger.error(f"Token exchange non-JSON response: {response.text[:300]}")
                return None
            if "access_token" not in data:
                logger.error(f"access_token field missing in response: {data}")
                return None
            return data
        except Exception as e:
            logger.error(f"Token exchange failed: {str(e)}")
            return None

    def call_advanced_api(self, endpoint: str, params: Dict, access_token: str) -> Optional[Dict]:
        """
        Advanced API v2 endpointini access_token ile çağırır.
        endpoint örn: 'hotproducts/query'
        """
        try:
            all_params = {
                "app_key":      self.app_key,
                "access_token": access_token,
                **params,
            }
            url = f"{self.ADVANCED_API_BASE}/{endpoint}"
            response = self.session.get(url, params=all_params, timeout=30)
            if response.status_code != 200:
                logger.error(f"Advanced API HTTP {response.status_code}: {response.text[:200]}")
                return None
            if "<html>" in response.text[:200].lower():
                logger.warning("Advanced API HTML döndürdü (bakım modu?)")
                return None
            return response.json()
        except Exception as e:
            logger.error(f"Advanced API call failed: {str(e)}")
            return None
