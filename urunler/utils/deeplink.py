import urllib.parse


def build_admitad_deeplink(base_link: str, product_url: str, subid: str | None = None) -> str:
    """
    Construct an Admitad deeplink using a known base affiliate link.
    - base_link: e.g. "https://rzekl.com/g/1e8d11449462ceef436f16525dc3e8/"
    - product_url: Target URL on advertiser site
    - subid: Optional subid/tracking code
    Returns the full deeplink URL.
    """
    if not base_link:
        raise ValueError("base_link is required")
    if not product_url:
        raise ValueError("product_url is required")

    # Ensure base_link ends with '/'
    if not base_link.endswith('/'):
        base_link = base_link + '/'

    params = {
        'ulp': product_url,
    }
    if subid:
        params['subid'] = subid

    query = urllib.parse.urlencode(params, safe=':/?&=')
    return f"{base_link}?{query}"
