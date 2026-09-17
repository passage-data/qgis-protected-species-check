# -*- coding: utf-8 -*-
"""Protected Species Check — a QGIS plugin by Passage Data.

Which species in your layer are legally protected, under which law, and which edition.
"""


def classFactory(iface):                                             # noqa: N802 — QGIS's own name
    from .plugin import ProtectedSpeciesCheck
    return ProtectedSpeciesCheck(iface)
