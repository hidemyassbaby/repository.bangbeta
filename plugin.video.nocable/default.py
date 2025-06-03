#!/usr/bin/python
# -*- coding: utf-8 -*-

# Kodi Specific
import xbmc, xbmcaddon, xbmcgui, xbmcplugin, xbmcvfs
# Python Specific
import base64, os, re, time, string, sys, urllib.request
import urllib.parse, urllib.error, json, datetime
from resources.modules import control, tools

# Add-on info
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
ADDON_NAME = ADDON.getAddonInfo('name')
DIALOG = xbmcgui.Dialog()
HOME = xbmcvfs.translatePath('special://home/')
ADDONDATA = os.path.join(HOME, 'userdata', 'addon_data', ADDON_ID)
MEDIA = os.path.join(HOME, 'addons', ADDON_ID, 'resources', 'media')
KODIV = float(xbmc.getInfoLabel("System.BuildVersion")[:4])

# Media Assets
icon = os.path.join(MEDIA, 'icon.png')
background = os.path.join(MEDIA, 'background.jpg')
iconaccount = os.path.join(MEDIA, 'iconaccount.png')
iconlive = os.path.join(MEDIA, 'iconlive.png')
iconTvseries = os.path.join(MEDIA, 'icontvseries.png')
iconcatchup = os.path.join(MEDIA, 'iconcatchup.png')
iconMoviesod = os.path.join(MEDIA, 'iconmovies.png')
iconsearch = os.path.join(MEDIA, 'iconsearch.png')
iconsettings = os.path.join(MEDIA, 'iconsettings.png')
iconextras = os.path.join(MEDIA, 'iconextras.png')
icontvguide = os.path.join(MEDIA, 'iconguide.png')

# Settings from settings.xml
dns = control.setting('DNS')
username = control.setting('Username')
password = control.setting('Password')

# URLs
live_url = f'{dns}/enigma2.php?username={username}&password={password}&type=get_live_categories'
vod_url = f'{dns}/enigma2.php?username={username}&password={password}&type=get_vod_categories'
series_url = f'{dns}/enigma2.php?username={username}&password={password}&type=get_series_categories'
panel_api = f'{dns}/panel_api.php?username={username}&password={password}'
player_api = f'{dns}/player_api.php?username={username}&password={password}'
play_live = f'{dns}/{username}/{password}/'
play_movies = f'{dns}/movie/{username}/{password}/'
play_series = f'{dns}/series/{username}/{password}/'

# Adult Filter List
adult_tags = ['xxx','xXx','XXX','adult','Adult','ADULT','adults','Adults','ADULTS','porn','Porn','PORN']

# Clean start() function
def start(signin):
    if dns and username and password:
        home()
    else:
        xbmcgui.Dialog().ok(
            ADDON_NAME,
            "Login settings (DNS, Username, or Password) are missing.\n\n"
            "Please check your addon settings.xml and make sure these values are set:\n\n"
            "- DNS\n- Username\n- Password"
        )

# Home menu layout
def home():
    tools.addDir('Account Information', 'url', 6, iconaccount, background, '')
    tools.addDir('Live TV', 'live', 1, iconlive, background, '')
    tools.addDir('TV Series', 'live', 18, iconTvseries, background, '')
    if xbmc.getCondVisibility('System.HasAddon(pvr.iptvsimple)'):
        tools.addDir('TV Guide', 'pvr', 7, icontvguide, background, '')
    tools.addDir('Catchup TV', 'url', 12, iconcatchup, background, '')
    tools.addDir('Video On Demand', 'vod', 3, iconMoviesod, background, '')
    tools.addDir('Search', 'url', 5, iconsearch, background, '')
    tools.addDir('Settings', 'url', 8, iconsettings, background, '')
    tools.addDir('Extras', 'url', 16, iconextras, background, '')

# Define the previously missing local functions
def livecategory(): xbmcgui.Dialog().ok("Live TV", "Live category would be loaded here.")
def Livelist(url): xbmcgui.Dialog().ok("Live List", f"Stream URL: {url}")
def vod(url): xbmcgui.Dialog().ok("VOD", f"VOD URL: {url}")
def stream_video(url): xbmcgui.Dialog().ok("Stream", f"Playing: {url}")
def search(): xbmcgui.Dialog().ok("Search", "Search screen here")
def accountinfo(): xbmcgui.Dialog().ok("Account", f"User: {username}\nDNS: {dns}")
def tvguide(): xbmc.executebuiltin('ActivateWindow(TVGuide)')
def settingsmenu(): xbmc.executebuiltin(f'Addon.OpenSettings({ADDON_ID})')
def addonsettings(url, description): xbmcgui.Dialog().ok("Addon Setting", f"{description}: {url}")
def catchup(): xbmcgui.Dialog().ok("Catchup", "Catchup logic here")
def tvarchive(name, description): xbmcgui.Dialog().ok("Archive", f"{name}: {description}")
def extras(): xbmcgui.Dialog().ok("Extras", "Extras tools and options")
def series_cats(url): xbmcgui.Dialog().ok("Series Cats", f"Load series categories from {url}")
def serieslist(url): xbmcgui.Dialog().ok("Series List", f"List series items from {url}")
def series_seasons(url): xbmcgui.Dialog().ok("Series Seasons", f"Seasons of series at {url}")
def season_list(url): xbmcgui.Dialog().ok("Season List", f"Episodes in season from {url}")

# Get parameters safely
params = tools.get_params()
url = urllib.parse.unquote_plus(params["url"]) if "url" in params else None
name = urllib.parse.unquote_plus(params["name"]) if "name" in params else None
mode = int(params["mode"]) if "mode" in params else None
iconimage = urllib.parse.unquote_plus(params["iconimage"]) if "iconimage" in params else None
description = urllib.parse.unquote_plus(params["description"]) if "description" in params else None
query = urllib.parse.unquote_plus(params["query"]) if "query" in params else None
type = urllib.parse.unquote_plus(params["type"]) if "type" in params else None

# Main routing logic
if mode is None or url is None or len(url) < 1:
    start('false')
elif mode == 1:
    livecategory()
elif mode == 2:
    Livelist(url)
elif mode == 3:
    vod(url)
elif mode == 4:
    stream_video(url)
elif mode == 5:
    search()
elif mode == 6:
    accountinfo()
elif mode == 7:
    tvguide()
elif mode == 8:
    settingsmenu()
elif mode == 10:
    addonsettings(url, description)
elif mode == 12:
    catchup()
elif mode == 13:
    tvarchive(name, description)
elif mode == 16:
    extras()
elif mode == 18:
    series_cats(url)
elif mode == 25:
    serieslist(url)
elif mode == 19:
    series_seasons(url)
elif mode == 20:
    season_list(url)
elif mode == 'start':
    start('false')

# End directory
xbmcplugin.endOfDirectory(int(sys.argv[1]))
