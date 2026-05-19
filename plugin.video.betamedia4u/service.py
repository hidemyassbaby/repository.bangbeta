# -*- coding: utf-8 -*-
"""Beta Media4u background playback watcher.

Keeps the plugin callback free so Kodi's Working spinner closes, then reopens
our custom GUI after playback stops using the state saved by default.py.
"""
from __future__ import annotations

import time
import urllib.parse

import xbmc
import xbmcaddon
import xbmcgui

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_NAME = ADDON.getAddonInfo("name") or "Beta Media4u"
PLUGIN_URL = f"plugin://{ADDON_ID}/?" + urllib.parse.urlencode({"mode": "modern_gui"})

ROOT = xbmcgui.Window(10000)
RESTORE_PROP = "betamedia4u_restore_gui"
PENDING_PROP = "betamedia4u_playback_pending"
STARTED_PROP = "betamedia4u_playback_started"
STARTED_AT_PROP = "betamedia4u_playback_started_at"
LOCK_PROP = "betamedia4u_playback_lock"
LOCK_AT_PROP = "betamedia4u_playback_lock_at"


def log(msg, level=xbmc.LOGINFO):
    xbmc.log(f"[{ADDON_ID} service] {msg}", level)


def close_busy_dialogs():
    try:
        xbmc.executebuiltin("Dialog.Close(busydialog,true)")
        xbmc.executebuiltin("Dialog.Close(busydialognocancel,true)")
    except Exception:
        pass


def clear_playback_props(clear_restore=False):
    ROOT.clearProperty(PENDING_PROP)
    ROOT.clearProperty(STARTED_PROP)
    ROOT.clearProperty(STARTED_AT_PROP)
    ROOT.clearProperty(LOCK_PROP)
    ROOT.clearProperty(LOCK_AT_PROP)
    if clear_restore:
        ROOT.clearProperty(RESTORE_PROP)


def reopen_gui():
    try:
        close_busy_dialogs()
        xbmc.sleep(450)
        # RunPlugin starts the custom WindowXML dialog without asking Kodi's
        # Videos window to read a directory, which avoids GetDirectory failed
        # errors and stuck Working spinners.
        xbmc.executebuiltin(f'RunPlugin("{PLUGIN_URL}")')
    except Exception as exc:
        log(f"Could not reopen GUI: {exc}", xbmc.LOGWARNING)


def main():
    monitor = xbmc.Monitor()
    player = xbmc.Player()
    seen_playing = False
    last_state = False
    while not monitor.abortRequested():
        pending = ROOT.getProperty(PENDING_PROP) == "true"
        is_playing = False
        try:
            is_playing = bool(player.isPlaying() or player.isPlayingVideo())
        except Exception:
            is_playing = False

        # Clear stale locks if Kodi was interrupted during startup.
        try:
            lock_at = int(ROOT.getProperty(LOCK_AT_PROP) or "0")
        except Exception:
            lock_at = 0
        if lock_at and int(time.time()) - lock_at > 45 and not is_playing:
            clear_playback_props(clear_restore=False)

        if pending:
            close_busy_dialogs()
            if is_playing:
                seen_playing = True
                ROOT.setProperty(STARTED_PROP, "true")
            else:
                started_prop = ROOT.getProperty(STARTED_PROP) == "true"
                try:
                    started_at = int(ROOT.getProperty(STARTED_AT_PROP) or "0")
                except Exception:
                    started_at = 0
                age = int(time.time()) - started_at if started_at else 0

                # Playback has ended after it really started, reopen the saved GUI.
                if seen_playing or started_prop:
                    clear_playback_props(clear_restore=False)
                    seen_playing = False
                    if ROOT.getProperty(RESTORE_PROP) == "true":
                        reopen_gui()

                # Stream failed to start, do not leave Kodi in a stuck Working state.
                elif age > 20:
                    clear_playback_props(clear_restore=False)
                    if ROOT.getProperty(RESTORE_PROP) == "true":
                        reopen_gui()
        elif last_state and not is_playing:
            seen_playing = False

        last_state = is_playing
        monitor.waitForAbort(0.5)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log(f"Service crashed safely: {exc}", xbmc.LOGERROR)
