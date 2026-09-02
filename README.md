# OpenAudio Spotify Chapter Status Scanner 🎧

Automated daily availability scanner and web dashboard for **OpenAudio Spotify Audiobooks & Chapters**.

Detects copyright flags, region blocks, and unplayable chapters across your Spotify shows, and sends an email alert via **Resend** whenever a chapter goes offline.

---

## 🌐 Web Dashboard
Once GitHub Pages is enabled on this repo, your status dashboard will be live at:  
👉 `https://openaudiooer.github.io/spotify-scanner/`

---

## 🛠️ How to Add Your Spotify Shows & Playlists

Edit [`shows.json`](shows.json) in this repository and add your Spotify Show or Playlist IDs:

```json
[
  {
    "name": "American Government 3e",
    "spotify_id": "4rvc...YOUR_SPOTIFY_SHOW_ID",
    "type": "show"
  },
  {
    "name": "US History Playlist",
    "spotify_id": "37i9...YOUR_SPOTIFY_PLAYLIST_ID",
    "type": "playlist"
  }
]
```

### How to get a Spotify Show/Playlist ID:
1. Open the podcast/show or playlist on Spotify.
2. Click **Share -> Copy link to show**.
3. The URL looks like: `https://open.spotify.com/show/4rvcX123456789`
4. Copy the string after `/show/` (or `/playlist/`): `4rvcX123456789`.

---

## 🔑 Setup GitHub Secrets

Go to **Settings -> Secrets and variables -> Actions -> New repository secret**:

| Secret Name | Description |
| :--- | :--- |
| **`SPOTIFY_CLIENT_ID`** | Client ID from your free [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) |
| **`SPOTIFY_CLIENT_SECRET`** | Client Secret from your Spotify Developer Dashboard |
| **`RESEND_API_KEY`** | Resend API key (`re_...`) from [Resend.com](https://resend.com) |
| **`ALERT_TO_EMAIL`** | Email address to receive alerts when chapters go offline |

---

## 🌐 Enabling GitHub Pages (Web Dashboard)

1. Go to **Settings -> Pages** in this repository.
2. Under **Build and deployment -> Source**, select **Deploy from a branch**.
3. Choose **Branch: `main` / Folder: `/ (root)`** and click **Save**.
