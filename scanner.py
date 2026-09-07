import os
import sys
import json
import re
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

SHOWS_FILE = "shows.json"
STATUS_FILE = "status.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9"
}

def audit_spotify_episode(episode_id_or_url: str):
    """
    Auditor for Spotify episodes with rate-limit protection and exponential backoff.
    Specifically checks for copyright takedowns ('Sorry, that's not currently available')
    and 404 deletions ('Page not found').
    """
    if "episode/" in episode_id_or_url:
        episode_id = episode_id_or_url.split("episode/")[1].split("?")[0]
    else:
        episode_id = episode_id_or_url

    embed_url = f"https://open.spotify.com/embed/episode/{episode_id}"

    max_retries = 3
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(embed_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as resp:
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

                # Check HTML text for fallback error titles
                if "not currently available" in html.lower():
                    return False, "403 Offline (Copyright / Legal Takedown)"
                elif "page not found" in html.lower():
                    return False, "404 Not Found (Deleted / Removed)"

                return True, "Online"
                
        except urllib.error.HTTPError as e:
            if e.code in [429, 403] and attempt < max_retries - 1:
                # Rate limited or Cloud WAF challenge -> Wait and retry
                time.sleep(1.5 * (attempt + 1))
                continue
            elif e.code == 404:
                return False, "404 Not Found (Deleted)"
            return False, f"HTTP Error {e.code}"
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1.0)
                continue

    return True, "Online"

def send_resend_alert(api_key: str, to_email: str, from_email: str, newly_offline: list):
    """Sends an HTML alert email via Resend API using standard urllib."""
    subject = f"🚨 OpenAudio Alert: {len(newly_offline)} Spotify Chapter(s) Offline!"
    
    rows = ""
    for item in newly_offline:
        rows += f"""
        <tr>
          <td style="padding: 10px; border-bottom: 1px solid #eee;"><strong>{item['show_name']}</strong></td>
          <td style="padding: 10px; border-bottom: 1px solid #eee;">{item['title']}</td>
          <td style="padding: 10px; border-bottom: 1px solid #eee; color: #d9534f; font-weight: bold;">{item['reason']}</td>
          <td style="padding: 10px; border-bottom: 1px solid #eee;"><a href="{item.get('url', '#')}">Link</a></td>
        </tr>
        """
        
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
      <div style="background-color: #d9534f; color: white; padding: 20px; text-align: center;">
        <h2 style="margin: 0;">🚨 Spotify Chapter Offline Alert</h2>
        <p style="margin: 5px 0 0 0;">OpenAudio Daily Master Audit</p>
      </div>
      
      <div style="padding: 20px; background-color: #ffffff;">
        <p>The daily audit detected that <strong>{len(newly_offline)} baseline chapter(s)</strong> are unplayable or taken down:</p>
        
        <table style="width: 100%; border-collapse: collapse; text-align: left; margin-top: 15px;">
          <thead>
            <tr style="background-color: #f8f9fa;">
              <th style="padding: 10px; border-bottom: 2px solid #ccc;">Show</th>
              <th style="padding: 10px; border-bottom: 2px solid #ccc;">Chapter</th>
              <th style="padding: 10px; border-bottom: 2px solid #ccc;">Status</th>
              <th style="padding: 10px; border-bottom: 2px solid #ccc;">Link</th>
            </tr>
          </thead>
          <tbody>
            {rows}
          </tbody>
        </table>
      </div>
    </div>
    """

    resend_url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": html_content
    }

    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(resend_url, data=data_bytes, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in [200, 201]:
                print(f"Successfully sent email alert to {to_email} via Resend!")
            else:
                print(f"Resend email response HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        print(f"Failed to send email alert via Resend (HTTP {e.code}): {e.read().decode('utf-8')}")
    except Exception as e:
        print(f"Error sending Resend email: {e}")

def main():
    if not os.path.exists(SHOWS_FILE):
        print(f"Error: {SHOWS_FILE} not found!")
        sys.exit(1)

    with open(SHOWS_FILE, "r", encoding="utf-8") as f:
        shows = json.load(f)

    audit_timestamp = datetime.now(timezone.utc).isoformat()
    status_output = {
        "last_updated": audit_timestamp,
        "total_shows": len(shows),
        "total_episodes": 0,
        "total_online": 0,
        "total_offline": 0,
        "shows": []
    }

    newly_offline = []

    print(f"Starting Spotify Audit at {audit_timestamp}...")

    for show in shows:
        show_name = show.get("name", "Unknown Show")
        episodes = show.get("expected_episodes", [])
        print(f"Auditing Show: '{show_name}' ({len(episodes)} chapters)...")

        show_online_count = 0
        show_offline_count = 0
        audited_episodes = []

        for ep in episodes:
            ep_id = ep.get("id")
            ep_title = ep.get("title", f"Episode {ep_id}")
            ep_url = ep.get("spotify_url", f"https://open.spotify.com/episode/{ep_id}")

            is_online, reason = audit_spotify_episode(ep_url)

            if is_online:
                show_online_count += 1
                status_output["total_online"] += 1
                clean_reason = "Online"
            else:
                show_offline_count += 1
                status_output["total_offline"] += 1
                clean_reason = reason
                newly_offline.append({
                    "show_name": show_name,
                    "title": ep_title,
                    "reason": clean_reason,
                    "url": ep_url
                })

            audited_episodes.append({
                "id": ep_id,
                "title": ep_title,
                "url": ep_url,
                "online": is_online,
                "reason": clean_reason
            })

            status_output["total_episodes"] += 1
            
            # Politeness delay to prevent cloud IP rate limiting
            time.sleep(0.25)

        print(f"Summary for '{show_name}': {show_online_count} Online, {show_offline_count} Offline")

        status_output["shows"].append({
            "name": show_name,
            "total": len(episodes),
            "online": show_online_count,
            "offline": show_offline_count,
            "episodes": audited_episodes
        })

    # Save to status.json
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status_output, f, indent=2)

    print(f"\nSaved updated audit results to '{STATUS_FILE}'.")
    print("--- AUDIT OVERALL SUMMARY ---")
    print(f"Total Chapters Audited: {status_output['total_episodes']}")
    print(f"Online: {status_output['total_online']} 🟢")
    print(f"Offline / Flagged: {status_output['total_offline']} 🔴")
    print("------------------------------")

    # Send Resend Alert if offline episodes detected
    resend_api_key = os.environ.get("RESEND_API_KEY")
    alert_to_email = os.environ.get("ALERT_TO_EMAIL")
    alert_from_email = os.environ.get("ALERT_FROM_EMAIL", "onboarding@resend.dev")

    if newly_offline:
        print(f"\n🚨 Detected {len(newly_offline)} OFFLINE chapter(s):")
        for item in newly_offline:
            print(f" - [{item['show_name']}] {item['title']} -> {item['reason']}")

        if resend_api_key and alert_to_email:
            send_resend_alert(resend_api_key, alert_to_email, alert_from_email, newly_offline)
        else:
            print("Notice: RESEND_API_KEY or ALERT_TO_EMAIL environment variables not set; skipping email notification.")
    else:
        print("All audited chapters are Online! No alerts sent.")

if __name__ == "__main__":
    main()
