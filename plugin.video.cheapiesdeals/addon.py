import xbmcplugin
import xbmcgui
import xbmcaddon
import sys
import urllib.parse
import requests
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup

BASE_URL = sys.argv[0]
HANDLE = int(sys.argv[1])
ARGS = urllib.parse.parse_qs(sys.argv[2][1:])
ADDON = xbmcaddon.Addon()

RSS_FEED_URL = 'https://www.cheapies.nz/deals/feed'

def get_feed():
    response = requests.get(RSS_FEED_URL)
    return response.content

def parse_feed(xml_data):
    root = ET.fromstring(xml_data)
    items = []
    for item in root.findall('.//item'):
        title = item.find('title').text
        link = item.find('link').text
        items.append({'title': title, 'link': link})
    return items

def fetch_deal_details(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    title = soup.find("h1", {"id": "title"}).get_text(strip=True)

    content_div = soup.find("div", class_="content")
    content = content_div.get_text(separator="\n", strip=True) if content_div else "No description available"

    deal_btn = soup.find("a", class_="btn", text="Go to Deal")
    deal_link = "https://www.cheapies.nz" + deal_btn['href'] if deal_btn else url

    return title, content, deal_link

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
