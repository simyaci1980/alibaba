"""
eBay API Integration Module
Handles OAuth token generation and product search via Browse API
"""

import requests
import json
from typing import Dict, List, Optional
from django.core.cache import cache
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class EbayAPIConnector:
    """eBay Browse API Connector"""
    
    # Endpoints (corrected OAuth token paths)
    SANDBOX_AUTH_URL = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
    SANDBOX_API_URL = "https://api.sandbox.ebay.com/buy/browse/v1"
    
    PRODUCTION_AUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
    PRODUCTION_API_URL = "https://api.ebay.com/buy/browse/v1"
    
    def __init__(self, client_id: str, client_secret: str, sandbox: bool = True):
        """
        Initialize eBay API Connector
        
        Args:
            client_id: eBay Developer App ID (Client ID)
            client_secret: eBay Developer Cert ID (Client Secret)
            sandbox: Use sandbox environment (default: True)
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.sandbox = sandbox
        
        self.auth_url = self.SANDBOX_AUTH_URL if sandbox else self.PRODUCTION_AUTH_URL
        self.api_url = self.SANDBOX_API_URL if sandbox else self.PRODUCTION_API_URL
        
        self.token = None
        self.token_type = "Bearer"
        
        # Setup session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,  # Total retries
            backoff_factor=1,  # Wait 1, 2, 4 seconds
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST", "GET"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        
    def get_oauth_token(self) -> Optional[str]:
        """
        Get OAuth 2.0 Application Access Token
        Uses Client Credentials flow
        
        Returns:
            Access token string or None if failed
        """
        # Check cache first
        cache_key = f"ebay_token_{'sandbox' if self.sandbox else 'production'}"
        cached_token = cache.get(cache_key)
        if cached_token:
            self.token = cached_token
            return cached_token
        
        try:
            # Prepare auth header
            auth = (self.client_id, self.client_secret)
            headers = {
                "Content-Type": "application/x-www-form-urlencoded"
            }
            data = {
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope"
            }
            
            # Use session with retry + longer timeout (30s)
            response = self.session.post(
                self.auth_url,
                headers=headers,
                data=data,
                auth=auth,
                timeout=30  # Increased from 10 to 30 seconds
            )
            
            if response.status_code != 200:
                logger.error(f"OAuth token error (HTTP {response.status_code}): {response.text}")
                return None
            
            token_data = response.json()
            self.token = token_data.get("access_token")
            
            # Cache token (expires in ~2 hours, cache for 1 hour)
            expires_in = token_data.get("expires_in", 7200)
            cache.set(cache_key, self.token, expires_in - 300)  # Refresh 5min before expiry
            
            logger.info(f"OAuth token obtained successfully ({'Sandbox' if self.sandbox else 'Production'})")
            return self.token
            
        except requests.exceptions.Timeout:
            logger.error("OAuth token request timed out. Check your network connection.")
            return None
        except requests.exceptions.ConnectionError:
            logger.error("Failed to connect to eBay OAuth server. Check internet connection.")
            return None
        except Exception as e:
            logger.error(f"Failed to get OAuth token: {str(e)}")
            return None
    
    def search_items(self, q: str, limit: int = 20, offset: int = 0, **kwargs) -> Optional[Dict]:
        """
        Search items using Browse API
        
        Args:
            q: Search query (e.g., "drone" or "trimui smart pro")
            limit: Number of results (1-200, default: 20)
            offset: Pagination offset
            **kwargs: Additional params (category_id, filter, sort, etc.)
        
        Returns:
            JSON response dict or None if failed
        """
        if not self.token:
            if not self.get_oauth_token():
                return None
        
        try:
            headers = {
                "Authorization": f"{self.token_type} {self.token}",
                "Content-Type": "application/json"
            }
            
            params = {
                "q": q,
                "limit": min(limit, 200),  # Max 200 per request
                "offset": offset
            }
            
            # Add optional params
            if "category_id" in kwargs:
                params["category_ids"] = kwargs["category_id"]
            if "filter" in kwargs:
                params["filter"] = kwargs["filter"]
            if "sort" in kwargs:
                params["sort"] = kwargs["sort"]
            
            url = f"{self.api_url}/item_summary/search"
            response = self.session.get(url, headers=headers, params=params, timeout=30)  # Increased timeout
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Search error {response.status_code}: {response.text}")
                return None
        
        except requests.exceptions.Timeout:
            logger.error(f"Search request timed out for query '{q}'. Check network connection.")
            return None
        except requests.exceptions.ConnectionError:
            logger.error("Failed to connect to eBay Search API. Check internet connection.")
            return None
        except Exception as e:
            logger.error(f"Search failed: {str(e)}")
            return None
    
    def get_item_details(self, item_id: str) -> Optional[Dict]:
        """
        Get detailed information about a specific item
        
        Args:
            item_id: eBay item ID (e.g., "v1|123456789|0")
        
        Returns:
            Item details dict or None
        """
        if not self.token:
            if not self.get_oauth_token():
                return None
        
        try:
            headers = {
                "Authorization": f"{self.token_type} {self.token}",
                "Content-Type": "application/json"
            }
            
            url = f"{self.api_url}/item/{item_id}"
            response = self.session.get(url, headers=headers, timeout=30)  # Increased timeout
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Item details error {response.status_code}: {response.text}")
                return None
        
        except requests.exceptions.Timeout:
            logger.error(f"Item details request timed out for item_id '{item_id}'. Check network connection.")
            return None
        except requests.exceptions.ConnectionError:
            logger.error("Failed to connect to eBay Item Details API. Check internet connection.")
            return None
        except Exception as e:
            logger.error(f"Get item details failed: {str(e)}")
            return None
    
    def parse_search_results(self, response: Dict) -> List[Dict]:
        """
        Parse search response and extract relevant fields
        
        Returns:
            List of dicts with relevant product info
        """
        items = []
        
        if not response or "itemSummaries" not in response:
            return items
        
        for item in response.get("itemSummaries", []):
            parsed_item = {
                "item_id": item.get("itemId"),
                "title": item.get("title"),
                "price": float(item.get("price", {}).get("value", 0)) if item.get("price") else 0,
                "currency": item.get("price", {}).get("currency", "USD") if item.get("price") else "USD",
                "condition": item.get("condition", "Unknown"),
                "image_url": item.get("image", {}).get("imageUrl") if item.get("image") else None,
                "affiliate_url": item.get("itemAffiliateWebUrl"),
                "item_web_url": item.get("itemWebUrl"),
                "category": item.get("categories")[0].get("categoryName") if item.get("categories") else None,
                "seller_feedback_score": item.get("seller", {}).get("feedbackScore", 0),
                "shipping_cost": 0,
                "shipping_origin": "USA",
                "shipping_available": True,
            }
            
            # Parse shipping info
            if item.get("shippingOptions"):
                shipping = item["shippingOptions"][0]
                parsed_item["shipping_cost"] = float(
                    shipping.get("shippingCost", {}).get("value", 0)
                ) if shipping.get("shippingCost") else 0
                if shipping.get("shippingCostType") == "FIXED":
                    parsed_item["shipping_available"] = True
            
            # Parse category
            if item.get("categories"):
                parsed_item["category"] = item["categories"][0].get("categoryName")
            
            items.append(parsed_item)
        
        return items
