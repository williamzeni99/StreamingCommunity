# 09.08.25
from __future__ import annotations

import time
import random
from typing import Any, Dict, Optional, Union


# External library
import httpx


# Logic class
from StreamingCommunity.Util.config_json import config_manager
from StreamingCommunity.Util.headers import get_userAgent


# Defaults from config
def _get_timeout() -> int:
    try:
        return int(config_manager.get_int("REQUESTS", "timeout"))
    except Exception:
        return 20


def _get_max_retry() -> int:
    try:
        return int(config_manager.get_int("REQUESTS", "max_retry"))
    except Exception:
        return 3


def _get_verify() -> bool:
    try:
        return bool(config_manager.get_bool("REQUESTS", "verify"))
    except Exception:
        return True


def _get_proxies() -> Optional[Dict[str, str]]:
    """Return proxies dict if present in config and non-empty, else None."""
    try:
        proxies = config_manager.get_dict("REQUESTS", "proxy")
        if not isinstance(proxies, dict):
            return None
        # Normalize empty strings to None (httpx ignores None)
        cleaned: Dict[str, str] = {}
        for scheme, url in proxies.items():
            if isinstance(url, str) and url.strip():
                cleaned[scheme] = url.strip()
        return cleaned or None
    except Exception:
        return None


def _default_headers(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    headers = {"User-Agent": get_userAgent()}
    if extra:
        headers.update(extra)
    return headers


def create_client(
    *,
    headers: Optional[Dict[str, str]] = None,
    cookies: Optional[Dict[str, str]] = None,
    timeout: Optional[Union[int, float]] = None,
    verify: Optional[bool] = None,
    proxies: Optional[Dict[str, str]] = None,
    http2: bool = False,
    follow_redirects: bool = True,
) -> httpx.Client:
    """Factory for a configured httpx.Client."""
    return httpx.Client(
        headers=_default_headers(headers),
        cookies=cookies,
        timeout=timeout if timeout is not None else _get_timeout(),
        verify=_get_verify() if verify is None else verify,
        follow_redirects=follow_redirects,
        http2=http2,
        proxy=proxies if proxies is not None else _get_proxies(),
    )


def create_async_client(
    *,
    headers: Optional[Dict[str, str]] = None,
    cookies: Optional[Dict[str, str]] = None,
    timeout: Optional[Union[int, float]] = None,
    verify: Optional[bool] = None,
    proxies: Optional[Dict[str, str]] = None,
    http2: bool = False,
    follow_redirects: bool = True,
) -> httpx.AsyncClient:
    """Factory for a configured httpx.AsyncClient."""
    return httpx.AsyncClient(
        headers=_default_headers(headers),
        cookies=cookies,
        timeout=timeout if timeout is not None else _get_timeout(),
        verify=_get_verify() if verify is None else verify,
        follow_redirects=follow_redirects,
        http2=http2,
        proxies=proxies if proxies is not None else _get_proxies(),
    )


def _sleep_with_backoff(attempt: int, base: float = 1.1, cap: float = 10.0) -> None:
    """Exponential backoff with jitter."""
    delay = min(base * (2 ** attempt), cap)
    # Add small jitter to avoid thundering herd
    delay += random.uniform(0.0, 0.25)
    time.sleep(delay)


def fetch(
    url: str,
    *,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Any] = None,
    json: Optional[Any] = None,
    headers: Optional[Dict[str, str]] = None,
    cookies: Optional[Dict[str, str]] = None,
    timeout: Optional[Union[int, float]] = None,
    verify: Optional[bool] = None,
    proxies: Optional[Dict[str, str]] = None,
    follow_redirects: bool = True,
    http2: bool = False,
    max_retry: Optional[int] = None,
    return_content: bool = False,
) -> Optional[Union[str, bytes]]:
    """
    Perform an HTTP request with retry. Returns text or bytes according to return_content.
    Returns None if all retries fail.
    """
    attempts = max_retry if max_retry is not None else _get_max_retry()

    with create_client(
        headers=headers,
        cookies=cookies,
        timeout=timeout,
        verify=verify,
        proxies=proxies,
        http2=http2,
        follow_redirects=follow_redirects,
    ) as client:
        for attempt in range(attempts):
            try:
                resp = client.request(method, url, params=params, data=data, json=json)
                resp.raise_for_status()
                return resp.content if return_content else resp.text
            except Exception:
                if attempt + 1 >= attempts:
                    break
                _sleep_with_backoff(attempt)
        return None


async def async_fetch(
    url: str,
    *,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Any] = None,
    json: Optional[Any] = None,
    headers: Optional[Dict[str, str]] = None,
    cookies: Optional[Dict[str, str]] = None,
    timeout: Optional[Union[int, float]] = None,
    verify: Optional[bool] = None,
    proxies: Optional[Dict[str, str]] = None,
    follow_redirects: bool = True,
    http2: bool = False,
    max_retry: Optional[int] = None,
    return_content: bool = False,
) -> Optional[Union[str, bytes]]:
    """
    Async HTTP request with retry. Returns text or bytes according to return_content.
    Returns None if all retries fail.
    """
    attempts = max_retry if max_retry is not None else _get_max_retry()

    async with create_async_client(
        headers=headers,
        cookies=cookies,
        timeout=timeout,
        verify=verify,
        proxies=proxies,
        http2=http2,
        follow_redirects=follow_redirects,
    ) as client:
        for attempt in range(attempts):
            try:
                resp = await client.request(method, url, params=params, data=data, json=json)
                resp.raise_for_status()
                return resp.content if return_content else resp.text
            except Exception:
                if attempt + 1 >= attempts:
                    break
                # Use same backoff logic for async by sleeping in thread (short duration)
                _sleep_with_backoff(attempt)
        return None