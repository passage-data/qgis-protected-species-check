# -*- coding: utf-8 -*-
"""screen_task.py — reading the layer, calling the door, writing the columns back.

⛔ THE CALL RUNS OFF THE GUI THREAD. A screening takes a few seconds and a frozen QGIS window is
   how a plugin gets uninstalled; `QgsTask` is the mechanism QGIS already has for this.
⛔ NOTHING IS WRITTEN UNTIL THE ANSWER IS WHOLE. The write-back happens in `finished()`, on the
   main thread, inside one edit session — a half-written attribute table is worse than none.
"""
from qgis.core import (NULL, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsField,
                       QgsPointXY, QgsProject, QgsTask)
from qgis.PyQt.QtCore import QVariant

from . import client

WGS84 = "EPSG:4326"


def _text(raw):
    """→ an attribute as a stripped string, or "" when it is NULL. ⛔ THE ONE WAY THIS PLUGIN
    READS A CELL.

    ⛔⛔ `str(raw)` ON A NULL GIVES THE FOUR CHARACTERS `NULL` ON QGIS 3, AND THEY WENT UP AS A
      SPECIES NAME. Measured 2026-09-17 on QGIS 3.44.14 / PyQt 5.15.13: `feature.attribute(i)`
      returns a null `QVariant` under PyQt5 and Python's `None` under PyQt6, so the test this
      module used — `"" if raw is None else str(raw)` — was correct on QGIS 4 and wrong on every
      QGIS 3 in the world. A layer with one empty name field sent the binomial "NULL" to the
      screening door, which is the single thing this plugin exists not to do: a name nobody
      wrote, on a table somebody files with a regulator. The door refused the column, so the
      user's whole screening failed with a message about common names.
    ⛔ `qgis.core.NULL` IS THE TEST THAT WORKS ON BOTH. It is a null QVariant on 3.x and `None`
      on 4.x, and `raw == NULL` is True for a null and False for a real value under both — both
      directions measured, and barred in `qgis_selftest`.
    ⚠ NOT A STRING COMPARISON AGAINST "NULL". That would also drop a cell somebody really typed,
      and it would go on quietly passing on QGIS 4 where the bug does not exist.
    """
    if raw is None or raw == NULL:
        return ""
    return str(raw).strip()


def name_values(layer, field):
    """→ ([(name, lat, lon)], n_features, n_without_place, truncated, n_blank)

    ⛔⛔ `n_blank` IS THE FEATURES THIS FUNCTION THREW AWAY, AND NOBODY USED TO BE TOLD. A feature
      whose name cell is empty cannot be screened — that is correct — but it left no trace at all:
      the panel reported "5 distinct names read from 7 features" for the ACT tree register and
      never that the layer has 298, because `BOTANICAL_` is filled on 7 of them (measured
      2026-09-17). A screening that silently covers 2% of a layer and reads like a verdict is the
      shape of every defect this plugin exists to prevent.

    ⛔ ONE ROW PER DISTINCT NAME, carrying that name's own mean position. Sending every feature
      would send the same name hundreds of times and put the whole layer's coordinates on the
      wire for a question that is about names.
    """
    idx = layer.fields().indexOf(field)
    if idx < 0:
        return [], 0, 0, False, 0
    to_wgs = None
    src = layer.crs()
    # ⛔ SAME FALSE PREMISE AS `dialog.has_geom` WAS: `geometryType()` returns `GeometryType.Null`
    #   for a table, never `None`, so this test never excluded anything. Here it happened to be
    #   harmless — a table's CRS is invalid, and `src.isValid()` carried the branch — but a guard
    #   that is right by accident is one line away from being wrong on purpose.
    if layer.isSpatial() and src.isValid() and src.authid() != WGS84:
        to_wgs = QgsCoordinateTransform(src, QgsCoordinateReferenceSystem(WGS84),
                                        QgsProject.instance())
    acc, n_feat, n_blank = {}, 0, 0
    for f in layer.getFeatures():
        value = _text(f.attribute(idx))
        if not value:
            n_blank += 1                                             # counted, never silent
            continue
        n_feat += 1
        slot = acc.setdefault(value, [0.0, 0.0, 0])
        geom = f.geometry()
        if geom is None or geom.isEmpty():
            continue
        try:
            pt = geom.centroid().asPoint()
            if to_wgs is not None:
                pt = to_wgs.transform(QgsPointXY(pt))
            if -90.0 <= pt.y() <= 90.0 and -180.0 <= pt.x() <= 180.0:
                slot[0] += pt.y()
                slot[1] += pt.x()
                slot[2] += 1
        except Exception:                                            # noqa: BLE001
            pass                                                     # a bad geometry is not a name
    rows, n_no_place = [], 0
    for value, (sy, sx, n) in acc.items():
        if n:
            rows.append((value, sy / n, sx / n))
        else:
            rows.append((value, None, None))
            n_no_place += 1
    rows.sort(key=lambda r: r[0].lower())
    truncated = len(rows) > client.MAX_NAMES
    return rows[:client.MAX_NAMES], n_feat, n_no_place, truncated, n_blank


def write_back(layer, field, answer, checked_on):
    """→ (n_written, why_not). Adds the six columns and fills them, in one edit session."""
    cards = answer.get("register_cards") or []
    by_value = {}
    # ⛔ THE COVERAGE BLOCK RIDES INTO EVERY CELL. Without it `pd_applies` cannot tell
    #   "no law in force here lists this taxon" from "we hold no law for where you are",
    #   and a reader filtering the attribute table meets one blank for both.
    coverage = answer.get("coverage") or {}
    for n in answer.get("names") or ():
        by_value[str(n.get("value") or "").strip().lower()] = client.columns_for(
            n, cards, checked_on, coverage)
    if not by_value:
        return 0, "the answer named no species, so there was nothing to write"

    provider = layer.dataProvider()
    existing = {f.name() for f in layer.fields()}
    missing = [QgsField(c, QVariant.String, len=254) for c, _why in client.COLUMNS
               if c not in existing]
    if missing and not provider.addAttributes(missing):
        return 0, "this layer's provider would not take new columns (%s)" % layer.providerType()
    if missing:
        layer.updateFields()

    idx_name = layer.fields().indexOf(field)
    idx = {c: layer.fields().indexOf(c) for c, _why in client.COLUMNS}
    if any(i < 0 for i in idx.values()):
        return 0, "the columns could not be created on this layer"

    changes, n = {}, 0
    for f in layer.getFeatures():
        # ⛔ THE SAME READER AS `name_values`, OR THE WRITE-BACK MATCHES A DIFFERENT SET OF ROWS
        #   THAN THE SCREEN DID. Two spellings of "read this cell" is how a layer gets columns on
        #   the wrong features.
        cols = by_value.get(_text(f.attribute(idx_name)).lower())
        if not cols:
            continue
        changes[f.id()] = {idx[c]: cols[c] for c, _why in client.COLUMNS}
        n += 1
    if not changes:
        return 0, "no feature's name matched what came back"
    if not provider.changeAttributeValues(changes):
        return 0, "this layer's provider refused the write"
    layer.triggerRepaint()
    return n, None


class ScreenTask(QgsTask):
    """The call, off the GUI thread. `on_done(answer, error)` runs back on the main thread."""

    def __init__(self, rows, province, on_done):
        super().__init__("Checking protected species", QgsTask.CanCancel)
        self._rows = rows
        self._province = province
        self._on_done = on_done
        self.answer = None
        self.error = None

    def run(self):
        try:
            self.answer = client.screen(self._rows, province=self._province)
            return True
        except client.ScreenError as e:
            self.error = str(e)
            return False
        except Exception as e:                                       # noqa: BLE001
            # ⛔ A PLUGIN THAT THROWS INTO THE QGIS LOG AND SAYS NOTHING ON SCREEN has failed
            #   twice. Whatever happened, the dialog gets a sentence.
            self.error = "Unexpected problem while screening: %s" % str(e)[:300]
            return False

    def finished(self, ok):
        self._on_done(self.answer if ok else None, None if ok else self.error)
