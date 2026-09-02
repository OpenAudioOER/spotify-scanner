import os
import sys
import json
import base64
from datetime import datetime, timezone
import requests

SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"

SHOWS_FILE = "shows.json"
STATUS_FILE = "status.json"
PREV_STATUS_FILE = "prev_status.json"

def get_spotify_access_token(client_id: str, client_secret: str) -> str:
    """Authenticates with Spotify API using Client Credentials flow."""
    auth_header = base64.b64encode(f"{client_id.strip()}:{client_secret.strip()}".encode('utf-8')).decode('utf-8')
    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"grant_type": "client_credentials"}
    
    response = requests.post(SPOTIFY_TOKEN_URL, data=data, headers=headers)
    if response.status_code != 200:
        print(f"❌ Spotify Authentication Error ({response.status_code}): {response.text}")
        response.raise_for_status()
        
    return response.json()["access_token"]

def fetch_show_episodes(access_token: str, show_id: str, market: str = "US"):
    """Fetches all episodes/chapters for a given Spotify Show ID."""
    headers = {"Authorization": f"Bearer {access_token}"}
    episodes = []
    url = f"{SPOTIFY_API_BASE}/shows/{show_id}/episodes?market={market}&limit=50"
    
    while url:
        res = requests.get(url, headers=headers)
        if res.status_code == 404:
            print(f"⚠️ Show ID '{show_id}' not found (404).")
            return None, []
        res.raise_for_status()
        data = res.json()
        
        for item in data.get("items", []):
            if item is None:
                continue
            is_playable = item.get("is_playable", True)
            restrictions = item.get("restrictions", {})
            reason = restrictions.get("reason", "None" if is_playable else "Unplayable/Flagged")
            
            episodes.append({
                "id": item["id"],
                "name": item["name"],
                "release_date": item.get("release_date"),
                "duration_ms": item.get("duration_ms"),
                "is_playable": is_playable,
                "reason": reason,
                "external_url": item.get("external_urls", {}).get("spotify")
            })
            
        url = data.get("next")
        
    return True, episodes

def fetch_playlist_tracks(access_token: str, playlist_id: str, market: str = "US"):
    """Fetches all tracks/episodes from a Spotify Playlist ID."""
    headers = {"Authorization": f"Bearer {access_token}"}
    items_list = []
    url = f"{SPOTIFY_API_BASE}/playlists/{playlist_id}/tracks?market={market}&limit=50"
    
    while url:
        res = requests.get(url, headers=headers)
        if res.status_code == 404:
            print(f"⚠️ Playlist ID '{playlist_id}' not found (404).")
            return None, []
        res.raise_for_status()
        data = res.json()
        
        for entry in data.get("items", []):
            track = entry.get("track")
            if not track:
                continue
            is_playable = track.get("is_playable", True)
            restrictions = track.get("restrictions", {})
            reason = restrictions.get("reason", "None" if is_playable else "Unplayable/Flagged")
            
            items_list.append({
                "id": track["id"],
                "name": track["name"],
                "release_date": track.get("album", {}).get("release_date"),
                "duration_ms": track.get("duration_ms"),
                "is_playable": is_playable,
                "reason": reason,
                "external_url": track.get("external_urls", {}).get("spotify")
            })
            
        url = data.get("next")
        
    return True, items_list

def send_resend_alert(api_key: str, to_email: str, from_email: str, newly_offline: list):
    """Sends email alert via Resend when chapters are flagged/offline."""
    subject = f"🚨 OpenAudio Alert: {len(newly_offline)} Spotify Chapter(s) Offline!"
    
    rows = ""
    for item in newly_offline:
        rows += f"""
        <tr>
          <td style="padding: 10px; border-bottom: 1px solid #eee;"><strong>{item['show_name']}</strong></td>
          <td style="padding: 10px; border-bottom: 1px solid #eee;">{item['name']}</td>
          <td style="padding: 10px; border-bottom: 1px solid #eee; color: #d9534f; font-weight: bold;">{item['reason']}</td>
          <td style="padding: 10px; border-bottom: 1px solid #eee;"><a href="{item.get('external_url', '#')}">Link</a></td>
        </tr>
        """
        
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
      <div style="background-color: #d9534f; color: white; padding: 20px; text-align: center;">
        <h2 style="margin: 0;">🚨 Spotify Chapter Offline Alert</h2>
        <p style="margin: 5px 0 0 0;">OpenAudio Availability Audit</p>
      </div>
      
      <div style="padding: 20px; background-color: #ffffff;">
        <p>The daily Spotify audit detected that the following <strong>{len(newly_offline)} chapter(s)</strong> are currently unplayable or flagged:</p>
        
        <table style="width: 100%; border-collapse: collapse; text-align: left; margin-top: 15px;">
          <thead>
            <tr style="background-color: #f8f9fa;">
              <th style="padding: 10px; border-bottom: 2px solid #ddd;">Show / Book</th>
              <th style="padding: 10px; border-bottom: 2px solid #ddd;">Chapter Title</th>
              <th style="padding: 10px; border-bottom: 2px solid #ddd;">Issue Reason</th>
              <th style="padding: 10px; border-bottom: 2px solid #ddd;">Link</th>
            </tr>
          </thead>
          <tbody>
            {rows}
          </tbody>
        </table>
        
        <p style="margin-top: 25px; font-size: 13px; color: #777;">Check your Spotify Creator Dashboard or distribution partner for copyright notifications.</p>
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
    client_id = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
    resend_api_key = os.environ.get("RESEND_API_KEY", "").strip()
    to_email = os.environ.get("ALERT_TO_EMAIL", "").strip()
    from_email = os.environ.get("ALERT_FROM_EMAIL", "onboarding@resend.dev").strip()
    
    if not client_id or not client_secret:
        print("❌ Error: SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables are required.")
        sys.exit(1)
        
    if not os.path.exists(SHOWS_FILE):
        print(f"❌ Error: {SHOWS_FILE} not found.")
        sys.exit(1)
        
    with open(SHOWS_FILE, "r") as f:
        shows_config = json.load(f)
        
    print(f"Authenticating with Spotify API...")
    access_token = get_spotify_access_token(client_id, client_secret)
    print("✅ Authenticated with Spotify successfully.")
    
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
    
    for show_item in shows_config:
        show_name = show_item["name"]
        spotify_id = show_item["spotify_id"]
        id_type = show_item.get("type", "show").lower()  # "show" or "playlist"
        
        print(f"\nScanning {id_type.upper()}: '{show_name}' (ID: {spotify_id})...")
        
        if spotify_id.startswith("REPLACE_WITH"):
            print("⚠️ Placeholder Spotify ID detected. Skipping.")
            continue
            
        if id_type == "playlist":
            found, episodes = fetch_playlist_tracks(access_token, spotify_id)
        else:
            found, episodes = fetch_show_episodes(access_token, spotify_id)
            
        if not found:
            print(f"❌ Could not fetch content for '{show_name}'.")
            continue
            
        show_online = 0
        show_offline = 0
        processed_episodes = []
        
        for ep in episodes:
            audit_results["total_chapters"] += 1
            if ep["is_playable"]:
                audit_results["online_chapters"] += 1
                show_online += 1
            else:
                audit_results["offline_chapters"] += 1
                show_offline += 1
                # Check if newly offline
                if ep["id"] not in prev_offline_ids:
                    newly_offline_list.append({
                        "show_name": show_name,
                        "name": ep["name"],
                        "reason": ep["reason"],
                        "external_url": ep["external_url"]
                    })
            processed_episodes.append(ep)
            
        print(f"  Summary for '{show_name}': {show_online} Online, {show_offline} Offline (Total {len(episodes)})")
        
        audit_results["shows"].append({
            "name": show_name,
            "spotify_id": spotify_id,
            "type": id_type,
            "total": len(episodes),
            "online": show_online,
            "offline": show_offline,
            "episodes": processed_episodes
        })
        
    # Save updated status.json
    with open(STATUS_FILE, "w") as f:
        json.dump(audit_results, f, indent=2)
    print(f"\nSaved updated audit results to '{STATUS_FILE}'.")
    
    print("\n--- AUDIT OVERALL SUMMARY ---")
    print(f"Total Chapters Audited: {audit_results['total_chapters']}")
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
