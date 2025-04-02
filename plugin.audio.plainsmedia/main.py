import sys
import urllib.parse
import xbmcplugin
import xbmcgui
import requests

API_URL = "https://kingfisher.api.firecrest.systems/station/programmes/latest-episodes?page=1&pageSize=25"
API_KEY = "eX8svQBlcC40ppWPUyzrO3oVnsLlLGqJ9jw7zGkk"

def build_url(query):
    return sys.argv[0] + '?' + urllib.parse.urlencode(query)

def list_latest_episodes():
    headers = {
        'x-api-key': API_KEY,
        'accept': 'application/json'
    }
    response = requests.get(API_URL, headers=headers)
    data = response.json()

    for item in data.get("items", []):
        title = item.get("title", "Untitled")
        audio_url = item.get("audio", {}).get("url")
        if not audio_url:
            continue

        li = xbmcgui.ListItem(title)
        li.setInfo('music', {'title': title})
        li.setProperty('IsPlayable', 'true')
        xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=audio_url, listitem=li, isFolder=False)

    xbmcplugin.endOfDirectory(int(sys.argv[1]))

def router(paramstring):
    params = urllib.parse.parse_qs(paramstring)
    action = params.get('action', [None])[0]

    if action is None:
        # Main menu
        url = build_url({'action': 'latest'})
        li = xbmcgui.ListItem("Latest Episodes")
        xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=url, listitem=li, isFolder=True)
        xbmcplugin.endOfDirectory(int(sys.argv[1]))

    elif action == 'latest':
        list_latest_episodes()

if __name__ == '__main__':
    router(sys.argv[2][1:])
