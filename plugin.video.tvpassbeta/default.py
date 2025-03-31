# Full working version of TV Pass addon with categories, search, favourites, and EPG
# Author: ChatGPT for user
import sys
import urllib.parse
import xbmcplugin
import xbmcgui
import xbmcaddon
import xbmc
import requests
import re
import os
import time
import json
from xbmcvfs import translatePath
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime

# Constants
addon = xbmcaddon.Addon()
HANDLE = int(sys.argv[1]) if len(sys.argv) > 1 else -1
BASE_URL = sys.argv[0] if len(sys.argv) > 0 else ""

M3U_URL = "http://tvpass.org/playlist/m3u"
EPG_URL = "https://tvpass.org/epg.xml"

CACHE_PATH = translatePath(addon.getAddonInfo('profile')).rstrip('/')
if not os.path.exists(CACHE_PATH):
    os.makedirs(CACHE_PATH)

FAVOURITES_FILE = os.path.join(CACHE_PATH, "favourites.json")
SETUP_FILE = os.path.join(CACHE_PATH, ".setupdone")
DEV_MODE_FILE = os.path.join(CACHE_PATH, ".devmode")
M3U_CACHE_FILE = os.path.join(CACHE_PATH, "channels.m3u")
EPG_CACHE_FILE = os.path.join(CACHE_PATH, "epg.xml")

# --- Utility functions ---
def log_error(e):
    xbmc.log(f"[TV Pass ERROR] {str(e)}\n{traceback.format_exc()}", xbmc.LOGERROR)

def build_url(query):
    return BASE_URL + '?' + urllib.parse.urlencode(query)

def is_developer_mode():
    return os.path.exists(DEV_MODE_FILE)

def toggle_developer_mode():
    try:
        if is_developer_mode():
            os.remove(DEV_MODE_FILE)
            xbmcgui.Dialog().notification("Developer Mode", "Disabled", xbmcgui.NOTIFICATION_INFO, 3000)
            xbmc.executebuiltin("Container.Refresh")
        else:
            password = xbmcgui.Dialog().input("Enter Developer Password", type=xbmcgui.INPUT_ALPHANUM)
            if password == 'bangdev':
                with open(DEV_MODE_FILE, 'w') as f:
                    f.write("enabled")
                xbmcgui.Dialog().notification("Developer Mode", "Enabled", xbmcgui.NOTIFICATION_INFO, 3000)
                xbmc.executebuiltin("Container.Refresh")
            else:
                xbmcgui.Dialog().ok("Access Denied", "Incorrect password.")
    except Exception as e:
        log_error(e)

# --- Cache loaders ---
def update_cache(force=False):
    try:
        m3u_expired = not os.path.exists(M3U_CACHE_FILE) or time.time() - os.path.getmtime(M3U_CACHE_FILE) > 86400
        epg_expired = not os.path.exists(EPG_CACHE_FILE) or time.time() - os.path.getmtime(EPG_CACHE_FILE) > 86400

        if force or m3u_expired or epg_expired:
            progress = xbmcgui.DialogProgress()
            progress.create("TV Pass Setup", "Fetching latest data")
            if force or m3u_expired:
                progress.update(10, "Updating M3U playlist")
                m3u = requests.get(M3U_URL, timeout=10)
                with open(M3U_CACHE_FILE, 'w', encoding='utf-8') as f:
                    f.write(m3u.text)
            if force or epg_expired:
                progress.update(60, "Updating EPG data")
                epg = requests.get(EPG_URL, timeout=10)
                with open(EPG_CACHE_FILE, 'w', encoding='utf-8') as f:
                    f.write(epg.text)
            progress.update(100, "Complete")
            time.sleep(0.5)
            progress.close()
    except Exception as e:
        log_error(e)
        xbmcgui.Dialog().notification("TV Pass", f"Cache update failed: {str(e)}", xbmcgui.NOTIFICATION_ERROR, 5000)

def get_cached_m3u():
    if os.path.exists(M3U_CACHE_FILE):
        with open(M3U_CACHE_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    else:
        update_cache(force=True)
        return get_cached_m3u()

def get_cached_epg():
    if os.path.exists(EPG_CACHE_FILE):
        return ET.parse(EPG_CACHE_FILE).getroot()
    else:
        update_cache(force=True)
        return get_cached_epg()

# --- EPG ---
def get_epg_for_channel(channel_id, limit=5):
    try:
        epg_data = get_cached_epg()
        now = datetime.utcnow()
        results = []
        for programme in epg_data.findall("programme"):
            if programme.attrib.get("channel") != channel_id:
                continue
            start = datetime.strptime(programme.attrib.get("start").split()[0], "%Y%m%d%H%M%S")
            stop = datetime.strptime(programme.attrib.get("stop").split()[0], "%Y%m%d%H%M%S")
            if stop < now:
                continue
            title = programme.findtext("title", default="Unknown").strip()
            subtitle = programme.findtext("sub-title", "")
            desc = programme.findtext("desc", default="").strip()
            full_desc = f"{subtitle + ' - ' if subtitle else ''}{desc}"
            results.append(f"[B]{start.strftime('%H:%M')}[/B] {title}\n{full_desc}")
            if len(results) >= limit:
                break
        return "\n\n".join(results) if results else "No upcoming programs."
    except Exception as e:
        log_error(e)
        return "EPG error."

# --- Favourites ---
def load_favourites():
    if os.path.exists(FAVOURITES_FILE):
        with open(FAVOURITES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_favourites(data):
    with open(FAVOURITES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def is_favourite(url):
    return any(f['url'] == url for f in load_favourites())

def add_to_favourites(name, url, logo="", tvg_id=""):
    favs = load_favourites()
    if not any(f['url'] == url for f in favs):
        favs.append({'name': name, 'url': url, 'logo': logo, 'tvg_id': tvg_id})
        save_favourites(favs)
        xbmcgui.Dialog().notification("TV Pass", "Added to favourites", xbmcgui.NOTIFICATION_INFO, 3000)

def remove_from_favourites(url):
    favs = [f for f in load_favourites() if f['url'] != url]
    save_favourites(favs)
    xbmcgui.Dialog().notification("TV Pass", "Removed from favourites", xbmcgui.NOTIFICATION_INFO, 3000)

# --- Categories, Channels, Search ---
def list_categories():
    raw_data = get_cached_m3u()
    pattern = re.compile(r'#EXTINF:-1.*?group-title="(.*?)",')
    groups = sorted(set(pattern.findall(raw_data)))
    for group in groups:
        li = xbmcgui.ListItem(label=group)
        url = build_url({'mode': 'group', 'group': group})
        xbmcplugin.addDirectoryItem(HANDLE, url, li, True)
    xbmcplugin.endOfDirectory(HANDLE)

def list_group_channels(group):
    raw_data = get_cached_m3u()
    pattern = re.compile(r'#EXTINF:-1 tvg-id="(.*?)".*?group-title="(.*?)",(.*?)\n(https?://\S+)')
    matches = re.findall(pattern, raw_data)
    for tvg_id, group_title, name, url in matches:
        if group_title != group:
            continue
        li = xbmcgui.ListItem(label=name)
        epg_info = get_epg_for_channel(tvg_id)
        li.setInfo('video', {'title': name})
        li.setPath(url)
        context = []
        if is_favourite(url):
            context.append(("Remove from TV Pass Favourites", f"RunPlugin({build_url({'mode': 'remove_favourite', 'url': url})})"))
        else:
            context.append(("Add to TV Pass Favourites", f"RunPlugin({build_url({'mode': 'add_favourite', 'name': name, 'url': url, 'tvg_id': tvg_id})})"))
        context.append(("View Full Schedule", f"RunScript(script.dialog, title=EPG for {name}, message={epg_info})"))
        li.addContextMenuItems(context)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, False)
    xbmcplugin.endOfDirectory(HANDLE)

def list_favourites():
    favs = load_favourites()
    for fav in favs:
        li = xbmcgui.ListItem(label=fav['name'])
        li.setInfo('video', {'title': fav['name']})
        li.setPath(fav['url'])
        epg_info = get_epg_for_channel(fav.get('tvg_id', ''))
        context = [
            ("Remove from TV Pass Favourites", f"RunPlugin({build_url({'mode': 'remove_favourite', 'url': fav['url']})})"),
            ("View Full Schedule", f"RunScript(script.dialog, title=EPG for {fav['name']}, message={epg_info})")
        ]
        li.addContextMenuItems(context)
        xbmcplugin.addDirectoryItem(HANDLE, fav['url'], li, False)
    xbmcplugin.endOfDirectory(HANDLE)

def search_channels():
    query = xbmcgui.Dialog().input("Search Channels")
    raw_data = get_cached_m3u()
    pattern = re.compile(r'#EXTINF:-1 tvg-id="(.*?)".*?,(.*?)\n(https?://\S+)')
    matches = [m for m in pattern.findall(raw_data) if query.lower() in m[1].lower()]
    for tvg_id, name, url in matches:
        li = xbmcgui.ListItem(label=name)
        epg_info = get_epg_for_channel(tvg_id)
        li.setInfo('video', {'title': name})
        li.setPath(url)
        context = []
        if is_favourite(url):
            context.append(("Remove from TV Pass Favourites", f"RunPlugin({build_url({'mode': 'remove_favourite', 'url': url})})"))
        else:
            context.append(("Add to TV Pass Favourites", f"RunPlugin({build_url({'mode': 'add_favourite', 'name': name, 'url': url, 'tvg_id': tvg_id})})"))
        context.append(("View Full Schedule", f"RunScript(script.dialog, title=EPG for {name}, message={epg_info})"))
        li.addContextMenuItems(context)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, False)
    xbmcplugin.endOfDirectory(HANDLE)

# --- Main menu and routing ---
def main_menu():
    if is_developer_mode():
        xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'dev_toggle'}), xbmcgui.ListItem('[B]Developer Mode[/B] [COLOR=green]ON[/COLOR]'), False)
    xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'categories'}), xbmcgui.ListItem('Live TV'), True)
    xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'favourites'}), xbmcgui.ListItem('Favourites'), True)
    xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'search'}), xbmcgui.ListItem('Search'), True)
    xbmcplugin.addDirectoryItem(HANDLE, build_url({'mode': 'settings'}), xbmcgui.ListItem('Settings'), True)
    xbmcplugin.endOfDirectory(HANDLE)

def router(paramstring):
    try:
        params = dict(urllib.parse.parse_qsl(paramstring))
        mode = params.get('mode')
        if mode == 'dev_toggle':
            toggle_developer_mode()
        elif mode == 'categories':
            list_categories()
        elif mode == 'group':
            list_group_channels(params.get('group'))
        elif mode == 'favourites':
            list_favourites()
        elif mode == 'search':
            search_channels()
        elif mode == 'add_favourite':
            add_to_favourites(params['name'], params['url'], tvg_id=params.get('tvg_id', ''))
        elif mode == 'remove_favourite':
            remove_from_favourites(params['url'])
        else:
            main_menu()
    except Exception as e:
        log_error(e)
        xbmcgui.Dialog().notification("TV Pass", "Startup failed", xbmcgui.NOTIFICATION_ERROR, 3000)

# --- First launch ---
if not os.path.exists(SETUP_FILE):
    update_cache(force=True)
    with open(SETUP_FILE, 'w') as f:
        f.write('done')

# --- Entry Point ---
if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[2]:
        router(sys.argv[2][1:])
    else:
        router("")
