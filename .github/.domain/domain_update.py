# 20.04.2024

import os
import re
import time
import json
from datetime import datetime
from urllib.parse import urlparse, urlunparse


import httpx
import ua_generator


JSON_FILE_PATH = os.path.join(".github", ".domain", "domains.json")


def load_domains(file_path):
    if not os.path.exists(file_path):
        print(f"Error: The file {file_path} was not found.")
        return None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    except Exception as e:
        print(f"Error reading the file {file_path}: {e}")
        return None

def save_domains(file_path, data):
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Data successfully saved to {file_path}")

    except Exception as e:
        print(f"Error saving the file {file_path}: {e}")

def get_new_tld(full_url):
    try:
        parsed_url = urlparse(full_url)
        hostname = parsed_url.hostname
        if hostname:
            parts = hostname.split('.')
            return parts[-1]
        
    except Exception:
        pass

    return None

def try_url_with_retries(url_to_try, headers, timeout=15, retries=3, backoff_factor=0.5):
    for attempt in range(retries):
        try:
            with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True) as client:
                response = client.get(url_to_try)
                response.raise_for_status()
            return response
        
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            print(f"  [!] Attempt {attempt + 1}/{retries} for {url_to_try}: Network error ({type(e).__name__}). Retrying in {backoff_factor * (2 ** attempt)}s...")
            if attempt + 1 == retries:
                print(f"  [!] Failed all {retries} attempts for {url_to_try} due to {type(e).__name__}.")
                return None
            time.sleep(backoff_factor * (2 ** attempt))
            
        except httpx.HTTPStatusError as http_err:
            if http_err.response.status_code in [403, 429, 503]:
                print(f"  [!] HTTP error {http_err.response.status_code} for {url_to_try}. Suspected Cloudflare, checking for <base href>...")
                try:
                    with httpx.Client(headers=headers, timeout=timeout, follow_redirects=False) as cf_client:
                        cf_page_response = cf_client.get(url_to_try)
                        if cf_page_response.status_code != http_err.response.status_code and not (200 <= cf_page_response.status_code < 300) :
                            cf_page_response.raise_for_status()

                    match = re.search(r'<base\s+href="([^"]+)"', cf_page_response.text, re.IGNORECASE)
                    if match:
                        base_href_url = match.group(1)
                        parsed_base_href = urlparse(base_href_url)
                        if not parsed_base_href.scheme or not parsed_base_href.netloc:
                            original_parsed_url = urlparse(url_to_try)
                            base_href_url = urlunparse(original_parsed_url._replace(path=base_href_url if base_href_url.startswith('/') else '/' + base_href_url, query='', fragment=''))

                        print(f"    [+] Found <base href>: {base_href_url}")
                        try:
                            print(f"    [] Attempting request to <base href> URL: {base_href_url}")
                            with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True) as base_client:
                                final_response_from_base = base_client.get(base_href_url)
                                final_response_from_base.raise_for_status()
                            print(f"    [+] Successfully fetched from <base href> URL.")
                            return final_response_from_base
                        
                        except httpx.RequestError as base_req_e:
                            print(f"    [!] Error requesting <base href> URL {base_href_url}: {base_req_e}")
                            return None
                        
                    else:
                        print(f"    [!] No <base href> found in page content for {url_to_try}.")
                        return None
                    
                except httpx.RequestError as cf_req_e:
                    print(f"    [!] Error fetching Cloudflare-like page content for {url_to_try}: {cf_req_e}")
                    return None
                
            else:
                print(f"  [!] HTTP error {http_err.response.status_code} for {url_to_try}. No retry.")
                return None
            
        except httpx.RequestError as e:
            print(f"  [!] Generic error for {url_to_try}: {e}. No retry.")
            return None
        
    return None


def update_domain_entries(data):
    if not data:
        return False

    updated_count = 0

    for key, entry in data.items():
        print(f"\n--- [DOMAIN] {key} ---")
        original_full_url = entry.get("full_url")
        original_domain_in_entry = entry.get("domain")

        if not original_full_url:
            print(f"  [!] 'full_url' missing. Skipped.")
            continue

        ua = ua_generator.generate(device=('desktop', 'mobile'), browser=('chrome', 'edge', 'firefox', 'safari'))
        current_headers = ua.headers.get()

        print(f"  [] Stored URL: {original_full_url}")
        if original_domain_in_entry:
            print(f"  [] Stored Domain (TLD): {original_domain_in_entry}")

        potential_urls_to_try = []
        potential_urls_to_try.append(("Original", original_full_url))

        try:
            parsed_original = urlparse(original_full_url)
            
            current_netloc = parsed_original.netloc
            if current_netloc.startswith("www."):
                varied_netloc = current_netloc[4:]
                potential_urls_to_try.append(("Without www", urlunparse(parsed_original._replace(netloc=varied_netloc))))
            else:
                varied_netloc = "www." + current_netloc
                potential_urls_to_try.append(("With www", urlunparse(parsed_original._replace(netloc=varied_netloc))))

            current_path = parsed_original.path
            if not current_path:
                potential_urls_to_try.append(("With trailing slash", urlunparse(parsed_original._replace(path='/'))))
            elif current_path.endswith('/'):
                potential_urls_to_try.append(("Without trailing slash", urlunparse(parsed_original._replace(path=current_path[:-1]))))
            else:
                potential_urls_to_try.append(("With trailing slash", urlunparse(parsed_original._replace(path=current_path + '/'))))
            
        except Exception as e:
            print(f"  [!] Error generating URL variations: {e}")

        entry_updated_in_this_run = False
        
        seen_urls_for_entry = set()
        unique_potential_urls = []
        for label, url_val in potential_urls_to_try:
            if url_val not in seen_urls_for_entry:
                unique_potential_urls.append((label, url_val))
                seen_urls_for_entry.add(url_val)
        
        parsed_original_for_http_check = urlparse(original_full_url)
        if parsed_original_for_http_check.scheme == 'https':
            http_url = urlunparse(parsed_original_for_http_check._replace(scheme='http'))
            if http_url not in seen_urls_for_entry:
                unique_potential_urls.append(("HTTP Fallback", http_url))

        for label, url_to_check in unique_potential_urls:
            if entry_updated_in_this_run:
                break
            
            print(f"  [] Testing URL ({label}): {url_to_check}")
            response = try_url_with_retries(url_to_check, current_headers)

            if response:
                final_url_from_request = str(response.url)
                print(f"    [+] Redirect/Response to: {final_url_from_request}")

                parsed_final_url = urlparse(final_url_from_request)
                normalized_full_url = urlunparse(parsed_final_url._replace(path='/', params='', query='', fragment=''))
                if parsed_final_url.path == '' and not normalized_full_url.endswith('/'):
                    normalized_full_url += '/'
                
                if normalized_full_url != final_url_from_request:
                    print(f"    [+] Normalized URL: {normalized_full_url}")

                if normalized_full_url != original_full_url:
                    new_tld_val = get_new_tld(final_url_from_request)
                    
                    if new_tld_val:
                        entry["full_url"] = normalized_full_url
                        
                        if new_tld_val != original_domain_in_entry:
                            print(f"    [-] Domain TLD Changed: '{original_domain_in_entry}' -> '{new_tld_val}'")
                            entry["old_domain"] = original_domain_in_entry if original_domain_in_entry else entry.get("old_domain", "")
                            entry["domain"] = new_tld_val
                            entry["time_change"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            print(f"    [-] Domain & URL Updated: New TLD '{new_tld_val}', New URL '{normalized_full_url}'")

                        else:
                            entry["domain"] = new_tld_val
                            print(f"    [-] URL Updated (TLD Unchanged '{new_tld_val}'): New URL '{normalized_full_url}'")
                        
                        updated_count += 1
                        entry_updated_in_this_run = True

                    else:
                        print(f"    [!] Could not extract TLD from {final_url_from_request}. URL not updated despite potential change.")
                else:
                    if final_url_from_request != original_full_url:
                        print(f"    [] Same Domain (after normalization): {final_url_from_request} -> {normalized_full_url}")

                    else:
                        print(f"    [] Same Domain: {final_url_from_request}")
                    
                    if label == "Original" or normalized_full_url == original_full_url :
                        entry_updated_in_this_run = True

        if not entry_updated_in_this_run:
            print(f"  [-] No Update for {key} after {len(unique_potential_urls)} attempts.")
        
    return updated_count > 0

def main():
    print("Starting domain update script...")
    domain_data = load_domains(JSON_FILE_PATH)

    if domain_data:
        if update_domain_entries(domain_data):
            save_domains(JSON_FILE_PATH, domain_data)
            print("\nUpdate complete. Some entries were modified.")

        else:
            print("\nUpdate complete. No domains were modified.")

    else:
        print("\nCannot proceed without domain data.")
    
    print("Script finished.")

if __name__ == "__main__":
    main()