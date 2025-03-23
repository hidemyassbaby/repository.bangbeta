import sys
import urllib.parse
import xbmcplugin
import xbmcgui
import xbmcaddon
import xbmc
import requests

addon = xbmcaddon.Addon()
SERVER = addon.getSetting("server_url").strip()
USERNAME = addon.getSetting("username").strip()
PASSWORD = addon.getSetting("password").strip()

HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]

def build_url(query):
    return BASE_URL + '?' + urllib.parse.urlencode(query)

def fetch_api(endpoint):
    url = f"{SERVER}/{endpoint}?username={USERNAME}&password={PASSWORD}"
    try:
        return requests.get(url, timeout=10).json()
    except:
        xbmcgui.Dialog().notification("My IPTV", "Connection error", xbmcgui.NOTIFICATION_ERROR)
        return {}

def list_main():
    xbmcplugin.setPluginCategory(HANDLE, 'My IPTV')
    xbmcplugin.setContent(HANDLE, 'videos')
    for label, mode in [('Live TV', 'live_categories'), ('Movies', 'vod_categories'), ('TV Shows', 'series_categories'), ('Search', 'search')]:
        li = xbmcgui.ListItem(label=label)
        xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': mode}), li, True)
    xbmcplugin.endOfDirectory(HANDLE)

def list_grouped_categories(content_type):
    cat_map = {
        'live_categories': 'get_live_categories',
        'vod_categories': 'get_vod_categories',
        'series_categories': 'get_series_categories'
    }
    api = cat_map[content_type]
    categories = fetch_api(f"player_api.php?action={api}")
    for cat in categories:
        li = xbmcgui.ListItem(label=cat['category_name'])
        xbmcplugin.addDirectoryItem(HANDLE, build_url({
            'mode': content_type.replace('_categories', ''),
            'cat_id': cat['category_id']
        }), li, True)
    xbmcplugin.endOfDirectory(HANDLE)

def list_items(content_type, cat_id, search_term=None):
    all_data = fetch_api("player_api.php")
    type_map = {
        'live': 'live_streams',
        'vod': 'movie_streams',
        'series': 'series'
    }
    content_list = all_data.get(type_map[content_type], [])

    for item in content_list:
        if cat_id and str(item.get('category_id')) != cat_id:
            continue
        if search_term and search_term.lower() not in item.get('name', '').lower():
            continue

        name = item.get('name')
        stream_id = item.get('stream_id')
        stream_icon = item.get('stream_icon') or ""
        
        if content_type == 'live':
            stream_url = f"{SERVER}/live/{USERNAME}/{PASSWORD}/{stream_id}.m3u8"
        else:
            stream_url = f"{SERVER}/movie/{USERNAME}/{PASSWORD}/{stream_id}.mp4"

        li = xbmcgui.ListItem(label=name)
        li.setArt({'thumb': stream_icon, 'icon': stream_icon, 'poster': stream_icon})
        li.setInfo('video', {'title': name})
        li.setProperty('inputstream', 'inputstream.adaptive')
        li.setProperty('inputstream.adaptive.manifest_type', 'hls')
        li.setMimeType('application/vnd.apple.mpegurl')
        li.setPath(stream_url)
        xbmcplugin.addDirectoryItem(HANDLE, stream_url, li, False)

    xbmcplugin.endOfDirectory(HANDLE)

def search():
    keyboard = xbmc.Keyboard('', 'Search IPTV')
    keyboard.doModal()
    if keyboard.isConfirmed():
        term = keyboard.getText()
        list_items('live', None, search_term=term)
        list_items('vod', None, search_term=term)
        list_items('series', None, search_term=term)
    else:
        xbmcplugin.endOfDirectory(HANDLE)

def router(paramstring):
    params = dict(urllib.parse.parse_qsl(paramstring))
    mode = params.get('mode')
    if mode in ['live_categories', 'vod_categories', 'series_categories']:
        list_grouped_categories(mode)
    elif mode in ['live', 'vod', 'series']:
        list_items(mode, params.get('cat_id'))
    elif mode == 'search':
        search()
    else:
        list_main()

if __name__ == '__main__':
    router(sys.argv[2][1:])
