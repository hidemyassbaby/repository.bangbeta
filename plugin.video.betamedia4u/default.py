import sys
import urllib.parse
import xbmcplugin
import xbmcgui
import xbmcaddon
import xbmc
import requests

# === Fallbacks if settings are blank ===
DEFAULT_SERVER = "https://m3ufilter.media4u.top"
DEFAULT_USERNAME = "media4u"
DEFAULT_PASSWORD = "media4u"

addon = xbmcaddon.Addon()
SERVER = addon.getSetting("server_url").strip() or DEFAULT_SERVER
USERNAME = addon.getSetting("username").strip() or DEFAULT_USERNAME
PASSWORD = addon.getSetting("password").strip() or DEFAULT_PASSWORD

HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]

# ✅ Proper TiviMate-style headers (full match)
HEADERS = {
    "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; AFTMM Build/PS7282.268) IPTV",
    "Accept": "*/*",
    "Accept-Encoding": "gzip",
    "Connection": "Keep-Alive"
}

def build_url(query):
    return BASE_URL + '?' + urllib.parse.urlencode(query)

def fetch_api(endpoint):
    sep = '&' if '?' in endpoint else '?'
    url = f"{SERVER}/{endpoint}{sep}username={USERNAME}&password={PASSWORD}"
    xbmc.log(f"[Media4u IPTV] Fetching: {url}", xbmc.LOGINFO)
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        xbmc.log(f"[Media4u IPTV] JSON Preview: {response.text[:500]}", xbmc.LOGINFO)
        return response.json()
    except Exception as e:
        xbmc.log(f"[Media4u IPTV] Connection error: {e}", xbmc.LOGERROR)
        xbmcgui.Dialog().notification("Media4u", "Connection error", xbmcgui.NOTIFICATION_ERROR)
        return {}

def validate_login():
    data = fetch_api("player_api.php")
    user_info = data.get("user_info", {})
    if user_info.get("auth") != 1:
        xbmcgui.Dialog().ok("Login Failed", "Invalid server, username, or password.")
        sys.exit()
    return data

def list_main():
    validate_login()
    xbmcplugin.setPluginCategory(HANDLE, 'Media4u IPTV')
    xbmcplugin.setContent(HANDLE, 'videos')

    for label, mode in [
        ("Live TV", "live_categories"),
        ("Movies", "vod_categories"),
        ("TV Shows", "series_categories"),
        ("Search", "search")
    ]:
        li = xbmcgui.ListItem(label=label)
        xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': mode}), li, True)

    xbmcplugin.endOfDirectory(HANDLE)

def list_categories(action, mode):
    data = fetch_api(f"player_api.php?action={action}")
    for cat in data:
        cat_id = str(cat.get("category_id"))
        name = cat.get("category_name")
        li = xbmcgui.ListItem(label=name)
        url = build_url({'mode': mode, 'cat_id': cat_id})
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.endOfDirectory(HANDLE)

def list_streams(content_type, cat_id):
    all_data = fetch_api("player_api.php")
    key_map = {
        'live': 'live_streams',
        'vod': 'movie_streams',
        'series': 'series'
    }
    streams = all_data.get(key_map[content_type], [])
    count = 0

    for item in streams:
        name = item.get("name")
        stream_id = item.get("stream_id")
        icon = item.get("stream_icon", "")
        xbmc.log(f"[DEBUG] {content_type.upper()} stream: {name} | ID: {stream_id}", xbmc.LOGINFO)

        if not stream_id:
            continue

        stream_url = f"{SERVER}/{content_type}/{USERNAME}/{PASSWORD}/{stream_id}.ts"
        li = xbmcgui.ListItem(label=name)
        li.setArt({'thumb': icon, 'icon': icon, 'poster': icon})
        li.setInfo('video', {'title': name})
        li.setPath(stream_url)
        xbmcplugin.addDirectoryItem(HANDLE, stream_url, li, False)
        count += 1

    if count == 0:
        xbmcgui.Dialog().notification("Media4u", f"No {content_type} streams found!", xbmcgui.NOTIFICATION_INFO)

    xbmcplugin.endOfDirectory(HANDLE)

def search():
    keyboard = xbmc.Keyboard('', 'Search')
    keyboard.doModal()
    if not keyboard.isConfirmed():
        xbmcplugin.endOfDirectory(HANDLE)
        return

    query = keyboard.getText().lower()
    all_data = fetch_api("player_api.php")
    results = []

    for content_type, key in [('live', 'live_streams'), ('vod', 'movie_streams'), ('series', 'series')]:
        for item in all_data.get(key, []):
            if query in item.get("name", "").lower():
                item["__type__"] = content_type
                results.append(item)

    if not results:
        xbmcgui.Dialog().notification("Media4u", "No results found.", xbmcgui.NOTIFICATION_INFO)
        xbmcplugin.endOfDirectory(HANDLE)
        return

    if len(results) == 1:
        item = results[0]
        stream_url = f"{SERVER}/{item['__type__']}/{USERNAME}/{PASSWORD}/{item['stream_id']}.ts"
        li = xbmcgui.ListItem(label=item["name"])
        li.setPath(stream_url)
        xbmcplugin.setResolvedUrl(HANDLE, True, li)
        return

    for item in results:
        name = item.get("name")
        icon = item.get("stream_icon", "")
        stream_id = item.get("stream_id")
        content_type = item["__type__"]
        stream_url = f"{SERVER}/{content_type}/{USERNAME}/{PASSWORD}/{stream_id}.ts"
        li = xbmcgui.ListItem(label=name)
        li.setArt({'thumb': icon, 'icon': icon, 'poster': icon})
        li.setInfo('video', {'title': name})
        li.setPath(stream_url)
        xbmcplugin.addDirectoryItem(HANDLE, stream_url, li, False)

    xbmcplugin.endOfDirectory(HANDLE)

def router(paramstring):
    params = dict(urllib.parse.parse_qsl(paramstring))
    mode = params.get('mode')

    if mode == 'live_categories':
        list_categories('get_live_categories', 'live')
    elif mode == 'vod_categories':
        list_categories('get_vod_categories', 'vod')
    elif mode == 'series_categories':
        list_categories('get_series_categories', 'series')
    elif mode in ['live', 'vod', 'series']:
        cat_id = params.get("cat_id")
        list_streams(mode, cat_id)
    elif mode == 'search':
        search()
    else:
        list_main()

if __name__ == '__main__':
    router(sys.argv[2][1:])
