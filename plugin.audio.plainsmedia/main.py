import urllib.request
import urllib.parse
import re
import xbmcplugin
import xbmcgui
import sys

BASE_URL = 'https://accessradio.org'
PROGRAMMES_URL = f'{BASE_URL}/station?SID=1e641e21-9297-4a53-adfc-8ceca841c90a'
IMAGE_BASE_URL = 'https://images.accessmedia.nz/StationFolder/plainsfm/Images/'

addon_handle = int(sys.argv[1])
xbmcplugin.setContent(addon_handle, 'audio')

def sanitize_title(title):
    # Remove special characters for image filenames
    return re.sub(r'[^A-Za-z0-9]', '', title)

def clean_html(raw_html):
    # Remove any embedded HTML tags from names
    return re.sub(r'<.*?>', '', raw_html).strip()

def fetch_programmes():
    """Fetch all programme names and IDs."""
    req = urllib.request.Request(PROGRAMMES_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=10) as response:
        html = response.read().decode('utf-8')

    # Extract programme IDs and titles
    pattern = re.compile(r'<a href="/programme-page\?PID=([a-f0-9-]+)".*?>(.*?)</a>')
    matches = pattern.findall(html)
    return [(pid, clean_html(title)) for pid, title in matches]

def list_programmes():
    """Show list of shows with thumbnails."""
    programmes = fetch_programmes()
    for pid, title in programmes:
        li = xbmcgui.ListItem(label=title)
        image_name = sanitize_title(title)
        image_url = f'{IMAGE_BASE_URL}{image_name}.png'
        li.setArt({'thumb': image_url, 'icon': image_url, 'fanart': image_url})
        xbmcplugin.addDirectoryItem(handle=addon_handle, url='', listitem=li, isFolder=False)
    xbmcplugin.endOfDirectory(addon_handle)

if __name__ == '__main__':
    list_programmes()
