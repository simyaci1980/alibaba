import requests
from decouple import config
from typing import Optional, Dict, List
import logging
import base64

logger = logging.getLogger(__name__)


class AdmitadAPI:
    """Admitad API client for fetching affiliate products."""
    
    BASE_URL = "https://api.admitad.com"
    TOKEN_URL = f"{BASE_URL}/token/"
    AUTH_URL = f"{BASE_URL}/authorize/"
    
    def __init__(self):
        # Credentials
        self.client_id = config('ADMITAD_CLIENT_ID', default='')
        self.client_secret = config('ADMITAD_CLIENT_SECRET', default='')

        # Tokens - for OAuth2 (if used later)
        self.access_token = config('ADMITAD_ACCESS_TOKEN', default='')
        self.refresh_token = config('ADMITAD_REFRESH_TOKEN', default='')

        # Fallback: if decouple fails, try direct read
        if not self.client_id or not self.client_secret:
            from pathlib import Path
            env_path = Path(__file__).resolve().parent.parent / '.env'
            if env_path.exists():
                with open(env_path) as f:
                    for line in f:
                        if line.startswith('ADMITAD_CLIENT_ID='):
                            self.client_id = line.split('=', 1)[1].strip()
                        elif line.startswith('ADMITAD_CLIENT_SECRET='):
                            self.client_secret = line.split('=', 1)[1].strip()
                        elif line.startswith('ADMITAD_ACCESS_TOKEN=') and not self.access_token:
                            self.access_token = line.split('=', 1)[1].strip()
                        elif line.startswith('ADMITAD_REFRESH_TOKEN=') and not self.refresh_token:
                            self.refresh_token = line.split('=', 1)[1].strip()

        # Always prefer latest token from admitad_token.json (overrides .env)
        try:
            from pathlib import Path
            token_file = Path(__file__).resolve().parent.parent / 'admitad_token.json'
            if token_file.exists():
                import json
                with open(token_file, 'r') as f:
                    data = json.load(f)
                    token_from_file = data.get('access_token', '')
                    if token_from_file:
                        self.access_token = token_from_file
        except Exception:
            pass
        
        # Generate Basic Auth header for direct API access
        if self.client_id and self.client_secret:
            credentials = f"{self.client_id}:{self.client_secret}"
            self.basic_auth = base64.b64encode(credentials.encode()).decode()
        else:
            self.basic_auth = None
    
    def get_authorization_url(self, redirect_uri: str = "http://localhost:8000/callback") -> str:
        """
        Get authorization URL for user to grant access.
        User must visit this URL and authorize the application.
        """
        params = {
            'client_id': self.client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            # Include deeplink scope to enable Deeplink API usage
            'scope': 'public_data statistics websites advcampaigns coupons deeplink',
        }
        query_string = '&'.join([f'{k}={v}' for k, v in params.items()])
        return f"{self.AUTH_URL}?{query_string}"
    
    def get_access_token_from_code(self, code: str, redirect_uri: str = "http://localhost:8000/callback") -> Optional[str]:
        """
        Exchange authorization code for access token.
        This is called after user authorizes the app.
        """
        try:
            # Create Basic Auth header
            credentials = f"{self.client_id}:{self.client_secret}"
            b64_credentials = base64.b64encode(credentials.encode()).decode()
            
            headers = {
                'Authorization': f'Basic {b64_credentials}',
                'Content-Type': 'application/x-www-form-urlencoded',
            }
            
            data = {
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': redirect_uri,
            }
            
            response = requests.post(self.TOKEN_URL, headers=headers, data=data)
            response.raise_for_status()
            token_data = response.json()
            self.access_token = token_data.get('access_token')
            logger.info("Access token obtained successfully")
            return self.access_token
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get access token: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            return None
    
    def set_access_token(self, token: str):
        """Manually set access token if you have one."""
        self.access_token = token
    
    def get_affiliate_programs(self, limit: int = 50, offset: int = 0) -> List[Dict]:
        """Get list of affiliate programs (e.g., AliExpress)."""
        if not self.access_token:
            return []

        try:
            url = f"{self.BASE_URL}/advcampaigns/?limit={limit}&offset={offset}"
            headers = {'Authorization': f'Bearer {self.access_token}'}
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data.get('results', [])
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch affiliate programs: {e}")
            return []

    def get_websites(self) -> List[Dict]:
        """List websites in Admitad account (needed for deeplinks)."""
        if not self.access_token:
            return []

        try:
            url = f"{self.BASE_URL}/websites/"
            headers = {'Authorization': f'Bearer {self.access_token}'}
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data.get('results', [])
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch websites: {e}")
            return []
    
    def get_aliexpress_products(self, keyword: str = "", limit: int = 10) -> List[Dict]:
        """
        Get AliExpress products via Admitad.
        Note: Specific endpoint depends on Admitad's AliExpress integration.
        """
        if not self.access_token:
            self.get_access_token()
        
        if not self.access_token:
            return []
        
        try:
            # This is a placeholder - actual endpoint may vary
            url = f"{self.BASE_URL}/products/"
            headers = {'Authorization': f'Bearer {self.access_token}'}
            params = {
                'campaign': 'aliexpress',  # May need actual campaign ID
                'keyword': keyword,
                'limit': limit
            }
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get('results', [])
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch AliExpress products: {e}")
            return []
    
    def get_product_details(self, product_url: str, campaign_id: int) -> Optional[Dict]:
        """
        AliExpress ürün URL'sinden ürün detaylarını çeker.
        
        NOT: Admitad API'nin ürün detayı endpoint'i yok veya yetersiz scope.
        Bu metod şimdilik None döndürür, admin.py fallback yapacak.
        
        Gelecek: AliExpress Open API entegrasyonu eklenebilir.
        """
        return None  # Admitad API'de ürün detayı endpoint'i yok
    
    def create_deeplink(self, url: str, campaign_id: int, website_id: int, debug: bool = False):
        """Create affiliate deeplink for a product URL using campaign & website IDs.

        When debug=True, returns tuple(deeplink_or_none, attempts) where attempts is a list of
        {url, method, status, body} to help diagnose failures.
        """
        # Try both Basic Auth (API credentials) and Bearer token
        auth_methods = []
        
        if self.basic_auth:
            auth_methods.append(('Basic', f'Basic {self.basic_auth}'))
        
        if self.access_token:
            auth_methods.append(('Bearer', f'Bearer {self.access_token}'))
        
        if not auth_methods:
            return (None, []) if debug else None

        # Try known endpoint variants; return first success
        endpoint_variants = [
            {
                'method': 'get',
                'url': f"{self.BASE_URL}/deeplink/{website_id}/",
                'params': {'advcampaign': campaign_id, 'ulp': url},
                'data': None,
            },
            {
                'method': 'get',
                'url': f"{self.BASE_URL}/deeplink/{website_id}/{campaign_id}/",
                'params': {'ulp': url},
                'data': None,
            },
            {
                'method': 'get',
                'url': f"{self.BASE_URL}/deeplink/{campaign_id}/",
                'params': {'website': website_id, 'ulp': url},
                'data': None,
            },
            {
                'method': 'get',
                'url': f"{self.BASE_URL}/deeplink/",
                'params': {'website': website_id, 'advcampaign': campaign_id, 'ulp': url},
                'data': None,
            },
            {
                'method': 'post',
                'url': f"{self.BASE_URL}/deeplink/create/",
                'params': None,
                'data': {'advcampaign': campaign_id, 'website': website_id, 'url': url},
            },
        ]

        attempts = []

        for auth_type, auth_header in auth_methods:
            for variant in endpoint_variants:
                try:
                    headers = {'Authorization': auth_header, 'Accept': 'application/json'}
                    
                    response = requests.request(
                        method=variant['method'],
                        url=variant['url'],
                        headers=headers,
                        params=variant['params'],
                        data=variant['data'],
                        timeout=15,
                    )
                    status_code = response.status_code
                    body_text = response.text
                    attempts.append({
                        'auth': auth_type,
                        'url': response.url,
                        'method': variant['method'],
                        'status': status_code,
                        'body': body_text
                    })

                    response.raise_for_status()
                    result = response.json()
                    deeplink = result.get('deeplink') or result.get('result') or result.get('link')
                    if deeplink:
                        return (deeplink, attempts) if debug else deeplink
                except requests.exceptions.HTTPError as e:
                    # Continue to next variant on 400/403/404/405; log others
                    status = e.response.status_code if hasattr(e, 'response') and e.response is not None else None
                    if status not in (400, 403, 404, 405):
                        logger.error(f"Failed to create deeplink via {variant['url']}: {e}")
                        if hasattr(e, 'response') and e.response is not None:
                            logger.error(f"Response: {e.response.text}")
                        return (None, attempts) if debug else None
                except requests.exceptions.RequestException as e:
                    logger.error(f"Failed to create deeplink via {variant['url']}: {e}")
                    return (None, attempts) if debug else None

        return (None, attempts) if debug else None
