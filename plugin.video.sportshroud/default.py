import xbmcplugin
import xbmcgui
import sys
import urllib.parse
import urllib.request
import json

BASE_URL = sys.argv[0]
HANDLE = int(sys.argv[1])
ARGS = urllib.parse.parse_qs(sys.argv[2][1:])

# Remote menu file
MENU_URL = "https://raw.githubusercontent.com/hidemyassbaby/SportShroud/refs/heads/main/Main%20Menu/SportShroudMenu.json"

def build_url(query):
    return BASE_URL + '?' + urllib.parse.urlencode(query)

def fetch_json(url):
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read().decode())

def list_main_menu():
    try:
        data = fetch_json(MENU_URL)
        for item in data:
            url = build_url({'name': item['name'], 'url': item['url']})
            li = xbmcgui.ListItem(label=item['name'])
            if 'thumb' in item:
                li.setArt({'thumb': item['thumb'], 'icon': item['thumb'], 'poster': item['thumb']})
            if 'plot' in item:
                li.setInfo('video', {'title': item['name'], 'plot': item['plot']})
            xbmcplugin.addDirectoryItem(handle=HANDLE, url=url, listitem=li, isFolder=True)
        xbmcplugin.endOfDirectory(HANDLE)
    except Exception as e:
        xbmcgui.Dialog().notification("Menu Error", str(e), xbmcgui.NOTIFICATION_ERROR)

def list_game_links(name, json_url):
    try:
        data = fetch_json(json_url)
        for stream in data.get('streams', []):
            li = xbmcgui.ListItem(label=stream['title'])
            if 'thumb' in stream:
                li.setArt({'thumb': stream['thumb'], 'icon': stream['thumb'], 'poster': stream['thumb']})
            if 'plot' in stream:
                li.setInfo('video', {'title': stream['title'], 'plot': stream['plot']})
            li.setProperty("IsPlayable", "true")
            xbmcplugin.addDirectoryItem(handle=HANDLE, url=stream['url'], listitem=li)
        xbmcplugin.endOfDirectory(HANDLE)
    except Exception as e:
        xbmcgui.Dialog().notification(f"{name} Error", str(e), xbmcgui.NOTIFICATION_ERROR)

if 'url' in ARGS and 'name' in ARGS:
    list_game_links(ARGS['name'][0], ARGS['url'][0])
else:
    list_main_menu()
