import xbmcplugin
import xbmcgui
import xbmcaddon
import xbmc
import sys
import urllib.parse
import urllib.request
from xml.etree import ElementTree as ET
from html.parser import HTMLParser

BASE_URL = sys.argv[0]
HANDLE = int(sys.argv[1])
ARGS = urllib.parse.parse_qs(sys.argv[2][1:])
ADDON = xbmcaddon.Addon()

RSS_FEED_URL = 'https://www.cheapies.nz/deals/feed'

# Optional debug log to Kodi log file
xbmc.log("🔥 Cheapies Deals Add-on Loaded")

class DealParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_content = False
        self.in_title = False
        self.content = ''
        self.title = ''
        self.deal_url = ''
        self.capture_data = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'h1' and attrs.get('id') == 'title':
            self.in_title = True
        elif tag == 'div' and 'class' in attrs and 'content' in attrs['class']:
            self.in_content = True
        elif tag == 'a' and attrs.get('class') == 'btn' and attrs.get('href', '').startswith('/goto/'):
            self.deal_url = 'https://www.cheapies.nz' + attrs['href']
        elif self.in_content or self.in_title:
            self.capture_data = True

    def handle_data(self, data):
        if self.in_title:
            self.title += data.strip()
        elif self.in_content and self.capture_data:
            self.content += data.strip() + '\n'

    def handle_endtag(self, tag):
        if tag == 'h1' and self.in_title:
            self.in_title = False
        elif tag == 'div' and self.in_content:
            self.in_content = False
        self.capture_data = False

def get_feed():
    req = urllib.request.Request(
        RSS_FEED_URL,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}
    )
    with urllib.request.urlopen(req) as response:
        return response.read()

def parse_feed(xml_data):
    root = ET.fromstring(xml_data)
    items = []
    for item in root.findall('.//item'):
        title = item.find('title').text
        link = item.find('link').text
        items.append({'title': title, 'link': link})
    return items

def fetch_deal_details(url):
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}
    )
    with urllib.request.urlopen(req) as response:
        html = response.read().decode('utf-8')
    parser = DealParser()
    parser.feed(html)
    return parser.title, parser.content.strip(), parser.deal_url or url

def list_items():
    xml_data = get_feed()
    feed_items = parse_feed(xml_data)

    for item in feed_items:
        url = f"{BASE_URL}?action=details&url={urllib.parse.quote(item['link'])}"
        list_item = xbmcgui.ListItem(label=item['title'])
        xbmcplugin.addDirectoryItem(handle=HANDLE, url=url, listitem=list_item, isFolder=True)

    xbmcplugin.endOfDirectory(HANDLE)

def show_details(article_url):
    article_url = urllib.parse.unquote(article_url)
    title, content, deal_url = fetch_deal_details(article_url)

    li = xbmcgui.ListItem(label=title)
    li.setInfo("video", {"title": title, "plot": content})
    li.setPath(deal_url)
    xbmcplugin.setResolvedUrl(HANDLE, True, li)

if __name__ == '__main__':
    if 'action' in ARGS and ARGS['action'][0] == 'details':
        show_details(ARGS['url'][0])
    else:
        list_items()
