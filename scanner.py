import urllib.request
import re
import json

def audit_spotify_episode(episode_id_or_url: str):
    """
    Zero-API-key auditor for Spotify episodes.
    Checks Spotify Embed status to detect 403 copyright claims and 404 deletions.
    """
    # Extract episode ID if full URL passed
    if "episode/" in episode_id_or_url:
        episode_id = episode_id_or_url.split("episode/")[1].split("?")[0]
    else:
        episode_id = episode_id_or_url

    embed_url = f"https://open.spotify.com/embed/episode/{episode_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        req = urllib.request.Request(embed_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8")
            
            # Extract Next.js data JSON payload
            match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
            if match:
                data = json.loads(match.group(1))
                page_props = data.get("props", {}).get("pageProps", {})
                status = page_props.get("status")
                title = page_props.get("title", "")

                if status == 403 or "not currently available" in title.lower():
                    return False, "403 Offline (Copyright / Legal Takedown)"
                elif status == 404 or "page not found" in title.lower():
                    return False, "404 Not Found (Deleted / Removed)"
                elif status == 200:
                    return True, "Online"
                else:
                    return False, f"HTTP Status {status}"

            return True, "Online"
            
    except urllib.error.HTTPError as e:
        if e.code == 403:
            return False, "403 Offline (Copyright Takedown)"
        elif e.code == 404:
            return False, "404 Not Found (Deleted)"
        return False, f"HTTP Error {e.code}"
    except Exception as e:
        return False, f"Network Error: {e}"
