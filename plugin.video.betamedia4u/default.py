# -*- coding: utf-8 -*-
"""
Media4u TV Kodi plugin
Version 5.1.2 beta
Kodi 21 and Kodi 22 friendly, Python 3 only.
"""

from __future__ import annotations

import json
import os
import sys
import time
import threading
import traceback
import urllib.parse
from typing import Any, Dict, Iterable, List, Optional, Tuple

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs
import requests

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_NAME = ADDON.getAddonInfo("name") or "Beta Media4u"
HANDLE = int(sys.argv[1]) if len(sys.argv) > 1 else -1
BASE_URL = sys.argv[0] if len(sys.argv) > 0 else ""

SERVER = "https://tv.media4u.top"
FREE_USER = "media4u"
FREE_PASS = "media4u"
FIRST_RUN_KEY = "first_run_done"

HEADERS = {
    "User-Agent": "Kodi BetaMedia4u/5.1.2",
    "Accept": "application/json,text/plain,*/*",
    "Connection": "keep-alive",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

PROFILE_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo("profile")).rstrip("/\\")
if not xbmcvfs.exists(PROFILE_PATH):
    xbmcvfs.mkdirs(PROFILE_PATH)

FAV_FILE = os.path.join(PROFILE_PATH, "favorites.json")
CACHE_FILE = os.path.join(PROFILE_PATH, "api_cache.json")
GUI_STATE_FILE = os.path.join(PROFILE_PATH, "gui_state.json")
CACHE_TTL_SECONDS = 10 * 60
# Short in-memory cache only, keeps GUI fast without hiding newly added channels for long.
MEMORY_API_CACHE: Dict[str, Tuple[int, Any]] = {}
MEMORY_CACHE_TTL_SECONDS = 20
EPG_CACHE: Dict[str, str] = {}


def log(message: str, level: int = xbmc.LOGINFO) -> None:
    xbmc.log(f"[{ADDON_ID}] {message}", level)


def notify(message: str, title: str = ADDON_NAME, ms: int = 3000, icon: str = xbmcgui.NOTIFICATION_INFO) -> None:
    xbmcgui.Dialog().notification(title, message, icon, ms)


def build_url(params: Dict[str, Any]) -> str:
    return BASE_URL + "?" + urllib.parse.urlencode(params)


def quote(value: Any) -> str:
    return urllib.parse.quote_plus(str(value or ""))


def setting_bool(key: str, default: bool = False) -> bool:
    value = (ADDON.getSetting(key) or "").strip().lower()
    if not value:
        return default
    return value in {"true", "1", "yes", "on"}


def get_setting(key: str, default: str = "") -> str:
    value = ADDON.getSetting(key)
    return value if value not in (None, "") else default


def get_effective_creds() -> Tuple[str, str, str]:
    if not setting_bool("use_paid_login", False):
        return FREE_USER, FREE_PASS, "Free Access"

    user = get_setting("username").strip()
    pwd = get_setting("password").strip()
    if not user or not pwd:
        xbmcgui.Dialog().ok(ADDON_NAME, "Paid login is selected, but the username or password is missing.\n\nFree Access will be used for now.")
        ADDON.setSetting("use_paid_login", "false")
        return FREE_USER, FREE_PASS, "Free Access"

    return user, pwd, "Paid Login"


def xc_api_url(endpoint: str) -> str:
    user, pwd, _label = get_effective_creds()
    sep = "&" if "?" in endpoint else "?"
    return f"{SERVER}/{endpoint}{sep}username={quote(user)}&password={quote(pwd)}"


def load_cache() -> Dict[str, Any]:
    try:
        if not os.path.exists(CACHE_FILE):
            return {}
        with open(CACHE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        log(f"Cache read failed: {exc}", xbmc.LOGWARNING)
        return {}


def save_cache(cache: Dict[str, Any]) -> None:
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False)
    except Exception as exc:
        log(f"Cache save failed: {exc}", xbmc.LOGWARNING)


def clear_cache() -> None:
    try:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
        notify("Cache cleared")
    except Exception as exc:
        log(f"Cache clear failed: {exc}", xbmc.LOGERROR)
        notify("Could not clear cache", icon=xbmcgui.NOTIFICATION_ERROR)


def http_get_json(url: str, timeout: int = 25, use_cache: bool = True) -> Optional[Any]:
    cache = load_cache() if use_cache else {}
    now = int(time.time())
    cached = cache.get(url)
    if use_cache and isinstance(cached, dict) and now - int(cached.get("time", 0)) < CACHE_TTL_SECONDS:
        return cached.get("data")

    try:
        response = SESSION.get(url, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        if use_cache:
            cache[url] = {"time": now, "data": data}
            save_cache(cache)
        return data
    except requests.exceptions.Timeout:
        notify("Connection timed out", icon=xbmcgui.NOTIFICATION_ERROR)
        log(f"Timeout: {url}", xbmc.LOGERROR)
    except requests.exceptions.RequestException as exc:
        notify("Server connection failed", icon=xbmcgui.NOTIFICATION_ERROR)
        log(f"HTTP error: {exc}", xbmc.LOGERROR)
    except ValueError as exc:
        notify("Server returned invalid JSON", icon=xbmcgui.NOTIFICATION_ERROR)
        log(f"JSON error: {exc}", xbmc.LOGERROR)
    return None


def http_get_json_memory(url: str, timeout: int = 25, ttl: int = MEMORY_CACHE_TTL_SECONDS) -> Optional[Any]:
    now = int(time.time())
    cached = MEMORY_API_CACHE.get(url)
    if isinstance(cached, tuple) and now - int(cached[0]) < ttl:
        return cached[1]
    data = http_get_json(url, timeout=timeout, use_cache=False)
    if data is not None:
        MEMORY_API_CACHE[url] = (now, data)
    return data


def first_run_check() -> None:
    if setting_bool(FIRST_RUN_KEY, False):
        return
    choice = xbmcgui.Dialog().select("Media4u TV setup", ["Use Free Access", "Use Paid Login"])
    if choice == 1:
        ADDON.setSetting("use_paid_login", "true")
        ADDON.openSettings()
    else:
        ADDON.setSetting("use_paid_login", "false")
    ADDON.setSetting(FIRST_RUN_KEY, "true")


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def set_art(li: xbmcgui.ListItem, thumb: str = "") -> None:
    if thumb:
        li.setArt({"thumb": thumb, "icon": thumb, "poster": thumb})


def set_video_info(li: xbmcgui.ListItem, title: str, plot: str = "", year: Any = None) -> None:
    info = {"title": title}
    if plot:
        info["plot"] = plot
    if year:
        info["year"] = safe_int(year)
    li.setInfo("video", info)


def add_folder(label: str, mode: str, extra: Optional[Dict[str, Any]] = None, thumb: str = "") -> None:
    params = {"mode": mode}
    if extra:
        params.update(extra)
    li = xbmcgui.ListItem(label=label)
    set_art(li, thumb)
    xbmcplugin.addDirectoryItem(HANDLE, build_url(params), li, True)


def add_action(label: str, mode: str, extra: Optional[Dict[str, Any]] = None) -> None:
    params = {"mode": mode}
    if extra:
        params.update(extra)
    li = xbmcgui.ListItem(label=label)
    xbmcplugin.addDirectoryItem(HANDLE, build_url(params), li, False)


def read_json_file(path: str, fallback: Any) -> Any:
    try:
        if not os.path.exists(path):
            return fallback
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data
    except Exception as exc:
        log(f"Could not read {path}: {exc}", xbmc.LOGWARNING)
        return fallback


def write_json_file(path: str, data: Any) -> None:
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except Exception as exc:
        log(f"Could not write {path}: {exc}", xbmc.LOGERROR)


def fav_load() -> List[Dict[str, str]]:
    data = read_json_file(FAV_FILE, [])
    return data if isinstance(data, list) else []


def fav_save(items: List[Dict[str, str]]) -> None:
    write_json_file(FAV_FILE, items)


def fav_is_saved(url: str) -> bool:
    clean_url = (url or "").strip()
    return any((item.get("url") or "").strip() == clean_url for item in fav_load())


def fav_add(name: str, url: str, thumb: str = "") -> None:
    clean_url = (url or "").strip()
    if not clean_url:
        notify("Cannot add an empty stream", icon=xbmcgui.NOTIFICATION_ERROR)
        return
    items = fav_load()
    if any((item.get("url") or "").strip() == clean_url for item in items):
        notify("Already in favourites")
        return
    items.append({"name": name or "Unknown", "url": clean_url, "thumb": thumb or ""})
    fav_save(items)
    notify("Added to favourites")


def fav_remove(url: str) -> None:
    clean_url = (url or "").strip()
    fav_save([item for item in fav_load() if (item.get("url") or "").strip() != clean_url])
    notify("Removed from favourites")


def clear_favourites() -> None:
    if xbmcgui.Dialog().yesno(ADDON_NAME, "Remove all saved favourites?"):
        fav_save([])
        notify("Favourites cleared")


def add_fav_context(li: xbmcgui.ListItem, name: str, play_url: str, thumb: str = "") -> None:
    if not play_url:
        return
    if fav_is_saved(play_url):
        cmd = f'RunPlugin({build_url({"mode": "fav_remove", "url": play_url})})'
        li.addContextMenuItems([("Remove from Media4u favourites", cmd)], replaceItems=False)
    else:
        cmd = f'RunPlugin({build_url({"mode": "fav_add", "name": name, "url": play_url, "thumb": thumb})})'
        li.addContextMenuItems([("Add to Media4u favourites", cmd)], replaceItems=False)


def add_playable(name: str, play_url: str, thumb: str = "", plot: str = "", year: Any = None) -> None:
    li = xbmcgui.ListItem(label=name)
    set_art(li, thumb)
    set_video_info(li, name, plot, year)
    li.setProperty("IsPlayable", "true")
    li.setPath(play_url)
    add_fav_context(li, name, play_url, thumb)
    xbmcplugin.addDirectoryItem(HANDLE, play_url, li, False)


def sorted_items(items: Iterable[Dict[str, Any]], name_key: str = "name") -> List[Dict[str, Any]]:
    return sorted(list(items), key=lambda i: (i.get(name_key) or i.get("category_name") or "").lower())


def list_categories(action: str, next_mode: str, title: str) -> None:
    xbmcplugin.setPluginCategory(HANDLE, title)
    xbmcplugin.setContent(HANDLE, "videos")
    data = http_get_json(xc_api_url(f"player_api.php?action={action}"), use_cache=False)
    if not isinstance(data, list) or not data:
        add_action("No categories found", "main")
        xbmcplugin.endOfDirectory(HANDLE)
        return
    for cat in sorted_items(data, "category_name"):
        name = cat.get("category_name") or "Unknown"
        cat_id = str(cat.get("category_id") or "")
        if cat_id:
            add_folder(name, next_mode, {"cat_id": cat_id})
    xbmcplugin.endOfDirectory(HANDLE)


def list_streams(content_type: str, cat_id: str = "", title: str = "") -> None:
    xbmcplugin.setPluginCategory(HANDLE, title or "Media4u TV")
    xbmcplugin.setContent(HANDLE, "videos")
    if content_type == "live":
        endpoint = f"player_api.php?action=get_live_streams&category_id={quote(cat_id)}"
    elif content_type == "vod":
        endpoint = f"player_api.php?action=get_vod_streams&category_id={quote(cat_id)}"
    else:
        endpoint = f"player_api.php?action=get_series&category_id={quote(cat_id)}"

    data = http_get_json_memory(xc_api_url(endpoint), ttl=5)
    if not isinstance(data, list) or not data:
        add_action("Nothing found", "main")
        xbmcplugin.endOfDirectory(HANDLE)
        return

    user, pwd, _label = get_effective_creds()
    for item in sorted_items(data):
        name = item.get("name") or "Unknown"
        icon = item.get("stream_icon") or item.get("cover") or item.get("cover_big") or ""
        plot = item.get("plot") or item.get("description") or ""
        year = item.get("year") or item.get("releaseDate") or None
        if content_type == "live":
            stream_id = item.get("stream_id")
            if stream_id is None:
                continue
            add_playable(name, f"{SERVER}/live/{quote(user)}/{quote(pwd)}/{stream_id}.ts", icon, plot, year)
        elif content_type == "vod":
            stream_id = item.get("stream_id")
            if stream_id is None:
                continue
            ext = item.get("container_extension") or "mp4"
            add_playable(name, f"{SERVER}/movie/{quote(user)}/{quote(pwd)}/{stream_id}.{ext}", icon, plot, year)
        else:
            series_id = str(item.get("series_id") or "")
            if not series_id:
                continue
            li = xbmcgui.ListItem(label=name)
            set_art(li, icon)
            set_video_info(li, name, plot, year)
            xbmcplugin.addDirectoryItem(HANDLE, build_url({"mode": "series_seasons", "series_id": series_id}), li, True)
    xbmcplugin.endOfDirectory(HANDLE)


def list_recent_vod() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Recently Added Movies")
    xbmcplugin.setContent(HANDLE, "movies")
    data = http_get_json(xc_api_url("player_api.php?action=get_vod_streams"))
    if not isinstance(data, list):
        data = []
    user, pwd, _label = get_effective_creds()
    recent = sorted(data, key=lambda i: safe_int(i.get("added")), reverse=True)[:100]
    for item in recent:
        name = item.get("name") or "Unknown"
        icon = item.get("stream_icon") or ""
        ext = item.get("container_extension") or "mp4"
        stream_id = item.get("stream_id")
        if stream_id is not None:
            add_playable(name, f"{SERVER}/movie/{quote(user)}/{quote(pwd)}/{stream_id}.{ext}", icon, item.get("plot") or "", item.get("year"))
    xbmcplugin.endOfDirectory(HANDLE)


def list_series_seasons(series_id: str) -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Series Seasons")
    xbmcplugin.setContent(HANDLE, "tvshows")
    data = http_get_json(xc_api_url(f"player_api.php?action=get_series_info&series_id={quote(series_id)}"))
    if not isinstance(data, dict):
        data = {}
    seasons = data.get("seasons") or []
    info = data.get("info") or {}
    cover = info.get("cover") or info.get("cover_big") or ""
    for season in seasons:
        season_num = str(season.get("season_number") or "")
        if not season_num:
            continue
        label = season.get("name") or f"Season {season_num}"
        li = xbmcgui.ListItem(label=label)
        set_art(li, season.get("cover") or cover)
        set_video_info(li, label, info.get("plot") or "")
        xbmcplugin.addDirectoryItem(HANDLE, build_url({"mode": "series_episodes", "series_id": series_id, "season": season_num}), li, True)
    xbmcplugin.endOfDirectory(HANDLE)


def list_series_episodes(series_id: str, season_num: str) -> None:
    xbmcplugin.setPluginCategory(HANDLE, f"Season {season_num}")
    xbmcplugin.setContent(HANDLE, "episodes")
    data = http_get_json(xc_api_url(f"player_api.php?action=get_series_info&series_id={quote(series_id)}"))
    if not isinstance(data, dict):
        data = {}
    episodes = (data.get("episodes") or {}).get(str(season_num)) or []
    user, pwd, _label = get_effective_creds()
    for ep in episodes:
        title = ep.get("title") or "Episode"
        ep_num = ep.get("episode_num")
        label = f"{ep_num}. {title}" if ep_num not in (None, "") else title
        ep_id = ep.get("id") or ep.get("episode_id")
        if not ep_id:
            continue
        info = ep.get("info") or {}
        thumb = info.get("movie_image") or info.get("cover_big") or info.get("cover") or ""
        ext = ep.get("container_extension") or "mp4"
        add_playable(label, f"{SERVER}/series/{quote(user)}/{quote(pwd)}/{ep_id}.{ext}", thumb, info.get("plot") or "", info.get("year"))
    xbmcplugin.endOfDirectory(HANDLE)


def favourites_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Favourites")
    xbmcplugin.setContent(HANDLE, "videos")
    items = fav_load()
    if not items:
        add_action("No favourites yet", "main")
    else:
        for item in items:
            add_playable(item.get("name") or "Unknown", item.get("url") or "", item.get("thumb") or "")
        add_action("Clear all favourites", "clear_favourites")
    xbmcplugin.endOfDirectory(HANDLE)


def normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    # Keep matching simple and reliable for channel names like
    # "Sky Sport 1", "SKY Sports News", "Sky-Sport-Select".
    for char in "._-:/\\|()[]{}+,&'\"":
        text = text.replace(char, " ")
    return " ".join(text.split())


def item_search_text(item: Dict[str, Any]) -> str:
    parts: List[str] = []
    keys = (
        "name", "title", "category_name", "plot", "description", "year",
        "releaseDate", "director", "cast", "genre", "rating", "tmdb_id",
        "stream_id", "series_id", "num", "container_extension"
    )
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            parts.append(str(value))
    info = item.get("info")
    if isinstance(info, dict):
        for value in info.values():
            if isinstance(value, (str, int, float)) and value not in (None, ""):
                parts.append(str(value))
    return normalize_text(" ".join(parts))


def matches_term(item: Dict[str, Any], term: str) -> bool:
    query = normalize_text(term)
    words = [w for w in query.split() if w]
    if not words:
        return False
    text = item_search_text(item)
    # Exact phrase first, then all words anywhere. This makes
    # "sky sport" match "Sky Sport 1" and related channel names.
    return query in text or all(word in text for word in words)


def add_search_result(label: str, kind: str, item: Dict[str, Any], user: str, pwd: str) -> bool:
    raw_name = item.get("name") or item.get("title") or "Unknown"
    name = f"{label}: {raw_name}"
    icon = item.get("stream_icon") or item.get("cover") or item.get("cover_big") or ""
    plot = item.get("plot") or item.get("description") or ""
    year = item.get("year") or item.get("releaseDate") or None
    if kind == "live" and item.get("stream_id") is not None:
        add_playable(name, f"{SERVER}/live/{quote(user)}/{quote(pwd)}/{item.get('stream_id')}.ts", icon, plot, year)
        return True
    if kind == "vod" and item.get("stream_id") is not None:
        ext = item.get("container_extension") or "mp4"
        add_playable(name, f"{SERVER}/movie/{quote(user)}/{quote(pwd)}/{item.get('stream_id')}.{ext}", icon, plot, year)
        return True
    if kind == "series" and item.get("series_id"):
        li = xbmcgui.ListItem(label=name)
        set_art(li, icon)
        set_video_info(li, name, plot, year)
        xbmcplugin.addDirectoryItem(HANDLE, build_url({"mode": "series_seasons", "series_id": str(item.get("series_id"))}), li, True)
        return True
    return False


def search_menu(kind_filter: str = "all") -> None:
    term = xbmcgui.Dialog().input("Search Media4u TV", type=xbmcgui.INPUT_ALPHANUM).strip()
    if not term:
        xbmcplugin.endOfDirectory(HANDLE)
        return

    xbmcplugin.setPluginCategory(HANDLE, f"Search: {term}")
    xbmcplugin.setContent(HANDLE, "videos")
    user, pwd, _label = get_effective_creds()
    all_sources = [
        ("Live", "player_api.php?action=get_live_streams", "live"),
        ("Movies", "player_api.php?action=get_vod_streams", "vod"),
        ("Series", "player_api.php?action=get_series", "series"),
    ]
    sources = [source for source in all_sources if kind_filter in ("all", source[2])]
    progress = xbmcgui.DialogProgress()
    progress.create(ADDON_NAME, "Searching...")
    found = 0

    try:
        for index, (label, endpoint, kind) in enumerate(sources):
            if progress.iscanceled():
                break
            progress.update(int((index / max(len(sources), 1)) * 100), f"Searching {label}...")
            data = http_get_json(xc_api_url(endpoint), use_cache=False)
            if not isinstance(data, list):
                continue
            matches = [item for item in data if isinstance(item, dict) and matches_term(item, term)]
            for item in sorted_items(matches)[:120]:
                if add_search_result(label, kind, item, user, pwd):
                    found += 1
        progress.update(100, "Done")
    finally:
        progress.close()

    if found == 0:
        add_action(f"No results for: {term}", "main")
        add_action("Tip: try one word only, like Batman, News, Sport, or 2025", "main")
        notify("No search results found")
    xbmcplugin.endOfDirectory(HANDLE)


def search_type_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Search")
    # These must be folders, not plain action items. On some Kodi builds,
    # non-playable action items do not open the keyboard/search route.
    add_folder("Search Everything", "search_all")
    add_folder("Search Live TV Channels", "search_live")
    add_folder("Search Movies", "search_vod")
    add_folder("Search Series", "search_series")
    xbmcplugin.endOfDirectory(HANDLE)


def account_status() -> None:
    data = http_get_json(xc_api_url("player_api.php"), use_cache=False)
    user, _pwd, label = get_effective_creds()
    lines = [f"Mode: {label}", f"Username: {user}"]
    if isinstance(data, dict):
        info = data.get("user_info") or {}
        if info:
            lines.extend([
                f"Status: {info.get('status', 'Unknown')}",
                f"Active connections: {info.get('active_cons', 'Unknown')}",
                f"Max connections: {info.get('max_connections', 'Unknown')}",
            ])
            exp = safe_int(info.get("exp_date"))
            if exp:
                lines.append("Expires: " + time.strftime("%Y-%m-%d", time.localtime(exp)))
    xbmcgui.Dialog().ok(ADDON_NAME, "\n".join(lines))


def connection_test() -> None:
    data = http_get_json(xc_api_url("player_api.php"), timeout=12, use_cache=False)
    if isinstance(data, dict):
        notify("Connection OK")
    else:
        notify("Connection failed", icon=xbmcgui.NOTIFICATION_ERROR)


def tools_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, "Tools")
    add_action("Account status", "account_status")
    add_action("Test connection", "connection_test")
    add_action("Clear API cache", "clear_cache")
    add_action("Clear favourites", "clear_favourites")
    add_action("Open Modern GUI", "modern_gui")
    add_action("Classic Kodi Menu", "classic_main")
    add_action("Settings", "open_settings")
    xbmcplugin.endOfDirectory(HANDLE)




HOME_ITEMS = [
    {"title": "Live TV", "subtitle": "", "section": "live"},
    {"title": "Movies", "subtitle": "", "section": "vod"},
    {"title": "Series", "subtitle": "", "section": "series"},
    {"title": "Recently Added", "subtitle": "", "section": "recent"},
    {"title": "Search", "subtitle": "", "section": "search"},
    {"title": "Favourites", "subtitle": "", "section": "favourites"},
    {"title": "Tools", "subtitle": "", "section": "tools"},
]


def gui_li(label: str, label2: str = "", icon: str = "") -> xbmcgui.ListItem:
    li = xbmcgui.ListItem(label=label, label2=label2)
    li.setProperty("subtitle", label2 or "")
    icon = icon or ADDON.getAddonInfo("icon")
    li.setArt({"icon": icon, "thumb": icon, "poster": icon})
    return li


def gui_endpoint_for_categories(content_type: str) -> Tuple[str, str]:
    if content_type == "live":
        return "player_api.php?action=get_live_categories", "Live TV"
    if content_type == "vod":
        return "player_api.php?action=get_vod_categories", "Movies"
    return "player_api.php?action=get_series_categories", "Series"


def gui_endpoint_for_streams(content_type: str, cat_id: str = "") -> str:
    if content_type == "live":
        return f"player_api.php?action=get_live_streams&category_id={quote(cat_id)}"
    if content_type == "vod":
        return f"player_api.php?action=get_vod_streams&category_id={quote(cat_id)}"
    return f"player_api.php?action=get_series&category_id={quote(cat_id)}"


def gui_play_url(content_type: str, item: Dict[str, Any]) -> str:
    user, pwd, _label = get_effective_creds()
    if content_type == "live" and item.get("stream_id") is not None:
        return f"{SERVER}/live/{quote(user)}/{quote(pwd)}/{item.get('stream_id')}.ts"
    if content_type == "vod" and item.get("stream_id") is not None:
        ext = item.get("container_extension") or "mp4"
        return f"{SERVER}/movie/{quote(user)}/{quote(pwd)}/{item.get('stream_id')}.{ext}"
    if content_type == "episode":
        ep_id = item.get("id") or item.get("episode_id")
        ext = item.get("container_extension") or "mp4"
        if ep_id:
            return f"{SERVER}/series/{quote(user)}/{quote(pwd)}/{ep_id}.{ext}"
    return ""



def clean_epg_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        import base64
        decoded = base64.b64decode(text, validate=True).decode("utf-8", "ignore").strip()
        if decoded and any(ch.isalpha() for ch in decoded):
            text = decoded
    except Exception:
        pass
    return " ".join(text.split())


def extract_now_next_from_item(item: Dict[str, Any]) -> str:
    # Some providers include guide data directly in the channel list. Use it first,
    # then fall back to get_short_epg when the row is selected.
    now_keys = (
        "now", "now_playing", "current", "current_program", "current_epg",
        "programme", "program", "title_now", "epg_now"
    )
    next_keys = (
        "next", "next_playing", "next_program", "next_epg",
        "title_next", "epg_next"
    )
    now_title = ""
    next_title = ""
    for key in now_keys:
        value = item.get(key)
        if isinstance(value, dict):
            value = value.get("title") or value.get("name") or value.get("description")
        now_title = clean_epg_text(value)
        if now_title:
            break
    for key in next_keys:
        value = item.get(key)
        if isinstance(value, dict):
            value = value.get("title") or value.get("name") or value.get("description")
        next_title = clean_epg_text(value)
        if next_title:
            break
    parts = []
    if now_title:
        parts.append(f"Now: {now_title}")
    if next_title:
        parts.append(f"Next: {next_title}")
    return "  |  ".join(parts)

def get_live_now_next(stream_id: Any) -> str:
    sid = str(stream_id or "").strip()
    if not sid:
        return ""
    if sid in EPG_CACHE:
        return EPG_CACHE[sid]
    try:
        data = http_get_json(xc_api_url(f"player_api.php?action=get_short_epg&stream_id={quote(sid)}&limit=2"), timeout=8, use_cache=False)
        programmes = []
        if isinstance(data, dict):
            programmes = data.get("epg_listings") or data.get("listings") or []
        elif isinstance(data, list):
            programmes = data
        labels = []
        for epg in programmes[:2]:
            if not isinstance(epg, dict):
                continue
            title = epg.get("title") or epg.get("name") or epg.get("description") or ""
            start = epg.get("start") or epg.get("start_timestamp") or epg.get("start_time") or ""
            prefix = "Now" if not labels else "Next"
            clean_title = clean_epg_text(title)
            if clean_title:
                labels.append(f"{prefix}: {clean_title}")
        result = "  |  ".join(labels)
        EPG_CACHE[sid] = result
        return result
    except Exception as exc:
        log(f"EPG lookup failed for {sid}: {exc}", xbmc.LOGWARNING)
        EPG_CACHE[sid] = ""
        return ""


def open_plugin_mode(mode: str) -> None:
    url = build_url({"mode": mode})
    xbmc.executebuiltin(f'ActivateWindow(Videos,"{url}",return)')



def li_to_state(li: xbmcgui.ListItem) -> Dict[str, Any]:
    props = {}
    for key in (
        "action", "section", "content_type", "cat_id", "series_id", "season",
        "play_url", "fav_url", "name", "thumb", "stream_id", "now_next",
        "now_next_loaded", "details", "subtitle"
    ):
        try:
            value = li.getProperty(key)
            if value:
                props[key] = value
        except Exception:
            pass
    icon = ""
    try:
        icon = li.getArt("thumb") or li.getArt("icon") or ""
    except Exception:
        pass
    return {
        "label": li.getLabel() or "",
        "label2": li.getLabel2() or "",
        "icon": icon,
        "props": props,
    }


def li_from_state(data: Dict[str, Any]) -> xbmcgui.ListItem:
    li = gui_li(data.get("label") or "", data.get("label2") or "", data.get("icon") or "")
    for key, value in (data.get("props") or {}).items():
        try:
            li.setProperty(key, value)
        except Exception:
            pass
    return li



class AsyncLoader:
    """Small worker loader for Kodi GUI network calls.

    Network/API work happens away from the GUI code path, while Kodi controls are
    only updated after the worker has finished. This keeps the GUI architecture
    cleaner and reduces focus/playback crashes caused by long blocking calls.
    """
    def __init__(self, owner=None):
        self.owner = owner

    def json(self, endpoint: str, label: str = "Loading...", timeout: int = 20, memory_ttl: int = 0, use_disk_cache: bool = False) -> Any:
        url = xc_api_url(endpoint)
        box = {"done": False, "data": None, "error": None}

        def worker():
            try:
                if memory_ttl > 0:
                    box["data"] = http_get_json_memory(url, timeout=timeout, ttl=memory_ttl)
                else:
                    box["data"] = http_get_json(url, timeout=timeout, use_cache=use_disk_cache)
            except Exception as exc:
                box["error"] = exc
                log("Async load failed:\n" + traceback.format_exc(), xbmc.LOGERROR)
            finally:
                box["done"] = True

        thread = threading.Thread(target=worker, name="BetaMedia4uLoader")
        thread.daemon = True
        progress = xbmcgui.DialogProgress()
        try:
            progress.create(ADDON_NAME, label)
            thread.start()
            tick = 0
            while not box["done"]:
                if progress.iscanceled():
                    raise RuntimeError("User cancelled loading")
                tick = (tick + 3) % 95
                progress.update(tick, label)
                xbmc.sleep(80)
            if box["error"]:
                raise box["error"]
            return box["data"]
        finally:
            try:
                progress.close()
            except Exception:
                pass


class GuiStateManager:
    """Owns saving and restoring the custom GUI state around playback."""
    RESTORE_PROP = "betamedia4u_restore_gui"

    def __init__(self, window):
        self.window = window

    def save(self) -> None:
        w = self.window
        try:
            state = {
                "section": w.current_section,
                "content_type": w.current_content_type,
                "title": w.current_title,
                "active_screen": w.active_screen,
                "cat_id": w.current_cat_id,
                "cat_label": w.current_cat_label,
                "nav": w.list_state(w.nav),
                "categories": w.list_state(w.categories),
                "items": w.list_state(w.items),
                "nav_pos": w.selected_pos(w.nav),
                "cat_pos": w.selected_pos(w.categories),
                "item_pos": w.selected_pos(w.items),
            }
            write_json_file(GUI_STATE_FILE, state)
            xbmcgui.Window(10000).setProperty(self.RESTORE_PROP, "true")
        except Exception:
            log("Could not save GUI state:\n" + traceback.format_exc(), xbmc.LOGWARNING)

    def restore(self) -> bool:
        w = self.window
        try:
            if xbmcgui.Window(10000).getProperty(self.RESTORE_PROP) != "true":
                return False
            data = read_json_file(GUI_STATE_FILE, {})
            xbmcgui.Window(10000).clearProperty(self.RESTORE_PROP)
            if not isinstance(data, dict):
                return False
            w.current_section = data.get("section") or "home"
            w.current_content_type = data.get("content_type") or ""
            w.current_title = data.get("title") or "Media4u TV"
            w.current_cat_id = data.get("cat_id") or ""
            w.current_cat_label = data.get("cat_label") or ""
            w.fill_list(w.nav, [li_from_state(x) for x in data.get("nav", [])] or [])
            if w.nav.size() == 0:
                w.setup_nav()
            w.fill_list(w.categories, [li_from_state(x) for x in data.get("categories", [])])
            w.fill_list(w.items, [li_from_state(x) for x in data.get("items", [])])
            w.set_header(w.current_title, "Returned to where playback started")
            w.set_details("Welcome back", "You are back where you were before playback.", ADDON.getAddonInfo("icon"))
            screen = data.get("active_screen") or "nav"
            if screen == "items" and w.items.size() == 0:
                screen = "categories" if w.categories.size() else "nav"
            if screen == "categories" and w.categories.size() == 0:
                screen = "nav"
            w.focus_screen(screen)
            try:
                if w.active_screen == "nav":
                    w.nav.selectItem(max(0, int(data.get("nav_pos", 0))))
                elif w.active_screen == "categories":
                    w.categories.selectItem(max(0, int(data.get("cat_pos", 0))))
                elif w.active_screen == "items":
                    w.items.selectItem(max(0, int(data.get("item_pos", 0))))
            except Exception:
                pass
            return True
        except Exception:
            log("Could not restore GUI state:\n" + traceback.format_exc(), xbmc.LOGWARNING)
            return False


class NavigationHistory:
    """Real in-GUI history stack, separate from the screen drawing code."""
    def __init__(self, window):
        self.window = window
        self.stack = []

    def snapshot(self):
        w = self.window
        cats = [w.categories.getListItem(i) for i in range(w.categories.size())]
        items = [w.items.getListItem(i) for i in range(w.items.size())]
        return (w.current_section, w.current_content_type, w.current_title, w.current_cat_id, w.current_cat_label, cats, items, w.active_screen)

    def push(self) -> None:
        try:
            self.stack.append(self.snapshot())
            if len(self.stack) > 40:
                self.stack = self.stack[-40:]
        except Exception:
            log("Navigation push failed", xbmc.LOGWARNING)

    def pop(self) -> bool:
        if not self.stack:
            return False
        w = self.window
        try:
            section, content_type, title, cat_id, cat_label, cats, items, screen = self.stack.pop()
            w.current_section = section
            w.current_content_type = content_type
            w.current_cat_id = cat_id
            w.current_cat_label = cat_label
            w.fill_list(w.categories, cats)
            w.fill_list(w.items, items)
            w.set_header(title, "")
            if screen == "items" and items:
                w.focus_screen("items")
            elif screen == "categories" and cats:
                w.focus_screen("categories")
            elif items:
                w.focus_screen("items")
            elif cats:
                w.focus_screen("categories")
            else:
                w.focus_screen("nav")
            return True
        except Exception:
            log("Navigation restore failed:\n" + traceback.format_exc(), xbmc.LOGERROR)
            return False


class PlaybackManager:
    """Playback handoff isolated from the GUI."""
    def __init__(self, window):
        self.window = window

    def play(self, li: xbmcgui.ListItem) -> None:
        w = self.window
        url = (li.getProperty("play_url") or "").strip()
        name = li.getProperty("name") or li.getLabel() or "Stream"
        thumb = li.getProperty("thumb") or ""
        if not url:
            notify("No playable URL", icon=xbmcgui.NOTIFICATION_ERROR)
            return
        if not url.lower().startswith(("http://", "https://")):
            notify("Bad stream URL", icon=xbmcgui.NOTIFICATION_ERROR)
            log(f"Playback blocked, unsupported URL for {name}: {url}", xbmc.LOGERROR)
            return
        try:
            item = xbmcgui.ListItem(label=name, path=url)
            set_art(item, thumb)
            item.setInfo("video", {"title": name})
            item.setProperty("IsPlayable", "true")
            try:
                item.setContentLookup(False)
            except Exception:
                pass
            lower = url.lower()
            if lower.endswith(".m3u8"):
                try: item.setMimeType("application/vnd.apple.mpegurl")
                except Exception: pass
            elif lower.endswith(".ts"):
                try: item.setMimeType("video/mp2t")
                except Exception: pass
            # Save GUI position, then hand playback to Kodi and return immediately.
            # Do NOT keep the plugin route blocked while the stream plays, because Kodi
            # will keep showing the "Working..." spinner until this callback exits.
            w.state_manager.save()
            root = xbmcgui.Window(10000)
            root.setProperty("betamedia4u_playback_pending", "true")
            root.setProperty("betamedia4u_playback_started", "false")
            root.setProperty("betamedia4u_playback_started_at", str(int(time.time())))
            log(f"Opening stream via PlaybackManager: {name}")
            w.set_busy(False)
            try:
                xbmc.executebuiltin("Dialog.Close(busydialog,true)")
                xbmc.executebuiltin("Dialog.Close(busydialognocancel,true)")
            except Exception:
                pass
            w.close_gui_safely()
            xbmc.sleep(120)
            player = xbmc.Player()
            player.play(url, item, False)
            xbmc.sleep(120)
            try:
                xbmc.executebuiltin("Dialog.Close(busydialog,true)")
                xbmc.executebuiltin("Dialog.Close(busydialognocancel,true)")
                xbmc.executebuiltin("ActivateWindow(fullscreenvideo)")
            except Exception:
                pass
            return
        except Exception:
            log("PlaybackManager failed:\n" + traceback.format_exc(), xbmc.LOGERROR)
            notify("Stream failed to open", icon=xbmcgui.NOTIFICATION_ERROR)
            try:
                w.set_busy(False)
                w.focus_active_list()
            except Exception:
                pass


class KodiActionMapper:
    """Maps remote, keyboard and mouse actions into stable GUI commands."""
    def __init__(self):
        self.context_ids = {117, 101}
        for name in ("ACTION_CONTEXT_MENU", "ACTION_MOUSE_RIGHT_CLICK"):
            if hasattr(xbmcgui, name):
                self.context_ids.add(getattr(xbmcgui, name))
        self.back_ids = {9, 10, 92}
        for name in ("ACTION_NAV_BACK", "ACTION_PREVIOUS_MENU", "ACTION_PARENT_DIR", "ACTION_PARENTDIR"):
            if hasattr(xbmcgui, name):
                self.back_ids.add(getattr(xbmcgui, name))
        self.select_ids = {xbmcgui.ACTION_SELECT_ITEM, xbmcgui.ACTION_MOUSE_LEFT_CLICK, 7, 100}
        for name in ("ACTION_ENTER", "ACTION_PLAYER_PLAY"):
            if hasattr(xbmcgui, name):
                self.select_ids.add(getattr(xbmcgui, name))

    def classify(self, action_id: int) -> str:
        if action_id in self.context_ids:
            return "context"
        if action_id in self.back_ids:
            return "back"
        if action_id in self.select_ids:
            return "select"
        if action_id == xbmcgui.ACTION_MOVE_DOWN:
            return "down"
        if action_id in (xbmcgui.ACTION_MOVE_LEFT, xbmcgui.ACTION_MOVE_RIGHT, xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_MOVE_DOWN):
            return "move"
        return "other"

class ModernHomeWindow(xbmcgui.WindowXMLDialog):
    CONTROL_NAV = 100
    CONTROL_CATEGORIES = 110
    CONTROL_ITEMS = 120
    CONTROL_TITLE = 200
    CONTROL_SUBTITLE = 201
    CONTROL_DETAILS_TITLE = 210
    CONTROL_DETAILS_TEXT = 211
    CONTROL_DETAILS_IMAGE = 212
    CONTROL_SEARCH = 300
    CONTROL_SETTINGS = 301
    CONTROL_BACK = 302

    def onInit(self) -> None:
        self.nav = self.getControl(self.CONTROL_NAV)
        self.categories = self.getControl(self.CONTROL_CATEGORIES)
        self.items = self.getControl(self.CONTROL_ITEMS)
        self.current_section = "home"
        self.current_content_type = ""
        self.current_title = "Media4u TV"
        self.active_screen = "nav"
        self.history: List[Tuple[str, str, str, List[xbmcgui.ListItem], List[xbmcgui.ListItem]]] = []
        self.current_cat_id = ""
        self.current_cat_label = ""
        self._last_back_time = 0
        self._last_action_time = 0
        self._is_busy = False
        self._allow_close = False
        self.loader = AsyncLoader(self)
        self.state_manager = GuiStateManager(self)
        self.nav_history = NavigationHistory(self)
        self.playback_manager = PlaybackManager(self)
        self.action_mapper = KodiActionMapper()
        self.setup_nav()
        if self.restore_after_playback():
            return
        self.set_header("Beta Media4u", "TV remote, keyboard and mouse ready.")
        self.set_details("Welcome", "Choose Live TV, Movies, Series, Search, Favourites or Tools.", ADDON.getAddonInfo("icon"))
        self.show_home_message()
        self.focus_screen("nav")

    def setup_nav(self) -> None:
        self.nav.reset()
        for entry in HOME_ITEMS:
            li = gui_li(entry["title"], entry["subtitle"])
            li.setProperty("section", entry["section"])
            self.nav.addItem(li)

    def set_header(self, title: str, subtitle: str = "") -> None:
        self.current_title = title
        try:
            self.getControl(self.CONTROL_TITLE).setLabel(title)
            self.getControl(self.CONTROL_SUBTITLE).setLabel(subtitle)
        except Exception:
            pass

    def set_details(self, title: str, text: str = "", icon: str = "") -> None:
        try:
            self.getControl(self.CONTROL_DETAILS_TITLE).setLabel(title or "")
            self.getControl(self.CONTROL_DETAILS_TEXT).setText(text or "")
            self.getControl(self.CONTROL_DETAILS_IMAGE).setImage(icon or ADDON.getAddonInfo("icon"))
        except Exception:
            pass

    def reset_panel(self, control) -> None:
        try:
            control.reset()
        except Exception:
            pass

    def show_only(self, screen: str) -> None:
        """Single-screen navigation: main menu OR section list OR content list, never side-by-side."""
        self.active_screen = screen
        try:
            self.nav.setVisible(screen == "nav")
            self.categories.setVisible(screen == "categories")
            self.items.setVisible(screen == "items")
        except Exception:
            pass

    def focus_screen(self, screen: str) -> None:
        self.show_only(screen)
        try:
            if screen == "nav":
                self.setFocus(self.nav)
            elif screen == "categories":
                self.setFocus(self.categories)
            else:
                self.setFocus(self.items)
        except Exception:
            pass

    def fill_list(self, control, items: List[xbmcgui.ListItem]) -> None:
        control.reset()
        for li in items:
            control.addItem(li)

    def placeholder(self, label: str, sub: str = "") -> xbmcgui.ListItem:
        li = gui_li(label, "")
        li.setProperty("action", "none")
        return li

    def back_item(self) -> xbmcgui.ListItem:
        li = gui_li("‹ Back", "")
        li.setProperty("action", "back")
        return li

    def add_back_first(self, items: List[xbmcgui.ListItem]) -> List[xbmcgui.ListItem]:
        return [self.back_item()] + items

    def snapshot(self) -> Tuple[str, str, str, List[xbmcgui.ListItem], List[xbmcgui.ListItem]]:
        cats = [self.categories.getListItem(i) for i in range(self.categories.size())]
        items = [self.items.getListItem(i) for i in range(self.items.size())]
        return (self.current_section, self.current_content_type, self.current_title, cats, items)

    def list_state(self, control) -> List[Dict[str, Any]]:
        try:
            return [li_to_state(control.getListItem(i)) for i in range(control.size())]
        except Exception:
            return []

    def selected_pos(self, control) -> int:
        try:
            return int(control.getSelectedPosition())
        except Exception:
            return 0

    def save_playback_state(self) -> None:
        self.state_manager.save()

    def restore_after_playback(self) -> bool:
        return self.state_manager.restore()

    def push_state(self) -> None:
        self.nav_history.push()

    def restore_state(self) -> bool:
        return self.nav_history.pop()

    def loading(self, message: str) -> xbmcgui.DialogProgress:
        progress = xbmcgui.DialogProgress()
        progress.create(ADDON_NAME, message)
        return progress

    def show_home_message(self) -> None:
        self.fill_list(self.categories, [])
        self.fill_list(self.items, [])
        self.show_only("nav")

    def select_nav(self) -> None:
        li = self.nav.getSelectedItem()
        if not li:
            return
        section = li.getProperty("section")
        self.current_section = section
        if section in ("live", "vod", "series"):
            self.load_categories(section)
        elif section == "recent":
            self.load_recent()
        elif section == "search":
            self.show_search_panel()
        elif section == "favourites":
            self.load_favourites()
        elif section == "tools":
            self.show_tools()

    def load_categories(self, content_type: str) -> None:
        endpoint, title = gui_endpoint_for_categories(content_type)
        self.current_content_type = content_type
        data = self.loader.json(endpoint, f"Loading {title} categories...", timeout=18, use_disk_cache=False)
        cats: List[xbmcgui.ListItem] = []
        if isinstance(data, list):
            all_li = gui_li("All", "")
            all_li.setProperty("action", "category")
            all_li.setProperty("content_type", content_type)
            all_li.setProperty("cat_id", "")
            cats.append(all_li)
            for cat in sorted_items(data, "category_name"):
                name = cat.get("category_name") or "Unknown"
                cat_id = str(cat.get("category_id") or "")
                if not cat_id:
                    continue
                li = gui_li(name, "")
                li.setProperty("action", "category")
                li.setProperty("content_type", content_type)
                li.setProperty("cat_id", cat_id)
                cats.append(li)
        if not cats:
            cats = [self.placeholder("No categories found", "The API returned no categories")]
        self.fill_list(self.categories, self.add_back_first(cats))
        self.fill_list(self.items, [])
        self.set_header(title, "")
        self.set_details(title, "", ADDON.getAddonInfo("icon"))
        self.focus_screen("categories")

    def load_category_items(self) -> None:
        if getattr(self, "_is_busy", False):
            return
        self.set_busy(True)
        li = self.categories.getSelectedItem()
        if not li or li.getProperty("action") != "category":
            self.set_busy(False)
            return
        content_type = li.getProperty("content_type") or self.current_content_type
        cat_id = li.getProperty("cat_id")
        label = li.getLabel()
        self.current_cat_id = cat_id or ""
        self.current_cat_label = label or ""
        try:
            data = self.loader.json(gui_endpoint_for_streams(content_type, cat_id), f"Loading {label}...", timeout=18, memory_ttl=3)
            self.push_state()
            self.fill_list(self.items, self.add_back_first(self.make_content_items(content_type, data)))
            self.set_header(label, "")
            self.focus_screen("items")
        except Exception as exc:
            log(f"Category load failed safely: {exc}", xbmc.LOGERROR)
            notify("Could not load category", icon=xbmcgui.NOTIFICATION_ERROR)
            self.focus_active_list()
        finally:
            self.set_busy(False)

    def make_content_items(self, content_type: str, data: Any) -> List[xbmcgui.ListItem]:
        out: List[xbmcgui.ListItem] = []
        if isinstance(data, list):
            for item in sorted_items(data):
                if not isinstance(item, dict):
                    continue
                name = item.get("name") or item.get("title") or "Unknown"
                icon = item.get("stream_icon") or item.get("cover") or item.get("cover_big") or ""
                plot = item.get("plot") or item.get("description") or ""
                if content_type in ("live", "vod"):
                    url = gui_play_url(content_type, item)
                    if not url:
                        continue
                    li = gui_li(name, "", icon)
                    li.setProperty("action", "play")
                    li.setProperty("play_url", url)
                    li.setProperty("name", name)
                    li.setProperty("thumb", icon)
                    li.setProperty("content_type", content_type)
                    li.setProperty("stream_id", str(item.get("stream_id") or ""))
                    if content_type == "live":
                        inline_epg = extract_now_next_from_item(item)
                        if inline_epg:
                            li.setLabel2(inline_epg)
                            li.setProperty("now_next", inline_epg)
                            li.setProperty("now_next_loaded", "true")
                            li.setProperty("details", inline_epg)
                        else:
                            li.setLabel2("Select channel to load now/next")
                    li.setProperty("details", (li.getProperty("details") or plot or name))
                    out.append(li)
                else:
                    series_id = str(item.get("series_id") or "")
                    if not series_id:
                        continue
                    li = gui_li(name, plot or "Press OK to open seasons", icon)
                    li.setProperty("action", "series_seasons")
                    li.setProperty("series_id", series_id)
                    li.setProperty("name", name)
                    li.setProperty("thumb", icon)
                    li.setProperty("fav_url", f"series://{series_id}")
                    li.setProperty("details", plot or name)
                    out.append(li)
        return out or [self.placeholder("Nothing found", "No items were returned by the API")]

    def load_recent(self) -> None:
        self.current_content_type = "vod"
        data = self.loader.json("player_api.php?action=get_vod_streams", "Loading recently added movies...", timeout=18, memory_ttl=5)
        if isinstance(data, list):
            data = sorted(data, key=lambda i: safe_int(i.get("added")), reverse=True)[:200]
        self.fill_list(self.categories, [self.placeholder("Recently Added", "Newest movies from the API")])
        self.fill_list(self.items, self.add_back_first(self.make_content_items("vod", data)))
        self.set_header("Recently Added", "Newest movies loaded fresh from the API")
        self.focus_screen("items")

    def show_search_panel(self) -> None:
        options = [("Search Everything", "all"), ("Search Live TV", "live"), ("Search Movies", "vod"), ("Search Series", "series")]
        cats: List[xbmcgui.ListItem] = []
        for title, kind in options:
            li = gui_li(title, "")
            li.setProperty("action", "search")
            li.setProperty("kind", kind)
            cats.append(li)
        self.fill_list(self.categories, self.add_back_first(cats))
        self.fill_list(self.items, [])
        self.set_header("Search", "")
        self.focus_screen("categories")

    def run_search(self) -> None:
        li = self.categories.getSelectedItem()
        kind_filter = li.getProperty("kind") if li else "all"
        term = xbmcgui.Dialog().input("Search Media4u TV", type=xbmcgui.INPUT_ALPHANUM).strip()
        if not term:
            return
        sources = [
            ("Live", "player_api.php?action=get_live_streams", "live"),
            ("Movies", "player_api.php?action=get_vod_streams", "vod"),
            ("Series", "player_api.php?action=get_series", "series"),
        ]
        sources = [s for s in sources if kind_filter in ("all", s[2])]
        results: List[xbmcgui.ListItem] = []
        progress = self.loading("Searching full API lists...")
        try:
            for idx, (label, endpoint, kind) in enumerate(sources):
                progress.update(int(idx / max(len(sources), 1) * 100), f"Searching {label}...")
                data = self.loader.json(endpoint, f"Searching {label}...", timeout=20, memory_ttl=5)
                if not isinstance(data, list):
                    continue
                matches = [i for i in data if isinstance(i, dict) and matches_term(i, term)]
                for item in sorted_items(matches)[:200]:
                    raw_name = item.get("name") or item.get("title") or "Unknown"
                    icon = item.get("stream_icon") or item.get("cover") or item.get("cover_big") or ""
                    plot = item.get("plot") or item.get("description") or ""
                    li2 = gui_li(f"{label}: {raw_name}", "", icon)
                    if kind in ("live", "vod"):
                        url = gui_play_url(kind, item)
                        if not url:
                            continue
                        li2.setProperty("action", "play")
                        li2.setProperty("play_url", url)
                        li2.setProperty("name", raw_name)
                        li2.setProperty("thumb", icon)
                        li2.setProperty("content_type", kind)
                        li2.setProperty("stream_id", str(item.get("stream_id") or ""))
                        if kind == "live":
                            inline_epg = extract_now_next_from_item(item)
                            if inline_epg:
                                li2.setLabel2(inline_epg)
                                li2.setProperty("now_next", inline_epg)
                                li2.setProperty("now_next_loaded", "true")
                                li2.setProperty("details", inline_epg)
                            else:
                                li2.setLabel2("Select channel to load now/next")
                    else:
                        series_id = str(item.get("series_id") or "")
                        if not series_id:
                            continue
                        li2.setProperty("action", "series_seasons")
                        li2.setProperty("series_id", series_id)
                        li2.setProperty("name", raw_name)
                        li2.setProperty("thumb", icon)
                        li2.setProperty("fav_url", f"series://{series_id}")
                    li2.setProperty("details", plot or raw_name)
                    results.append(li2)
            progress.update(100, "Done")
        finally:
            progress.close()
        self.push_state()
        self.fill_list(self.categories, [])
        self.fill_list(self.items, self.add_back_first(results or [self.placeholder(f"No results for: {term}", "Try one word only, like sport, sky, news, or movie title")]))
        self.set_header(f"Search: {term}", "")
        self.focus_screen("items")

    def load_favourites(self) -> None:
        favs = fav_load()
        items: List[xbmcgui.ListItem] = []
        for fav in favs:
            fav_url = fav.get("url") or ""
            li = gui_li(fav.get("name") or "Unknown", "", fav.get("thumb") or "")
            if fav_url.startswith("series://"):
                li.setProperty("action", "series_seasons")
                li.setProperty("series_id", fav_url.replace("series://", "", 1))
                li.setProperty("fav_url", fav_url)
            else:
                li.setProperty("action", "play")
                li.setProperty("play_url", fav_url)
            li.setProperty("name", fav.get("name") or "Unknown")
            li.setProperty("thumb", fav.get("thumb") or "")
            items.append(li)
        self.push_state()
        self.fill_list(self.categories, [])
        self.fill_list(self.items, self.add_back_first(items or [self.placeholder("No favourites yet", "Use right-click or C to save favourites")]))
        self.set_header("Favourites", "")
        self.focus_screen("items")

    def show_tools(self) -> None:
        tools = [
            ("Account status", "account_status", "View username, status and connections"),
            ("Test connection", "connection_test", "Check API connection"),
            ("Clear API cache", "clear_cache", "Clear old API cache if used"),
            ("Clear favourites", "clear_favourites", "Remove saved favourites"),
            ("Classic Kodi Menu", "classic", "Open standard Kodi directory menu"),
            ("Settings", "settings", "Open add-on settings"),
        ]
        cats: List[xbmcgui.ListItem] = []
        for title, action, sub in tools:
            li = gui_li(title, "")
            li.setProperty("action", action)
            cats.append(li)
        self.fill_list(self.categories, self.add_back_first(cats))
        self.fill_list(self.items, [])
        self.set_header("Tools", "")
        self.focus_screen("categories")

    def load_series_seasons(self, series_id: str) -> None:
        self.push_state()
        data = self.loader.json(f"player_api.php?action=get_series_info&series_id={quote(series_id)}", "Loading seasons...", timeout=18, use_disk_cache=False)
        cats: List[xbmcgui.ListItem] = []
        if isinstance(data, dict):
            seasons = data.get("seasons") or []
            info = data.get("info") or {}
            cover = info.get("cover") or info.get("cover_big") or ""
            for season in seasons:
                season_num = str(season.get("season_number") or "")
                if not season_num:
                    continue
                label = season.get("name") or f"Season {season_num}"
                li = gui_li(label, "", season.get("cover") or cover)
                li.setProperty("action", "season")
                li.setProperty("series_id", series_id)
                li.setProperty("season", season_num)
                cats.append(li)
        self.fill_list(self.categories, self.add_back_first(cats or [self.placeholder("No seasons found", "The API returned no seasons")]))
        self.fill_list(self.items, [])
        self.set_header("Series Seasons", "")
        self.focus_screen("categories")

    def load_series_episodes(self) -> None:
        li = self.categories.getSelectedItem()
        if not li:
            return
        series_id = li.getProperty("series_id")
        season = li.getProperty("season")
        data = self.loader.json(f"player_api.php?action=get_series_info&series_id={quote(series_id)}", "Loading episodes...", timeout=18, use_disk_cache=False)
        out: List[xbmcgui.ListItem] = []
        if isinstance(data, dict):
            episodes = (data.get("episodes") or {}).get(str(season)) or []
            for ep in episodes:
                title = ep.get("title") or "Episode"
                ep_num = ep.get("episode_num")
                label = f"{ep_num}. {title}" if ep_num not in (None, "") else title
                info = ep.get("info") or {}
                thumb = info.get("movie_image") or info.get("cover_big") or info.get("cover") or ""
                url = gui_play_url("episode", ep)
                if not url:
                    continue
                item = gui_li(label, "", thumb)
                item.setProperty("action", "play")
                item.setProperty("play_url", url)
                item.setProperty("name", label)
                item.setProperty("thumb", thumb)
                item.setProperty("details", info.get("plot") or label)
                out.append(item)
        self.push_state()
        self.fill_list(self.items, self.add_back_first(out or [self.placeholder("No episodes found", "No episodes were returned")]))
        self.set_header(f"Season {season}", "")
        self.focus_screen("items")

    def save_focus_marker(self) -> None:
        """Save the exact visible row before playback or window focus changes."""
        try:
            marker = {
                "active_screen": self.active_screen,
                "nav_pos": self.selected_pos(self.nav),
                "cat_pos": self.selected_pos(self.categories),
                "item_pos": self.selected_pos(self.items),
                "title": self.current_title,
            }
            xbmcgui.Window(10000).setProperty("betamedia4u_focus_marker", json.dumps(marker))
        except Exception:
            pass

    def restore_focus_marker(self) -> None:
        """Restore keyboard/remote focus after Windows alt-tab or Kodi window refocus."""
        try:
            raw = xbmcgui.Window(10000).getProperty("betamedia4u_focus_marker")
            marker = json.loads(raw) if raw else {}
            screen = marker.get("active_screen") or self.active_screen or "nav"
            if screen == "items" and self.items.size() == 0:
                screen = "categories" if self.categories.size() else "nav"
            if screen == "categories" and self.categories.size() == 0:
                screen = "nav"
            self.focus_screen(screen)
            if screen == "items":
                self.items.selectItem(min(max(0, int(marker.get("item_pos", 0))), max(0, self.items.size() - 1)))
            elif screen == "categories":
                self.categories.selectItem(min(max(0, int(marker.get("cat_pos", 0))), max(0, self.categories.size() - 1)))
            else:
                self.nav.selectItem(min(max(0, int(marker.get("nav_pos", 0))), max(0, self.nav.size() - 1)))
            self.update_details_from_focus()
        except Exception:
            self.focus_active_list()

    def play_item(self, li: xbmcgui.ListItem) -> None:
        if getattr(self, "_is_busy", False):
            return
        self.set_busy(True)
        try:
            self.save_focus_marker()
            self.playback_manager.play(li)
        finally:
            # PlaybackManager may close the GUI. If it does not, make sure the UI is usable again.
            try:
                self.set_busy(False)
            except Exception:
                pass

    def handle_category_action(self) -> None:
        li = self.categories.getSelectedItem()
        if not li:
            return
        action = li.getProperty("action")
        if action == "back":
            self.go_back()
        elif action == "category":
            self.load_category_items()
        elif action == "search":
            self.run_search()
        elif action == "season":
            self.load_series_episodes()
        elif action == "account_status":
            account_status()
        elif action == "connection_test":
            connection_test()
        elif action == "clear_cache":
            clear_cache()
        elif action == "clear_favourites":
            clear_favourites(); self.load_favourites()
        elif action == "classic":
            self.close(); xbmc.sleep(150); open_plugin_mode("classic_main")
        elif action == "settings":
            ADDON.openSettings()

    def handle_item_action(self) -> None:
        li = self.items.getSelectedItem()
        if not li:
            return
        action = li.getProperty("action")
        if action == "back":
            self.go_back()
        elif action == "play":
            self.play_item(li)
        elif action == "series_seasons":
            self.load_series_seasons(li.getProperty("series_id"))

    def selected_visible_item(self) -> Optional[xbmcgui.ListItem]:
        try:
            focus = self.getFocusId()
            if focus == self.CONTROL_NAV and self.active_screen == "nav":
                return self.nav.getSelectedItem()
            if focus == self.CONTROL_CATEGORIES and self.active_screen == "categories":
                return self.categories.getSelectedItem()
            if focus == self.CONTROL_ITEMS and self.active_screen == "items":
                return self.items.getSelectedItem()
        except Exception:
            pass
        try:
            if self.active_screen == "items":
                return self.items.getSelectedItem()
            if self.active_screen == "categories":
                return self.categories.getSelectedItem()
            return self.nav.getSelectedItem()
        except Exception:
            return None

    def show_context_menu(self) -> None:
        li = self.selected_visible_item()
        if not li:
            return
        action = li.getProperty("action")
        label = li.getProperty("name") or li.getLabel()
        url = li.getProperty("play_url") or li.getProperty("fav_url") or ""
        options = []
        actions = []
        if action == "play" and li.getProperty("play_url"):
            options.append("Play")
            actions.append("play")
        elif action == "series_seasons":
            options.append("Open")
            actions.append("open_series")
        if url and action in ("play", "series_seasons"):
            if fav_is_saved(url):
                options.append("Remove from favourites")
                actions.append("fav_remove")
            else:
                options.append("Add to favourites")
                actions.append("fav_add")
        if li.getProperty("content_type") == "live" or li.getProperty("now_next"):
            options.append("Show now/next")
            actions.append("info")
        options.extend(["Back", "Settings"])
        actions.extend(["back", "settings"])
        choice = xbmcgui.Dialog().contextmenu(options)
        if choice < 0:
            return
        selected = actions[choice]
        if selected == "play":
            self.play_item(li)
        elif selected == "open_series":
            self.load_series_seasons(li.getProperty("series_id"))
        elif selected == "fav_add":
            fav_add(label, url, li.getProperty("thumb") or li.getArt("thumb") or "")
        elif selected == "fav_remove":
            fav_remove(url)
            if self.current_section == "favourites":
                self.load_favourites()
        elif selected == "info":
            self.maybe_update_selected_epg(li)
            xbmcgui.Dialog().ok(label, li.getProperty("now_next") or "No EPG now/next data available for this channel.")
        elif selected == "back":
            self.go_back()
        elif selected == "settings":
            ADDON.openSettings()

    def focus_active_list(self) -> None:
        """Return focus from top-bar buttons to the list that is visible on the current screen."""
        try:
            if self.active_screen == "items" and self.items.size() > 0:
                self.setFocus(self.items)
            elif self.active_screen == "categories" and self.categories.size() > 0:
                self.setFocus(self.categories)
            else:
                self.setFocus(self.nav)
        except Exception:
            pass

    def maybe_update_selected_epg(self, li: xbmcgui.ListItem) -> None:
        try:
            if li.getProperty("content_type") != "live":
                return
            if li.getProperty("now_next_loaded") == "true":
                return
            sid = li.getProperty("stream_id")
            if not sid:
                return
            now_next = get_live_now_next(sid)
            li.setProperty("now_next_loaded", "true")
            if now_next:
                li.setProperty("now_next", now_next)
                li.setLabel2(now_next)
                if not li.getProperty("details") or li.getProperty("details") == li.getLabel():
                    li.setProperty("details", now_next)
            else:
                li.setLabel2("No EPG data available")
                if not li.getProperty("details") or li.getProperty("details") == li.getLabel():
                    li.setProperty("details", "No EPG now/next data available for this channel.")
        except Exception as exc:
            log(f"Lazy EPG update failed: {exc}", xbmc.LOGWARNING)


    def update_details_from_focus(self) -> None:
        try:
            focus = self.getFocusId()
            li = None
            if focus == self.CONTROL_NAV:
                li = self.nav.getSelectedItem()
            elif focus == self.CONTROL_CATEGORIES:
                li = self.categories.getSelectedItem()
            elif focus == self.CONTROL_ITEMS:
                li = self.items.getSelectedItem()
            if li:
                self.set_details(li.getLabel(), li.getProperty("details") or li.getLabel2() or li.getProperty("subtitle"), li.getArt("thumb") or li.getArt("icon"))
        except Exception:
            pass


    def allow_action(self, min_gap_ms: int = 180) -> bool:
        """Debounce OK/Back/context actions from remotes, keyboards and mice.

        Some Kodi builds can send duplicate events for the same key press.
        Debouncing prevents double-open, double-back and close-while-loading crashes.
        """
        try:
            if getattr(self, "_is_busy", False):
                return False
            now_ms = int(time.time() * 1000)
            if now_ms - int(getattr(self, "_last_action_time", 0)) < min_gap_ms:
                return False
            self._last_action_time = now_ms
        except Exception:
            pass
        return True

    def set_busy(self, busy: bool) -> None:
        try:
            self._is_busy = bool(busy)
        except Exception:
            pass

    def onClick(self, control_id: int) -> None:
        if not self.allow_action():
            return
        if control_id == self.CONTROL_NAV:
            self.select_nav()
        elif control_id == self.CONTROL_CATEGORIES:
            self.handle_category_action()
        elif control_id == self.CONTROL_ITEMS:
            self.handle_item_action()
        elif control_id == self.CONTROL_SEARCH:
            self.show_search_panel()
        elif control_id == self.CONTROL_SETTINGS:
            ADDON.openSettings()
        elif control_id == self.CONTROL_BACK:
            try:
                self.go_back()
            except Exception as exc:
                log(f"Top back failed safely: {exc}", xbmc.LOGERROR)
                self.focus_active_list()

    def go_back(self) -> None:
        """Safe Back handling for Kodi keyboard/remotes.

        Back should step through the GUI history first. On the home screen it no
        longer closes immediately, because rapid Back presses on Kodi v21/v22 can
        close the dialog while controls are still updating and may crash Kodi on
        some Windows/Android builds.
        """
        try:
            if self.active_screen == "items":
                if self.restore_state():
                    return
                if self.categories.size() > 0:
                    self.focus_screen("categories")
                    return
                self.focus_screen("nav")
                self.set_header("Beta Media4u", "TV remote, keyboard and mouse ready.")
                return

            if self.active_screen == "categories":
                if self.restore_state():
                    return
                self.focus_screen("nav")
                self.set_header("Beta Media4u", "TV remote, keyboard and mouse ready.")
                return

            # Home screen: ask before closing. This prevents accidental rapid Back presses
            # from tearing down the dialog while Kodi is changing focus.
            self.focus_screen("nav")
            if xbmcgui.Dialog().yesno(ADDON_NAME, "Close Beta Media4u?"):
                self.close_gui_safely()
            else:
                self.set_header("Beta Media4u", "TV remote, keyboard and mouse ready.")
                self.set_details("Main menu", "Choose a section to open.", ADDON.getAddonInfo("icon"))
        except Exception as exc:
            log(f"Safe back failed: {exc}", xbmc.LOGERROR)
            try:
                self.focus_active_list()
            except Exception:
                pass

    def close_gui_safely(self) -> None:
        try:
            self._allow_close = True
            self.close()
        except Exception as exc:
            log(f"Safe close failed: {exc}", xbmc.LOGERROR)
            self.focus_active_list()

    def onFocus(self, control_id: int) -> None:
        """Recover focus if Kodi XML navigation lands on a hidden list after using top buttons."""
        try:
            hidden_nav = self.active_screen != "nav" and control_id == self.CONTROL_NAV
            hidden_categories = self.active_screen != "categories" and control_id == self.CONTROL_CATEGORIES
            hidden_items = self.active_screen != "items" and control_id == self.CONTROL_ITEMS
            if hidden_nav or hidden_categories or hidden_items:
                xbmc.executebuiltin("AlarmClock(media4u_refocus,noop,00:00,silent)")
                xbmc.sleep(10)
                self.focus_active_list()
            else:
                self.update_details_from_focus()
        except Exception:
            pass

    def onAction(self, action) -> None:
        action_id = action.getId()
        command = self.action_mapper.classify(action_id)
        top_controls = (self.CONTROL_SEARCH, self.CONTROL_SETTINGS, self.CONTROL_BACK)
        try:
            focus_id = self.getFocusId()
        except Exception:
            focus_id = -1

        # Windows can return Kodi focus without a focused control after alt-tab or
        # clicking the Kodi window border. Recover focus before handling keys.
        if focus_id in (-1, 0, None):
            self.restore_focus_marker()
            try:
                focus_id = self.getFocusId()
            except Exception:
                focus_id = -1

        if command in ("move", "select", "context"):
            self.save_focus_marker()

        if command == "down" and focus_id in top_controls:
            self.focus_active_list()
            return

        if command == "move":
            if self.active_screen == "items" and focus_id in (self.CONTROL_NAV, self.CONTROL_CATEGORIES):
                self.focus_active_list(); return
            if self.active_screen == "categories" and focus_id in (self.CONTROL_NAV, self.CONTROL_ITEMS):
                self.focus_active_list(); return
            if self.active_screen == "nav" and focus_id in (self.CONTROL_CATEGORIES, self.CONTROL_ITEMS):
                self.focus_active_list(); return

        if command == "context":
            if self.allow_action():
                self.show_context_menu()
            return

        if command == "back":
            if self.allow_action(160):
                self.go_back()
            return

        if command == "select":
            if not self.allow_action():
                return
            try:
                focus = self.getFocusId()
                if focus == self.CONTROL_NAV:
                    self.select_nav()
                elif focus == self.CONTROL_CATEGORIES:
                    self.handle_category_action()
                elif focus == self.CONTROL_ITEMS:
                    self.handle_item_action()
                elif focus == self.CONTROL_SEARCH:
                    self.show_search_panel()
                elif focus == self.CONTROL_SETTINGS:
                    ADDON.openSettings()
                elif focus == self.CONTROL_BACK:
                    self.go_back()
                else:
                    self.focus_active_list()
            except Exception:
                log("GUI action failed:\n" + traceback.format_exc(), xbmc.LOGERROR)
                notify("Action failed", icon=xbmcgui.NOTIFICATION_ERROR)
            return
        self.update_details_from_focus()


def modern_gui() -> None:
    try:
        win = ModernHomeWindow("media4u_home.xml", ADDON.getAddonInfo("path"), "Default", "1080i")
        win.doModal()
        del win
    except Exception as exc:
        log(f"Modern GUI failed: {exc}", xbmc.LOGERROR)
        notify("Modern GUI could not open", icon=xbmcgui.NOTIFICATION_ERROR)
        main_menu()

def main_menu() -> None:
    xbmcplugin.setPluginCategory(HANDLE, ADDON_NAME)
    xbmcplugin.setContent(HANDLE, "videos")
    add_action("Open Modern GUI", "modern_gui")
    if setting_bool("show_account_status", True):
        _user, _pwd, label = get_effective_creds()
        add_action(f"Account: {label}", "account_status")
    add_folder("Live TV", "live_categories")
    add_folder("Movies", "vod_categories")
    add_folder("Recently Added Movies", "recent_vod")
    add_folder("Series", "series_categories")
    add_folder("Search", "search")
    add_folder("Favourites", "favourites")
    add_folder("Tools", "tools")
    xbmcplugin.endOfDirectory(HANDLE)


def router(paramstring: str) -> None:
    params = dict(urllib.parse.parse_qsl(paramstring or ""))
    mode = params.get("mode") or "main"
    if mode == "main":
        if setting_bool("use_modern_gui", True):
            modern_gui()
        else:
            main_menu()
    elif mode == "classic_main":
        main_menu()
    elif mode == "modern_gui":
        modern_gui()
    elif mode == "open_settings":
        ADDON.openSettings()
    elif mode == "tools":
        tools_menu()
    elif mode == "account_status":
        account_status()
    elif mode == "connection_test":
        connection_test()
    elif mode == "clear_cache":
        clear_cache()
        xbmc.executebuiltin("Container.Refresh")
    elif mode == "clear_favourites":
        clear_favourites()
        xbmc.executebuiltin("Container.Refresh")
    elif mode == "favourites":
        favourites_menu()
    elif mode == "fav_add":
        fav_add(params.get("name") or "Unknown", params.get("url") or "", params.get("thumb") or "")
        xbmc.executebuiltin("Container.Refresh")
    elif mode == "fav_remove":
        fav_remove(params.get("url") or "")
        xbmc.executebuiltin("Container.Refresh")
    elif mode == "search":
        search_type_menu()
    elif mode == "search_all":
        search_menu("all")
    elif mode == "search_live":
        search_menu("live")
    elif mode == "search_vod":
        search_menu("vod")
    elif mode == "search_series":
        search_menu("series")
    elif mode == "live_categories":
        list_categories("get_live_categories", "live_streams", "Live TV")
    elif mode == "vod_categories":
        list_categories("get_vod_categories", "vod_streams", "Movies")
    elif mode == "series_categories":
        list_categories("get_series_categories", "series_list", "Series")
    elif mode == "live_streams":
        list_streams("live", params.get("cat_id") or "", "Live TV")
    elif mode == "vod_streams":
        list_streams("vod", params.get("cat_id") or "", "Movies")
    elif mode == "series_list":
        list_streams("series", params.get("cat_id") or "", "Series")
    elif mode == "recent_vod":
        list_recent_vod()
    elif mode == "series_seasons":
        list_series_seasons(params.get("series_id") or "")
    elif mode == "series_episodes":
        list_series_episodes(params.get("series_id") or "", params.get("season") or "")
    else:
        main_menu()


if __name__ == "__main__":
    first_run_check()
    router(sys.argv[2][1:] if len(sys.argv) > 2 else "")
