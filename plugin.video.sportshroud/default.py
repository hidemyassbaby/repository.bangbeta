import xbmcplugin
import xbmcgui
import sys
import urllib.parse
import requests
import json

BASE_URL = sys.argv[0]
HANDLE = int(sys.argv[1])
ARGS = urllib.parse.parse_qs(sys.argv[2][1:])

# Remote menu file
MENU_URL = "https://raw.githubusercontent.com/hidemyassbaby/SportShroud/refs/heads/main/Main%20Menu/SportShroudMenu.json"

def build_url(query):
    return BASE_URL + '?' + urllib.parse.urlencode(query)

def list_main_menu():
    try:
        response = requests.get(MENU_URL)
        data = response.json()
        for item in data:
            url = build_url({'name': item['name'], 'url': item['url']})
            li = xbmcgui.ListItem(label=item['name'])
            xbmcplugin.addDirectoryItem(handle=HANDLE, url=url, listitem=li, isFolder=True)
        xbmcplugin.endOfDirectory(HANDLE)
    except Exception as e:
        xbmcgui.Dialog().notification("Menu Error", str(e), xbmcgui.NOTIFICATION_ERROR)

def list_game_links(name, json_url):
    try:
        response = requests.get(json_url)
        data = response.json()
        for stream in data.get('streams', []):
            li = xbmcgui.ListItem(label=stream['title'])
            li.setProperty("IsPlayable", "true")
            xbmcplugin.addDirectoryItem(handle=HANDLE, url=stream['url'], listitem=li)
        xbmcplugin.endOfDirectory(HANDLE)
    except Exception as e:
        xbmcgui.Dialog().notification(f"{name} Error", str(e), xbmcgui.NOTIFICATION_ERROR)

if 'url' in ARGS and 'name' in ARGS:
    list_game_links(ARGS['name'][0], ARGS['url'][0])
else:
    list_main_menu()
