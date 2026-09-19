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


class NameRows(list):
    """[(name, [(lat, lon), …])], one per distinct name, and how the positions were gridded:
    `grid` in degrees, `n_fine` the distinct ~1 km cells the layer covers, `n_cells` those sent."""
    grid, n_fine, n_cells = 0.0, 0, 0


def name_values(layer, field):
    """→ (NameRows, n_features, n_without_place, n_distinct_if_truncated, n_blank)

    ⛔⛔ `n_blank` IS THE FEATURES THIS FUNCTION THREW AWAY, AND NOBODY USED TO BE TOLD. A feature
      whose name cell is empty cannot be screened — that is correct — but it left no trace at all:
      the panel reported "5 distinct names read from 7 features" for the ACT tree register and
      never that the layer has 298, because `BOTANICAL_` is filled on 7 of them (measured
      2026-09-17). A screening that silently covers 2% of a layer and reads like a verdict is the
      shape of every defect this plugin exists to prevent.

    ⛔ ONE ROW PER DISTINCT NAME, carrying the distinct cells its features fall in (`client.GRID`)
      — never their average, which is a point no record sits on. Sending every feature would
      put the whole layer's coordinates on the wire for a question that is about names and
      places; a cell per place is what the service reads anyway.
    """
    idx = layer.fields().indexOf(field)
    if idx < 0:
        return NameRows(), 0, 0, False, 0
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
        cells = acc.setdefault(value, set())
        geom = f.geometry()
        if geom is None or geom.isEmpty():
            continue
        try:
            pt = geom.centroid().asPoint()
            if to_wgs is not None:
                pt = to_wgs.transform(QgsPointXY(pt))
            if -90.0 <= pt.y() <= 90.0 and -180.0 <= pt.x() <= 180.0:
                cells.add((round(pt.y() / client.GRID), round(pt.x() / client.GRID)))
        except Exception:                                            # noqa: BLE001
            pass                                                     # a bad geometry is not a name
    names = sorted(acc, key=str.lower)
    # ⛔⛔ A FLAG THAT ATE THE NUMBER. This was `len(rows) > MAX_NAMES`, a bool — so the panel
    #   could say the cap was hit and NOT how far past it, and a person could not tell whether one
    #   name was dropped or fourteen hundred. §4: a limit that eats information has to change what
    #   the caller sees, and "some were dropped" is the shape of exactly that. It is the TOTAL
    #   distinct count when the cap bit and 0 otherwise, so `if truncated:` reads the same.
    truncated = len(names) if len(names) > client.MAX_NAMES else 0
    names = names[:client.MAX_NAMES]
    # ⛔ PAST THE SERVICE'S CELL CAP, CELLS ARE MERGED — ONE SHARED REPRESENTATIVE PER MERGED CELL,
    #   so the file stays inside what the service places, and every name in a merged cell is asked
    #   about the same real ~1 km cell rather than about a coarse cell's centre, which can be sea.
    fine = sorted({c for v in names for c in acc[v]})
    for k in client.COARSEN:
        rep = {}
        for c in fine:
            rep.setdefault((c[0] // k, c[1] // k), c)
        if len(rep) <= client.MAX_CELLS:
            break
    rows, n_no_place = NameRows(), 0
    rows.grid, rows.n_fine, rows.n_cells = k * client.GRID, len(fine), len(rep)
    for v in names:
        pts = sorted({rep[(c[0] // k, c[1] // k)] for c in acc[v]})
        if not pts:
            n_no_place += 1
        rows.append((v, [(a * client.GRID, b * client.GRID) for a, b in pts]))
    return rows, n_feat, n_no_place, truncated, n_blank


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
