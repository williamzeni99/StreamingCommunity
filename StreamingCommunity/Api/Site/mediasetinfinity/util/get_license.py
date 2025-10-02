# 16.03.25

from urllib.parse import urlencode
import xml.etree.ElementTree as ET


# External library
import httpx


# Internal utilities
from StreamingCommunity.Util.config_json import config_manager
from StreamingCommunity.Util.headers import get_headers, get_userAgent


# Variable
MAX_TIMEOUT = config_manager.get_int("REQUESTS", "timeout")


def get_bearer_token():
    """
    Gets the BEARER_TOKEN for authentication.

    Returns:
        str: The bearer token string.
    """
    return config_manager.get_dict("SITE_LOGIN", "mediasetinfinity")["beToken"]

def get_playback_url(BEARER_TOKEN, CONTENT_ID):
    """
    Gets the playback URL for the specified content.

    Args:
        BEARER_TOKEN (str): The authentication token.
        CONTENT_ID (str): The content identifier.

    Returns:
        dict: The playback JSON object.
    """
    headers = get_headers()
    headers['authorization'] = f'Bearer {BEARER_TOKEN}'
    
    json_data = {
        'contentId': CONTENT_ID,
        'streamType': 'VOD'
    }

    try:
        response = httpx.post(
            'https://api-ott-prod-fe.mediaset.net/PROD/play/playback/check/v2.0',
            headers=headers,
            json=json_data,
            follow_redirects=True,
            timeout=MAX_TIMEOUT
        )
        response.raise_for_status()
        resp_json = response.json()

        # Check for PL022 error (Infinity+ rights)
        if 'error' in resp_json and resp_json['error'].get('code') == 'PL022':
            raise RuntimeError("Infinity+ required for this content.")
        
        # Check for PL402 error (TVOD not purchased)
        if 'error' in resp_json and resp_json['error'].get('code') == 'PL402':
            raise RuntimeError("Content available for rental: you must rent it first.")

        playback_json = resp_json['response']['mediaSelector']
        return playback_json
    
    except Exception as e:
        raise RuntimeError(f"Failed to get playback URL: {e}")

def parse_tracking_data(tracking_value):
    """
    Parses the trackingData string into a dictionary.

    Args:
        tracking_value (str): The tracking data string.

    Returns:
        dict: Parsed tracking data.
    """
    return dict(item.split('=', 1) for item in tracking_value.split('|') if '=' in item)

def parse_smil_for_tracking_and_video(smil_xml):
    """
    Extracts all video_src and trackingData pairs from the SMIL.

    Args:
        smil_xml (str): The SMIL XML as a string.

    Returns:
        list: A list of dicts: {'video_src': ..., 'tracking_info': ...}
    """
    results = []
    root = ET.fromstring(smil_xml)
    ns = {'smil': root.tag.split('}')[0].strip('{')}

    # Search all <par>
    for par in root.findall('.//smil:par', ns):
        video_src = None
        tracking_info = None

        # Search <video> inside <par>
        video_elem = par.find('.//smil:video', ns)
        if video_elem is not None:
            video_src = video_elem.attrib.get('src')

        # Search <ref> inside <par>
        ref_elem = par.find('.//smil:ref', ns)
        if ref_elem is not None:
            # Search <param name="trackingData">
            for param in ref_elem.findall('.//smil:param', ns):
                if param.attrib.get('name') == 'trackingData':
                    tracking_value = param.attrib.get('value')
                    if tracking_value:
                        tracking_info = parse_tracking_data(tracking_value)
                    break

        if video_src and tracking_info:
            results.append({'video_src': video_src, 'tracking_info': tracking_info})

    return results

def get_tracking_info(BEARER_TOKEN, PLAYBACK_JSON):
    """
    Retrieves tracking information from the playback JSON.

    Args:
        BEARER_TOKEN (str): The authentication token.
        PLAYBACK_JSON (dict): The playback JSON object.

    Returns:
        list or None: List of tracking info dicts, or None if request fails.
    """
    params = {
        "format": "SMIL",
        "auth": BEARER_TOKEN,
        "formats": "MPEG-DASH",
        "assetTypes": "HR,browser,widevine,geoIT|geoNo:HR,browser,geoIT|geoNo:SD,browser,widevine,geoIT|geoNo:SD,browser,geoIT|geoNo:SS,browser,widevine,geoIT|geoNo:SS,browser,geoIT|geoNo",
        "balance": "true",
        "auto": "true",
        "tracking": "true",
        "delivery": "Streaming"
    }

    if 'publicUrl' in PLAYBACK_JSON:
        params['publicUrl'] = PLAYBACK_JSON['publicUrl']

    try:
        response = httpx.get(
            PLAYBACK_JSON['url'],
            headers={'user-agent': get_userAgent()},
            params=params,
            follow_redirects=True,
            timeout=MAX_TIMEOUT
        )
        response.raise_for_status()

        smil_xml = response.text
        results = parse_smil_for_tracking_and_video(smil_xml)
        return results
    
    except Exception:
        return None

def generate_license_url(BEARER_TOKEN, tracking_info):
    """
    Generates the URL to obtain the Widevine license.

    Args:
        BEARER_TOKEN (str): The authentication token.
        tracking_info (dict): The tracking info dictionary.

    Returns:
        str: The full license URL.
    """
    params = {
        'releasePid': tracking_info['tracking_info'].get('pid'),
        'account': f"http://access.auth.theplatform.com/data/Account/{tracking_info['tracking_info'].get('aid')}",
        'schema': '1.0',
        'token': BEARER_TOKEN,
    }
    
    return f"{'https://widevine.entitlement.theplatform.eu/wv/web/ModularDrm/getRawWidevineLicense'}?{urlencode(params)}"