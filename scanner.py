import os
import sys
import json
import re
from datetime import datetime, timezone
import requests

SHOWS_FILE = "shows.json"
STATUS_FILE = "status.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def audit_spotify_episode(spotify_url: str):
    """Scrapes individual Spotify web page to check if episode is online or unplayable/deleted."""
    try:
        res = requests.get(spotify_url, headers=HEADERS, timeout=10)
        if res.status_code == 404:
            return False, "404 Not Found (Deleted/Removed)"
        elif res.status_code >= 500:
            return False, f"Spotify Server Error (HTTP {res.status_code})"
        elif res.status_code != 200:
            return False, f"HTTP Status {res.status_code}"
            
        html = res.text.lower()
        if "content not available" in html or "this content is unavailable" in html or "page not found" in html:
            return False, "Content Unavailable on Spotify Web Player"
            
        return True, "None"
    except Exception as e:
        return False, f"Network Error: {e}"

def send_resend_alert(api_key: str, to_email: str, from_email: str, newly_offline: list):
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
              <th style="padding: 10px; border-bottom: 2px solid #ddd;">Show / Book</th>
              <th style="padding: 10px; border-bottom: 2px solid #ddd;">Expected Chapter Title</th>
              <th style="padding: 10px; border-bottom: 2px solid #ddd;">Status / Reason</th>
              <th style="padding: 10px; border-bottom: 2px solid #ddd;">Link</th>
            </tr>
          </thead>
          <tbody>
            {rows}
          </tbody>
        </table>
      </div>
    </div>
    """
    
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json"
    }
    payload = {
        "from": from_email.strip(),
        "to": [to_email.strip()],
        "subject": subject,
        "html": html_content
    }
    
    res = requests.post("https://api.resend.com/emails", json=payload, headers=headers)
    res.raise_for_status()
    print(f"✅ Alert email sent successfully to {to_email}!")

def load_previous_status():
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not read previous status.json: {e}")
    return {}

def main():
    resend_api_key = os.environ.get("RESEND_API_KEY", "").strip()
    to_email = os.environ.get("ALERT_TO_EMAIL", "").strip()
    from_email = os.environ.get("ALERT_FROM_EMAIL", "onboarding@resend.dev").strip()
    
    if not os.path.exists(SHOWS_FILE):
        print(f"❌ Error: {SHOWS_FILE} not found.")
        sys.exit(1)
        
    with open(SHOWS_FILE, "r") as f:
        shows_config = json.load(f)
        
    prev_data = load_previous_status()
    prev_offline_ids = set()
    for prev_show in prev_data.get("shows", []):
        for ch in prev_show.get("episodes", []):
            if not ch.get("is_playable"):
                prev_offline_ids.add(ch["id"])
                
    audit_results = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total_shows": len(shows_config),
        "total_chapters": 0,
        "online_chapters": 0,
        "offline_chapters": 0,
        "shows": []
    }
    
    newly_offline_list = []
    
    for show in shows_config:
        show_name = show.get("name", "Unnamed Show")
        expected_episodes = show.get("expected_episodes", [])
        
        print(f"\nAuditing Show: '{show_name}' ({len(expected_episodes)} baseline chapters)...")
        
        show_online = 0
        show_offline = 0
        processed_episodes = []
        
        for idx, exp_ep in enumerate(expected_episodes, start=1):
            ep_id = exp_ep.get("id", f"ep_{idx}")
            title = exp_ep.get("title", f"Chapter {idx}")
            spotify_url = exp_ep.get("spotify_url", "")
            
            is_playable, reason = audit_spotify_episode(spotify_url)
                    
            audit_results["total_chapters"] += 1
            if is_playable:
                audit_results["online_chapters"] += 1
                show_online += 1
            else:
                audit_results["offline_chapters"] += 1
                show_offline += 1
                if ep_id not in prev_offline_ids:
                    newly_offline_list.append({
                        "show_name": show_name,
                        "title": title,
                        "reason": reason,
                        "url": spotify_url
                    })
                    
            processed_episodes.append({
                "id": ep_id,
                "name": title,
                "is_playable": is_playable,
                "reason": reason,
                "external_url": spotify_url
            })
            
        print(f"  Summary for '{show_name}': {show_online} Online, {show_offline} Offline (Total {len(expected_episodes)})")
        
        audit_results["shows"].append({
            "name": show_name,
            "total": len(expected_episodes),
            "online": show_online,
            "offline": show_offline,
            "episodes": processed_episodes
        })
        
    with open(STATUS_FILE, "w") as f:
        json.dump(audit_results, f, indent=2)
    print(f"\nSaved updated audit results to '{STATUS_FILE}'.")
    
    print("\n--- AUDIT OVERALL SUMMARY ---")
    print(f"Total Baseline Chapters Audited: {audit_results['total_chapters']}")
    print(f"Online: {audit_results['online_chapters']} 🟢")
    print(f"Offline / Flagged: {audit_results['offline_chapters']} 🔴")
    print("------------------------------")
    
    if newly_offline_list and resend_api_key and to_email:
        print(f"🔔 {len(newly_offline_list)} NEW offline chapter(s) detected! Sending Resend email alert...")
        try:
            send_resend_alert(resend_api_key, to_email, from_email, newly_offline_list)
        except Exception as e:
            print(f"❌ Error sending Resend alert: {e}")
            sys.exit(1)
    elif newly_offline_list:
        print(f"⚠️ {len(newly_offline_list)} NEW offline chapter(s) detected, but RESEND_API_KEY/ALERT_TO_EMAIL missing. Skipping email.")
    else:
        print("No new offline chapters detected. All good!")

if __name__ == "__main__":
    main()
