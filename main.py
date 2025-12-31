import requests
import time
import os
from datetime import datetime
import pytz

# ---------------- CONFIG ----------------
ROBLOX_USER_IDS = ["761047329", "3570016078", "417699108", "8082787633", "8406734576", "7851813003"]
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
CHECK_INTERVAL = 20  # seconds
TIMEZONE = pytz.timezone("Europe/Berlin")
UPDATE_INTERVAL = 5  # seconds between live duration edits
# ---------------------------------------

last_status = {uid: None for uid in ROBLOX_USER_IDS}
offline_counter = {uid: 0 for uid in ROBLOX_USER_IDS}
online_since = {}
playing_since = {}
session_history = {uid: [] for uid in ROBLOX_USER_IDS}
last_online_duration = {}

# Store Discord message IDs for live updates
discord_messages = {}
last_update = {}

# ---------------- KNOWN GAMES ----------------
GAME_IDS = {
    "920587237": "Adopt Me!",
    "4924922222": "Brookhaven 🏡RP",
    "4442272183": "Blox Fruits",
    "1962086868": "Tower of Hell",
    "142823291": "Murder Mystery 2"
}
# ---------------------------------------------

def get_now():
    return datetime.now(TIMEZONE)

def format_duration(seconds):
    mins, sec = divmod(seconds, 60)
    hrs, mins = divmod(mins, 60)
    if hrs > 0:
        return f"{hrs}h {mins}m {sec}s"
    elif mins > 0:
        return f"{mins}m {sec}s"
    else:
        return f"{sec}s"

def get_game_name(place_id, last_location):
    if place_id and str(place_id) in GAME_IDS:
        return GAME_IDS[str(place_id)]
    if place_id:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            url = f"https://games.roblox.com/v1/games/multiget-place-details?placeIds={place_id}"
            response = requests.get(url, headers=headers, timeout=5).json()
            data = response.get("data", [])
            if data and isinstance(data, list):
                return data[0].get("name", last_location)
        except:
            pass
    if last_location:
        return last_location
    return "Unknown"

def get_avatar_url(user_id):
    try:
        # Smaller size: 150x150
        url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=150x150&format=Png&isCircular=false"
        response = requests.get(url, timeout=5).json()
        data = response.get("data", [])
        if data:
            return data[0].get("imageUrl", "")
    except:
        pass
    return f"https://www.roblox.com/headshot-thumbnail/image?userId={user_id}&width=150&height=150&format=png"

def send_discord_notification(user_id, status, extra, emoji, place_id=None):
    if not DISCORD_WEBHOOK_URL:
        return None
    
    avatar_url = get_avatar_url(user_id)
    try:
        info = requests.get(f"https://users.roblox.com/v1/users/{user_id}").json()
        username = info.get("name", "Unknown")
    except:
        username = "Unknown"

    timestamp = get_now().strftime("%Y-%m-%d %H:%M:%S")
    thumbnail_url = avatar_url
    if place_id:
        thumbnail_url = f"https://www.roblox.com/asset-thumbnail/image?assetId={place_id}&width=150&height=150&format=png"

    # Make status text bigger using Markdown headers
    display_status = f"## {status}"
    
    embed = {
        "title": f"{emoji} {username} Status Update",
        "description": f"{display_status}{extra}\n**Last Updated:** {timestamp}",
        "thumbnail": {"url": avatar_url},
        "color": 3447003 if status == "Online" else 3066993 if status in ["In Game", "In Studio"] else 15158332
    }
    try:
        webhook_url = DISCORD_WEBHOOK_URL
        if "?" not in webhook_url:
            webhook_url += "?wait=true"
        else:
            webhook_url += "&wait=true"
            
        response = requests.post(webhook_url, json={"embeds":[embed]}, timeout=5).json()
        return response.get("id")
    except:
        return None

def check_status():
    global last_status, online_since, last_online_duration, session_history
    try:
        url = "https://presence.roblox.com/v1/presence/users"
        data = {"userIds": [int(uid) for uid in ROBLOX_USER_IDS]}
        response = requests.post(url, json=data, timeout=15).json()
    except Exception as e:
        print(f"Error checking status: {e}")
        return

    for uid in ROBLOX_USER_IDS:
        pres = next((p for p in response.get("userPresences", []) if str(p["userId"]) == uid), None)
        status_code = pres.get("userPresenceType", 0) if pres else 0
        place_id = pres.get("placeId") if pres else None
        last_location = pres.get("lastLocation") if pres else None

        if status_code == 1:
            status = "Online"; emoji = "💙"
        elif status_code == 2:
            status = "In Game"; emoji = "💚"
        elif status_code == 3:
            status = "In Studio"; emoji = "📳"
        else:
            status = "Offline"; emoji = "❤️"

        # Glitch Prevention: If detected offline, wait for 300 consecutive offline reports (~100 minutes)
        if status == "Offline" and last_status.get(uid) != "Offline" and last_status.get(uid) is not None:
            offline_counter[uid] += 1
            if offline_counter[uid] < 300:
                status = last_status[uid]
                if status == "Online": emoji = "💙"
                elif status == "In Game": emoji = "💚"
                elif status == "In Studio": emoji = "📳"
        else:
            offline_counter[uid] = 0

        extra = ""
        now = get_now()

        # Update Session Timing
        if status in ["In Game", "In Studio"]:
            game_name = get_game_name(place_id, last_location)
            if not game_name or game_name.lower() in ["studio", "play roblox"]:
                game_name = last_location or "Unknown"
            
            if game_name:
                extra += f"\n**Game Name:** {game_name}"
            
            if uid not in playing_since:
                playing_since[uid] = {"start": now, "name": game_name, "place_id": place_id}
            
            curr_playing = format_duration(int((now - playing_since[uid]["start"]).total_seconds()))
            extra += f"\n**Session Duration:** {curr_playing}"
        else:
            if uid in playing_since:
                dur = format_duration(int((now - playing_since[uid]["start"]).total_seconds()))
                session_history[uid].append(f"{playing_since[uid]['name']}: {dur}")
                playing_since.pop(uid)

        # Show Session History
        if session_history[uid]:
            extra += "\n\n**Session History:**"
            for s in session_history[uid]:
                extra += f"\n└ {s}"

        # Update Online Timing
        if status != "Offline":
            if not online_since.get(uid):
                online_since[uid] = now
            online_duration = format_duration(int((now - online_since[uid]).total_seconds()))
            extra += f"\n**Total Online Duration:** {online_duration}"
            last_online_duration[uid] = online_duration
        else:
            if online_since.get(uid):
                online_duration = format_duration(int((now - online_since[uid]).total_seconds()))
                extra += f"\n**Was Online For:** {online_duration}"
                online_since[uid] = None
                # Clear history for next online period
                # session_history[uid] = [] # Wait until status changed is handled
            elif last_online_duration.get(uid):
                extra += f"\n**Was Online For:** {last_online_duration[uid]}"

        if last_status.get(uid) != status:
            message_id = send_discord_notification(uid, status, extra, emoji, place_id if status in ["In Game", "In Studio"] else None)
            if status == "Offline":
                if uid in discord_messages:
                    del discord_messages[uid]
                session_history[uid] = [] # Clear history on complete logoff
            else:
                if message_id:
                    discord_messages[uid] = message_id
            last_status[uid] = status

def startup_summary():
    try:
        url = "https://presence.roblox.com/v1/presence/users"
        data = {"userIds": [int(uid) for uid in ROBLOX_USER_IDS]}
        response = requests.post(url, json=data, timeout=5).json()
    except:
        return

    summary_lines = []
    now = get_now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    for uid in ROBLOX_USER_IDS:
        pres = next((p for p in response.get("userPresences", []) if str(p["userId"]) == uid), None)
        status_code = pres.get("userPresenceType", 0) if pres else 0
        place_id = pres.get("placeId") if pres else None
        last_location = pres.get("lastLocation") if pres else None

        if status_code == 1:
            status = "Online"; emoji = "💙"
        elif status_code == 2:
            status = "In Game"; emoji = "💚"
        elif status_code == 3:
            status = "In Studio"; emoji = "📳"
        else:
            status = "Offline"; emoji = "❤️"

        extra = ""
        if status in ["In Game", "In Studio"]:
            game_name = get_game_name(place_id, last_location)
            if not game_name or game_name.lower() in ["studio", "play roblox"]:
                game_name = last_location or "Unknown"
            if game_name: extra += f"\n**Game Name:** {game_name}"
            playing_since[uid] = {"start": now, "name": game_name}
            extra += f"\n**Session Duration:** 0s"

        if status != "Offline":
            online_since[uid] = now
            extra += f"\n**Total Online Duration:** 0s"
        else:
            if last_online_duration.get(uid):
                extra += f"\n**Was Online For:** {last_online_duration[uid]}"

        try:
            info = requests.get(f"https://users.roblox.com/v1/users/{uid}").json()
            username = info.get("name", "Unknown")
        except:
            username = "Unknown"

        summary_lines.append(f"{emoji} {username}: {status}{extra}")

    if summary_lines and DISCORD_WEBHOOK_URL:
        description = "\n\n".join(summary_lines)
        embed = {
            "title": "Startup Summary",
            "description": f"{description}\n**Last Updated:** {timestamp}",
            "color": 16776960
        }
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={"embeds":[embed]}, timeout=5)
        except:
            pass

# ---------------- MAIN LOOP ----------------
if DISCORD_WEBHOOK_URL:
    try: requests.post(DISCORD_WEBHOOK_URL, json={"content": "🟡 Roblox watcher started successfully"})
    except: pass
startup_summary()
time.sleep(1)

while True:
    check_status()
    now = get_now()
    for uid, message_id in list(discord_messages.items()):
        if uid in online_since and online_since[uid] is not None:
            last_edit = last_update.get(uid)
            if last_edit and (now - last_edit).total_seconds() < UPDATE_INTERVAL:
                continue

            online_duration = format_duration(int((now - online_since[uid]).total_seconds()))
            current_status = last_status.get(uid, "Online")
            extra = f"\n**Total Online Duration:** {online_duration}"
            
            if uid in playing_since:
                play_duration = format_duration(int((now - playing_since[uid]["start"]).total_seconds()))
                extra += f"\n**Session Duration:** {play_duration}"

            if session_history[uid]:
                extra += "\n\n**Session History:**"
                for s in session_history[uid]:
                    extra += f"\n└ {s}"

            try:
                # Use official thumbnails API
                avatar_url = get_avatar_url(uid)
                info = requests.get(f"https://users.roblox.com/v1/users/{uid}").json()
                username = info.get("name", "Unknown")
                
                # Check for place icon if playing
                current_status = last_status.get(uid)
                thumbnail_url = avatar_url
                if uid in playing_since and playing_since[uid].get('place_id'):
                    thumbnail_url = f"https://www.roblox.com/asset-thumbnail/image?assetId={playing_since[uid]['place_id']}&width=150&height=150&format=png"

                # Bigger status text
                display_status = f"## {current_status}"

                embed = {
                    "title": f"💙 {username} Status Update" if current_status == "Online" else f"💚 {username} Status Update",
                    "description": f"{display_status}{extra}\n**Last Updated:** {get_now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "thumbnail": {"url": avatar_url},
                    "color": 3447003 if current_status == "Online" else 3066993
                }
                requests.patch(f"{DISCORD_WEBHOOK_URL}/messages/{message_id}", json={"embeds":[embed]}, timeout=5)
                last_update[uid] = now
            except:
                discord_messages.pop(uid, None)
    time.sleep(1)
