# Kleanix Wizard - Interactive Kodi Maintenance and Backup Tool
# default.py

import xbmcgui
import xbmcplugin
import xbmcaddon
import xbmc
import os
import shutil
import zipfile

ADDON = xbmcaddon.Addon()
ADDON_NAME = ADDON.getAddonInfo('name')
ADDON_ID = ADDON.getAddonInfo('id')
HOME = xbmc.translatePath("special://home/")
BACKUP_DIR = os.path.join(HOME, 'kleanix_backups')
BUILD_DIR = os.path.join(HOME, 'kleanix_builds')

if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)
if not os.path.exists(BUILD_DIR):
    os.makedirs(BUILD_DIR)

class KleanixWindow(xbmcgui.WindowXMLDialog):
    def onInit(self):
        self.getControl(100).setLabel("Kleanix Wizard")
        self.getControl(200).setLabel("Clear Cache")
        self.getControl(201).setLabel("Delete Thumbnails")
        self.getControl(202).setLabel("Delete Packages")
        self.getControl(203).setLabel("Backup Kodi")
        self.getControl(204).setLabel("Restore Build")
        self.getControl(205).setLabel("Force Close Kodi")
        self.getControl(299).setLabel("Status: Idle")

    def onClick(self, controlId):
        if controlId == 200:
            self.clear_cache()
        elif controlId == 201:
            self.delete_thumbnails()
        elif controlId == 202:
            self.delete_packages()
        elif controlId == 203:
            self.backup_kodi()
        elif controlId == 204:
            self.restore_build()
        elif controlId == 205:
            xbmc.executebuiltin('ShutDown()')

    def update_status(self, text):
        self.getControl(299).setLabel(f"Status: {text}")

    def clear_cache(self):
        cache_path = os.path.join(HOME, 'cache')
        if os.path.exists(cache_path):
            for root, dirs, files in os.walk(cache_path):
                for file in files:
                    try:
                        os.remove(os.path.join(root, file))
                    except:
                        pass
        self.update_status("Cache Cleared")

    def delete_thumbnails(self):
        thumb_path = os.path.join(HOME, 'userdata', 'Thumbnails')
        if os.path.exists(thumb_path):
            shutil.rmtree(thumb_path)
        self.update_status("Thumbnails Deleted")

    def delete_packages(self):
        pkg_path = os.path.join(HOME, 'packages')
        if os.path.exists(pkg_path):
            for file in os.listdir(pkg_path):
                try:
                    os.remove(os.path.join(pkg_path, file))
                except:
                    pass
        self.update_status("Packages Deleted")

    def backup_kodi(self):
        zip_name = os.path.join(BACKUP_DIR, 'kodi_backup.zip')
        with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for folder in ['userdata', 'addons']:
                folder_path = os.path.join(HOME, folder)
                for root, _, files in os.walk(folder_path):
                    for file in files:
                        filepath = os.path.join(root, file)
                        arcname = os.path.relpath(filepath, HOME)
                        zipf.write(filepath, arcname)
        self.update_status("Backup Created")

    def restore_build(self):
        files = [f for f in os.listdir(BACKUP_DIR) if f.endswith('.zip')]
        if not files:
            self.update_status("No Backups Found")
            return
        index = xbmcgui.Dialog().select("Choose Backup to Restore", files)
        if index == -1:
            return
        selected = os.path.join(BACKUP_DIR, files[index])
        with zipfile.ZipFile(selected, 'r') as zipf:
            zipf.extractall(HOME)
        self.update_status("Build Restored. Please Restart Kodi.")

# Launch the window
win = KleanixWindow("script-kleanix.xml", ADDON.getAddonInfo('path'), "default", "720p")
win.doModal()
del win
