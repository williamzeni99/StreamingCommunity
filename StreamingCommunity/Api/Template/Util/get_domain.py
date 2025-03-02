# 18.06.24

import certifi
from urllib.parse import urlparse, unquote


# External libraries
import httpx
from rich.console import Console


# Internal utilities
from StreamingCommunity.Util.headers import get_headers
from StreamingCommunity.Util.config_json import config_manager


# Variable
console = Console()
VERIFY = config_manager.get("REQUESTS", "verify")
MAX_TIMEOUT = config_manager.get_int("REQUESTS", "timeout")


def get_tld(url_str):
    """Extract the TLD (Top-Level Domain) from the URL."""
    try:
        url_str = unquote(url_str)
        parsed = urlparse(url_str)
        domain = parsed.netloc.lower()

        if domain.startswith('www.'):
            domain = domain[4:]
        parts = domain.split('.')

        return parts[-1] if len(parts) >= 2 else None
    
    except Exception:
        return None

def get_base_domain(url_str):
    """Extract base domain without protocol, www and path."""
    try:
        parsed = urlparse(url_str)
        domain = parsed.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]

        # Check if domain has multiple parts separated by dots
        parts = domain.split('.')
        if len(parts) > 2:
            return '.'.join(parts[:-1])
        
        return parts[0]
    
    except Exception:
        return None
    
def validate_url(url, base_url):
    """Validate if URL is accessible and matches expected base domain."""
    console.print(f"\n[cyan]Starting validation for URL[white]: [yellow]{url}")
    
    # Verify URL structure matches base_url structure
    base_domain = get_base_domain(base_url)
    url_domain = get_base_domain(url)

    if base_domain != url_domain:
        console.print(f"[red]Domain structure mismatch: {url_domain} != {base_domain}")
        return False, None
    
    client = httpx.Client(
        http1=True,
        verify=certifi.where(),
        headers=get_headers(),
        timeout=MAX_TIMEOUT
    )

    # Make request to web site
    response = client.get(url, follow_redirects=False)
        
    if response.status_code >= 400:
        console.print(f"[red]Check failed: HTTP {response.status_code}")
        console.print(f"[red]Response content: {response.text}")
        return False, None
        
    return True, base_domain

def search_domain(base_url: str):
    """Search for valid domain matching site name and base URL."""    
    try:
        is_correct, redirect_tld = validate_url(base_url, base_url)

        if is_correct:
            tld = redirect_tld or get_tld(base_url)
            return tld, base_url
        
        else:
            return None, None
        
    except Exception as e:
        console.print(f"[red]Error testing initial URL: {str(e)}")
        return None, None