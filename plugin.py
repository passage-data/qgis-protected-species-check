# -*- coding: utf-8 -*-
"""plugin.py — the menu entry, and nothing else.

⛔ ONE ENTRY POINT. The plugin adds a single action to the Vector menu and the toolbar; a plugin
   that plants a submenu of six things for one job is a plugin people turn off.
"""
import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

TITLE = "Protected Species Check"


class ProtectedSpeciesCheck:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dialog = None

    def initGui(self):                                               # noqa: N802 — QGIS's own name
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        self.action = QAction(icon, TITLE, self.iface.mainWindow())
        self.action.setWhatsThis("Screen a layer's scientific names against the laws and "
                                 "assessment lists that decide, and say which edition each cites.")
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToVectorMenu(TITLE, self.action)

    def unload(self):
        if self.action is not None:
            self.iface.removePluginVectorMenu(TITLE, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None
        self.dialog = None

    def run(self):
        # ⛔ REBUILT EACH TIME, so a layer added since the last run is in the list. A cached
        #   dialog is how a plugin comes to show a project the user has already closed.
        from .dialog import ScreenDialog
        self.dialog = ScreenDialog(self.iface, self.iface.mainWindow())
        self.dialog.show()
