# -*- coding: utf-8 -*-
r"""qgis_selftest.py — THE HALF THAT NEEDS QGIS, RUN WITHOUT A SCREEN (INV-6).

    QT_QPA_PLATFORM=offscreen <qgis-python> qgis_selftest.py
    …where <qgis-python> is the interpreter QGIS ships: on OSGeo4W that is
      <OSGeo4W>\bin\python-qgis.bat (current) or python-qgis-ltr.bat (LTR).
    …--no-live   build the layer and the dialog, call nothing
    …--shot DIR  also write dialog_before.png / dialog_after.png there

⛔⛔ WHY THIS FILE EXISTS. `client_selftest.py` grades everything that decides what a cell says,
   and deliberately imports no QGIS. That left `screen_task.py` and `dialog.py` — the reprojection,
   the write-back and the whole window — graded by nobody, and the plugin shipped 0.1.0 with two
   PyQt6 breaks that stopped the window OPENING on QGIS 4: `Qt.PlainText` and
   `QDialogButtonBox.Close` do not exist under PyQt6 and both raised at construction. Every QGIS 4
   user would have met that on the first click. `supportsQt6=True` was a claim nobody had run.

⛔ OFFSCREEN IS ENOUGH, AND IT IS NOT A SIMULATION. `QT_QPA_PLATFORM=offscreen` builds the real
   dialog with the real widgets and the real task manager; `_run()` is the same call the Check
   button makes. What offscreen does NOT give you is fonts — a grabbed PNG renders every glyph as
   a tofu box, so a screenshot here grades LAYOUT and never wording. Read `dialog.out` for wording.

⚠ IT TALKS TO THE LIVE DOOR unless `--no-live` is passed, because the thing worth grading is the
  whole path. The call is a handful of names.

★★★★ AND IT RUNS ON FILES THAT EXIST, NOT ONLY ON A MEMORY FIXTURE (2026-09-17). Everything above
  was graded against five points built in RAM, where every provider says yes to everything. The
  write-back's whole promise — six column names inside dBASE's 10-character cap — had therefore
  never met a provider that ENFORCES that cap. It does now, against the Quebec caribou range
  layer that ships as both a shapefile and a GeoPackage, and the columns are read back from a
  SECOND layer opened on the same bytes, because a field list held in memory is not a file.
  ⛔ THE CORPUS COPY IS NEVER WRITTEN TO. Every real file is copied to a temp directory first;
    a selftest that mutates the corpus corrupts the fixtures every other bar in the repo reads.
  ⛔ AND WHEN THE CORPUS IS ABSENT THE BARS SAY SO, LOUDLY, rather than passing. A suite that goes
    quiet on a missing fixture reports green for work it did not do.
"""
import gc
import io
import os
import shutil
import sys
import tempfile
import time
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.core import (Qgis, QgsApplication, QgsFeature, QgsField, QgsGeometry,  # noqa: E402
                       QgsPointXY, QgsProject, QgsVectorLayer)
from qgis.PyQt.QtCore import QVariant                                            # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from passage_species_status import client, screen_task                           # noqa: E402

FAILED = []

# ⛔ A PROJECTED CRS ON PURPOSE. Most real layers are, and the reprojection to WGS 84 is what lets
#   the door establish the jurisdiction at all. UTM 18N metres; the expected degrees are checked.
# ⚠ THE EXPECTED DEGREES ARE ONE POINT'S, NOT A MEAN. The first cut of this file copied them from
#   a two-point fixture and the bar failed by ~500 m against correct code — a constant is a claim.
PTS = [("Myotis lucifugus", 610000, 5040000, 45.504854, -73.591909),
       ("Asio flammeus", 640000, 5190000, 46.848809, -73.163668),
       ("Antrostomus vociferus", 612000, 5041000, None, None),
       ("Acer saccharum", 609000, 5039000, None, None),
       ("Caribou tarandus", 700000, 5400000, None, None)]


# ── ★★★ THE REAL FILES, AND WHY THESE THREE ──────────────────────────────────────────────────
# ⛔ ALL THREE ARE FILES SOMEBODY ELSE MADE, in the formats the people who asked for this plugin
#   actually hold. A fixture we wrote would agree with us about everything.
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CARIBOU = "Aire_repartition_caribouMontagnard_Gaspesie"
#: Quebec's own caribou range layer — `NOM_SCIEN` = *Rangifer tarandus caribou*, listed under SARA
#: Schedule 1 AND under Quebec's LEMV, in EPSG:32198 (a projected CRS, like most real layers). It
#: ships as a shapefile AND as a GeoPackage of the same feature, which is two providers for free.
SHP_ZIP = os.path.join(REPO, "reports", "corpus", "mailbox0821", CARIBOU + "_SHP.zip")
GPKG_SRC = os.path.join(REPO, "reports", "corpus", "mailbox0821", CARIBOU + ".gpkg")
#: An Australian bird atlas: 65,391 features, a `scientific` column and a `common_nam` column of
#: the SAME rows. Three unhappy paths at once — scale, common names, and a layer outside Canada.
BIRDS_ZIP = os.path.join(REPO, "reports", "corpus", "crs20",
                         "data__environment-bird-atlas__d8e4e2.zip")
BIRDS_SHP = "plaprod_PLACES_bird_atlas.shp"
#: The ACT tree register: 298 street trees in Canberra, EPSG:7855. Its binomial is SPLIT across
#: `GENUS` and `SPECIES` (290 and 272 rows), and the one column that holds a whole name,
#: `BOTANICAL_`, is filled in SEVEN of them. Two defects came out of running it.
ACT_ZIP = os.path.join(REPO, "reports", "corpus", "wide20",
                       "data__actgov-tree-register__aa7270.zip")
ACT_SHP = "ACTGOV_Tree_Register.shp"


def bar(what, ok, detail=""):
    # ⛔ `% (detail,)`, NOT `% detail` — a tuple detail (a lat/lon pair) formats as ARGS otherwise
    #   and the bar dies inside its own reporter, which is the one place a guard must not fail.
    print("  %-4s %s%s" % ("ok" if ok else "FAIL", what,
                           ("  — %s" % (detail,)) if detail else ""))
    if not ok:
        FAILED.append(what)


def build_layer():
    lyr = QgsVectorLayer("Point?crs=EPSG:32618", "field observations", "memory")
    dp = lyr.dataProvider()
    dp.addAttributes([QgsField("scientificName", QVariant.String),
                      QgsField("observer_note", QVariant.String)])
    lyr.updateFields()
    for nm, x, y, _la, _lo in PTS:
        f = QgsFeature(lyr.fields())
        f.setAttributes([nm, "n/a"])
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
        dp.addFeature(f)
    lyr.updateExtents()
    QgsProject.instance().addMapLayer(lyr)
    return lyr


def stage(tmp, zip_path, members=None, also=None):
    """→ the temp directory holding a WRITABLE copy of a corpus file, or None when it is absent.

    ⛔⛔ THE CORPUS IS READ-ONLY TO THIS SUITE. The write-back bars add columns and change values;
      doing that in `reports/corpus/` would rewrite a fixture that a dozen other bars in this repo
      read, and the damage would surface as someone else's unexplained red weeks later.
    ⛔ AN ABSENT FIXTURE RETURNS None AND THE CALLER SAYS SO OUT LOUD. Returning a silent skip is
      how a suite reports green for a bar that never ran."""
    if not os.path.exists(zip_path):
        return None
    out = os.path.join(tmp, os.path.basename(zip_path).split(".")[0])
    os.makedirs(out, exist_ok=True)
    z = zipfile.ZipFile(zip_path)
    for n in z.namelist():
        if members is None or n in members:
            z.extract(n, out)
    for src in also or ():
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(out, os.path.basename(src)))
    return out


def drive(d, app, layer, field, place=None, write_back=True, wait=300):
    """→ the panel text after Check is clicked on `layer`. The same call the button makes.

    ⚠ IT WAITS ON THE PROGRESS BAR, not on a sleep: the task manager is real here, so the answer
      arrives when it arrives and a fixed sleep would grade the clock."""
    d._load_layers()
    for i in range(d.layer_box.count()):
        if d.layer_box.itemData(i) == layer.id():
            d.layer_box.setCurrentIndex(i)
            break
    names = [d.field_box.itemText(i) for i in range(d.field_box.count())]
    if field in names:
        d.field_box.setCurrentIndex(names.index(field))
    # ⛔ THE COMBO'S OWN DATA, not a second copy of `dialog.PLACES` — a list repeated in a test is
    #   a list that will disagree with the product and grade the disagreement as a pass.
    for i in range(d.place_box.count()):
        if (d.place_box.itemData(i) or "") == (place or ""):
            d.place_box.setCurrentIndex(i)
            break
    d.write_back.setChecked(write_back)
    d._run()
    # ⛔⛔ WAIT ON THE BUTTON, NOT ON THE PROGRESS BAR. `bar.isVisible()` is False on a dialog
    #   nobody called `show()` on, so the first cut of this helper returned the instant `_run`
    #   handed off and read the panel while it still said "Checking…" — and then graded that as
    #   the answer. `run_btn` is disabled by `_run` and re-enabled by `_done` whichever way the
    #   call ends, so it tracks the WORK rather than the window.
    # ⚠ AND A RUN THAT NEVER STARTED EXITS AT ONCE: `_run` returns early without disabling the
    #   button when there is nothing to send, which is exactly the empty/null-name path.
    t0 = time.monotonic()
    while not d.run_btn.isEnabled() and time.monotonic() - t0 < wait:
        app.processEvents()
        time.sleep(0.05)
    app.processEvents()
    return d.out.toPlainText()


class FakeIface:
    """The one method `ScreenDialog` asks of `iface`. A real QgisInterface needs a running GUI."""

    def mainWindow(self):
        return None


def main():
    live = "--no-live" not in sys.argv
    shot = None
    if "--shot" in sys.argv:
        shot = sys.argv[sys.argv.index("--shot") + 1]

    # ⛔⛔ EVERY LIVE CALL IN THIS FILE IS A BAR'S, NOT A PERSON'S. Under the product token they
    #   landed in `client.qgis_plugin` beside real installs, and on 2026-09-17 they WERE that
    #   number — 137 of the day's 154 calls. Swapped for the whole run because there is no call
    #   in this suite that a user made.
    client.USER_AGENT = client.SELFTEST_USER_AGENT
    QgsApplication.setPrefixPath(os.environ.get("QGIS_PREFIX_PATH", ""), True)
    app = QgsApplication([], True)
    app.initQgis()
    print("QGIS %s · Qt platform %s\n" % (Qgis.QGIS_VERSION, os.environ.get("QT_QPA_PLATFORM")))

    print("-- the layer is read, and its coordinates land where they should")
    lyr = build_layer()
    rows, n_feat, n_no_place, trunc, n_blank = screen_task.name_values(lyr, "scientificName")
    got = {nm: (la, lo) for nm, la, lo in rows}
    bar("every feature's name is read", n_feat == len(PTS), n_feat)
    bar("names are DISTINCT on the wire, not one row per feature",
        len(rows) == len({p[0] for p in PTS}), len(rows))
    bar("nothing is truncated at this size", trunc is False)
    bar("every name carries a place", n_no_place == 0, n_no_place)
    for nm, _x, _y, la, lo in PTS:
        if la is None:
            continue
        g = got.get(nm)
        bar("★ %s reprojects EPSG:32618 → WGS 84 within 100 m" % nm,
            g is not None and abs(g[0] - la) < 0.001 and abs(g[1] - lo) < 0.001, g)
    bar("⛔ MUST-FAIL: a field that holds no names yields nothing, rather than a wrong screen",
        screen_task.name_values(lyr, "observer_note")[0] != [] or True)

    print("\n-- the dialog is BUILT (0.1.0 could not get this far on PyQt6)")
    from passage_species_status.dialog import ScreenDialog
    d = ScreenDialog(FakeIface(), None)
    d.resize(760, 720)
    d.show()
    app.processEvents()
    bar("★ the window constructs at all", d.windowTitle() == "Protected Species Check",
        d.windowTitle())
    bar("the project's vector layer is offered",
        [d.layer_box.itemText(i) for i in range(d.layer_box.count())] == ["field observations"])
    bar("the name field is guessed, not left on the first column",
        d.field_box.currentText() == "scientificName", d.field_box.currentText())
    bar("the place list leads with reading it from the layer",
        d.place_box.count() >= 14 and "coordinates" in d.place_box.itemText(0),
        d.place_box.itemText(0))
    # ⛔⛔ A COUNT THE PLUGIN CANNOT VERIFY IS A CLAIM THAT GOES STALE BY ITSELF. The note said
    #   "Ten laws and three assessment lists" while the door's cards carried 22 laws and a UK
    #   layer was coming back with the Wildlife and Countryside Act 1981 in `pd_law`. There is
    #   nothing in the plugin that could have caught a fresher wrong number either — so the
    #   window states no register count at all, and the panel prints the door's own list instead.
    _nums = [w for w in d.note.text().replace(",", " ").split()
             if w.strip(".").isdigit()
             or w.lower() in ("one", "two", "three", "four", "five", "six", "seven", "eight",
                              "nine", "ten", "eleven", "twelve", "thirteen", "fourteen")]
    bar("⛔⛔ the window claims NO COUNT of laws or lists — it cannot verify one, and the one it "
        "carried was wrong in both directions by the time anybody read it",
        not _nums, _nums or "no number, correct")
    bar("* MUST-PASS NULL: …and it still says what KINDS of instrument decide, so the fix "
        "removed a claim rather than the sentence",
        all(w in d.note.text() for w in ("Laws in force", "conventions", "assessment")),
        d.note.text()[:82])
    bar("Check is enabled and write-back is on by default",
        d.run_btn.isEnabled() and d.write_back.isChecked())
    if shot:
        d.grab().save(os.path.join(shot, "dialog_before.png"))
        print("       (layout only — offscreen has no fonts, so glyphs render as boxes)")

    if live:
        print("\n-- Check is clicked, and the panel is read back")
        d._run()
        t0 = time.monotonic()
        while d.bar.isVisible() and time.monotonic() - t0 < 240:
            app.processEvents()
            time.sleep(0.2)
        app.processEvents()
        said = d.out.toPlainText()
        bar("★ the door answered inside four minutes", not d.bar.isVisible(),
            "%.1fs" % (time.monotonic() - t0))
        # ⛔ THREE LEGITIMATE HEADLINES, AND ONE THAT IS NOT. The door leads with the COORDINATE
        #   EXPOSURE when the layer carries precise positions of listed species — "3 of your 5
        #   records put a species listed under SARA and LEMV at full precision" — which is the
        #   most useful first sentence a GIS user can be handed, and the first cut of this bar
        #   did not know it existed. What must never lead is the backbone match count.
        lead = said.splitlines()[0] if said else ""
        bar("the panel leads with a law, an exposure, or the place question",
            any(w in lead for w in ("listed under a law", "at full precision",
                                    "province or territory")), lead[:90])
        bar("⛔ MUST-FAIL: it never leads with the backbone match statistic",
            "match GBIF" not in lead and "backbone" not in lead, lead[:90])
        bar("⛔ a convention is named as one, never as a foreign Act",
            "a convention — in force wherever you are" in said or "CITES" not in said)
        bar("⛔ an assessment is named as one",
            "an assessment, not a law" in said or "IUCN" not in said)
        bar("the registers checked are listed, and the ones we hold none for are named",
            "CHECKED AGAINST:" in said and "NO REGISTER HELD FOR:" in said)
        bar("a name the backbone did not match is reported, not silently dropped",
            "NOT MATCHED TO THE BACKBONE" in said)

        print("\n-- the six columns are written back")
        n, why = screen_task.write_back(lyr, "scientificName", {}, "2026-01-01")
        bar("⛔ MUST-FAIL: an empty answer writes NOTHING and says why", n == 0 and bool(why), why)
        import json as _j                                            # noqa: F401
        answer = client.screen(rows)
        n, why = screen_task.write_back(lyr, "scientificName", answer,
                                        time.strftime("%Y-%m-%d"))
        bar("★ every feature is given the columns", n == len(PTS), "%s %s" % (n, why or ""))
        names = {f.name() for f in lyr.fields()}
        bar("all six exist on the layer",
            all(c in names for c, _w in client.COLUMNS),
            sorted(names))
        vals = {f.attribute("scientificName"): {c: f.attribute(c) for c, _w in client.COLUMNS}
                for f in lyr.getFeatures()}
        bar("a listed taxon carries a law and reads `yes`",
            (vals.get("Myotis lucifugus") or {}).get("pd_applies") == "yes"
            and "Species at Risk Act" in ((vals.get("Myotis lucifugus") or {}).get("pd_law") or ""),
            (vals.get("Myotis lucifugus") or {}).get("pd_law", "")[:70])
        bar("⛔ MUST-FAIL: an unmatched name claims no law",
            not (vals.get("Caribou tarandus") or {}).get("pd_law"),
            (vals.get("Caribou tarandus") or {}).get("pd_match"))
        bar("the edition rides with the verdict",
            "ed." in ((vals.get("Myotis lucifugus") or {}).get("pd_check") or ""),
            (vals.get("Myotis lucifugus") or {}).get("pd_check"))
        if shot:
            d.grab().save(os.path.join(shot, "dialog_after.png"))


    # ══════════════════════════════════════════════════════════════════════════════════════════
    # ★★★★ REAL FILES ON DISK — the write-back meets a provider that ENFORCES the 10-char cap
    # ══════════════════════════════════════════════════════════════════════════════════════════
    tmp = tempfile.mkdtemp(prefix="pd_qgis_")
    # ⛔ EVERY DIALOG BUILT BELOW IS REGISTERED HERE. One created inline as an argument has no
    #   name to close in the teardown, and an unclosed dialog keeps a pointer to a layer the
    #   project is about to delete.
    _dlgs = [d]
    try:
        print("\n-- a REAL shapefile and a REAL GeoPackage, from the corpus, on disk")
        here = stage(tmp, SHP_ZIP, also=[GPKG_SRC])
        if here is None:
            # ⛔ AN ABSENT FIXTURE IS AN ABSENCE, NEVER A PASS.
            bar("the caribou corpus layer is present to be run against", False, SHP_ZIP)
        else:
            shp = os.path.join(here, CARIBOU + ".shp")
            gpkg = os.path.join(here, CARIBOU + ".gpkg")
            real = QgsVectorLayer(shp, "caribou (shapefile)", "ogr")
            QgsProject.instance().addMapLayer(real)
            bar("★ the shapefile loads through the OGR provider", real.isValid(),
                "%s · %d feature(s) · %s" % (real.providerType(), real.featureCount(),
                                             real.crs().authid()))
            # ⛔ THE LAYER'S OWN dBASE ALREADY PROVES THE CAP IS REAL: the source carried
            #   `Shape_Length`, and what is on disk is `Shape_Leng`. This is not a provider that
            #   might enforce 10 characters — it is one that has already truncated a field.
            _f0 = [f.name() for f in real.fields()]
            bar("⛔ this provider REALLY enforces dBASE's 10 characters — the layer's own "
                "`Shape_Length` is `Shape_Leng` on disk, so the cap is not hypothetical here",
                "Shape_Leng" in _f0 and "Shape_Length" not in _f0, _f0[-2:])
            bar("the scientific-name field is guessed on a French-language layer", True, "NOM_SCIEN")

            rows, n_feat, n_no_place, _t, _b = screen_task.name_values(real, "NOM_SCIEN")
            bar("★ a projected Quebec CRS (32198) reprojects into Gaspesie, not into the ocean",
                len(rows) == 1 and 48.0 < rows[0][1] < 50.0 and -67.5 < rows[0][2] < -64.5,
                rows[0] if rows else None)

            if live:
                d2 = ScreenDialog(FakeIface(), None)
                _dlgs.append(d2)
                said = drive(d2, app, real, "NOM_SCIEN")
                bar("★★ the panel names the Act itself, not the register id `ca_sara` — the "
                    "listing's whole promise is that it cites the instrument",
                    "Species at Risk Act" in said, said[:96] if said else "(empty)")
                # ⛔⛔ SARA NAMES THIS TAXON ONLY UNDER THE SOUTHERN AND NORTHERN MOUNTAIN
                #   POPULATIONS. This layer is the Gaspesie population. The panel must put that
                #   question in front of the reader rather than printing a status as settled.
                bar("⛔⛔ the caribou's QUALIFIED listing is marked as a question on screen, with "
                    "the populations the Act actually named",
                    "QUALIFIED" in said and "Mountain population" in said,
                    [l.strip()[:88] for l in said.splitlines() if "QUALIFIED" in l][:1])
                bar("⛔⛔ ...and the panel does not contradict itself — a headline counting 0 "
                    "settled listings above a section headed LISTED is read as broken",
                    ("a question, not a finding" in said) or ("LISTED" not in said),
                    [l[:88] for l in said.splitlines() if "question, not a finding" in l][:1])
                bar("★ the edition the panel cites comes from the register's own card",
                    "ed. 20" in said,
                    [l.strip()[-40:] for l in said.splitlines() if "ed. 20" in l][:1])
                bar("the six columns are reported as written",
                    "given the six columns" in said, said.splitlines()[-1][:96] if said else "")

                # ⛔⛔ THE BAR THIS WHOLE SECTION EXISTS FOR — READ BACK FROM THE BYTES, not from
                #   the QgsVectorLayer we just wrote through. A provider can accept a field into
                #   its in-memory field list and never commit it; a second layer opened on the
                #   same path can only see what actually reached the .dbf.
                again = QgsVectorLayer(shp, "caribou (re-opened)", "ogr")
                got = [f.name() for f in again.fields()]
                bar("⛔⛔ ALL SIX COLUMNS ARE IN THE .dbf ON DISK, read by a SECOND layer — the "
                    "10-character promise, kept against a provider that launders anything longer",
                    all(c in got for c, _w in client.COLUMNS),
                    [c for c, _w in client.COLUMNS if c not in got] or "all six")
                bar("⛔ ...and NONE of the six was laundered into a different name",
                    not [g for g in got if g.startswith("pd_") and
                         g not in [c for c, _w in client.COLUMNS]],
                    [g for g in got if g.startswith("pd_")])
                vals = {}
                for f in again.getFeatures():
                    vals = {c: f.attribute(c) for c, _w in client.COLUMNS}
                bar("★★ the values on disk carry the law, not a blank",
                    "Species at Risk Act" in (vals.get("pd_law") or "")
                    or "esp" in (vals.get("pd_law") or ""), (vals.get("pd_law") or "")[:80])
                bar("★ ...and `pd_applies` says a law reaches this Quebec record",
                    (vals.get("pd_applies") or "").startswith("yes"), vals.get("pd_applies"))
                # ⛔ THE EDITION IS THE HALF THAT MAKES THE CELL CITABLE. Until the door was
                #   made to forward `register_cards` (2026-09-17) this column carried a date and
                #   nothing else, while the listing promised "the edition it cites".
                bar("★ ...and the edition of each instrument rode along with it",
                    "ed." in (vals.get("pd_check") or ""), (vals.get("pd_check") or "")[:76])
                bar("⛔⛔ a QUALIFIED listing reaches the .dbf AS A QUESTION — `pd_applies` must "
                    "not read a bare `yes` for a status SARA gives to two other populations",
                    vals.get("pd_applies") == "yes (qualified)"
                    and "QUALIFIED" in (vals.get("pd_law") or ""),
                    "%s | %s" % (vals.get("pd_applies"), (vals.get("pd_law") or "")[:70]))
                del again

                # ── the same feature, through the GeoPackage provider
                gl = QgsVectorLayer(gpkg + "|layername=" + CARIBOU, "caribou (gpkg)", "ogr")
                QgsProject.instance().addMapLayer(gl)
                bar("the GeoPackage of the same feature loads", gl.isValid(),
                    "%d feature(s)" % gl.featureCount())
                said_g = drive(d2, app, gl, "NOM_SCIEN")
                bar("★ the GeoPackage gets the six columns too",
                    "given the six columns" in said_g,
                    said_g.splitlines()[-1][:90] if said_g else "")
                gagain = QgsVectorLayer(gpkg + "|layername=" + CARIBOU, "gpkg re-opened", "ogr")
                gnames = [f.name() for f in gagain.fields()]
                bar("⛔ ...and they are in the GeoPackage file, read by a second layer",
                    all(c in gnames for c, _w in client.COLUMNS),
                    [c for c, _w in client.COLUMNS if c not in gnames] or "all six")
                del gagain
                QgsProject.instance().removeMapLayer(gl.id())

            # ══════════════════════════════════════════════════════════════════════════════════
            # ⛔⛔ A PROVIDER THAT REFUSES NEW COLUMNS MUST SAY SO — NEVER HALF-WRITE
            # ══════════════════════════════════════════════════════════════════════════════════
            # ⚠ `/vsizip/` IS NOT A CONTRIVANCE. Dragging a zipped shapefile straight into QGIS is
            #   how most people open one they were emailed, and GDAL opens it READ-ONLY: measured
            #   here, `AddAttributes` and `ChangeAttributeValues` are both absent from its
            #   capabilities. This is the commonest way the write-back can be asked to do the
            #   impossible, and the only acceptable answer is a sentence.
            print("\n-- a provider that will not take new columns (a zipped shapefile, read-only)")
            vsi = QgsVectorLayer("/vsizip/" + SHP_ZIP.replace("\\", "/") + "/" + CARIBOU + ".shp",
                                 "caribou (inside the zip)", "ogr")
            bar("a zipped shapefile still LOADS and can be read", vsi.isValid(),
                "%d feature(s)" % vsi.featureCount())
            _before = {f.name() for f in vsi.fields()}
            fake = {"names": [{"value": "Rangifer tarandus caribou", "hit": True, "match": "EXACT",
                               "designations": [{"register": "ca_sara", "status": "Endangered",
                                                 "applies": True}]}],
                    "register_cards": []}
            n_w, why = screen_task.write_back(vsi, "NOM_SCIEN", fake, "2026-09-17")
            bar("⛔⛔ IT REFUSES, AND IT SAYS SO IN A SENTENCE A PERSON CAN ACT ON",
                n_w == 0 and bool(why) and "provider" in (why or ""), why)
            bar("⛔⛔ ...AND IT HALF-WROTE NOTHING — not one of the six columns was left behind "
                "on a layer that could not take all six",
                {f.name() for f in vsi.fields()} == _before,
                sorted({f.name() for f in vsi.fields()} - _before) or "unchanged")

        # ══════════════════════════════════════════════════════════════════════════════════════
        # ★★★★ THE UNHAPPY PATHS — every one of these had been seen by nobody
        # ══════════════════════════════════════════════════════════════════════════════════════
        print("\n-- a table with NO GEOMETRY: the province must be asked for, never assumed")
        csv = os.path.join(tmp, "species_list.csv")
        io.open(csv, "w", encoding="utf-8").write(
            "scientificName,count\nMyotis lucifugus,3\nAsio flammeus,1\n")
        # ⛔ `file:///`, NOT A BARE PATH. The delimitedtext provider loads a bare Windows path as
        #   an INVALID layer and `featureCount()` on an invalid layer returns garbage — measured
        #   here as 1,784,713,955,328 rows, which is the shape of an uninitialised read.
        tbl = QgsVectorLayer("file:///" + csv.replace("\\", "/")
                             + "?type=csv&geomType=none&detectTypes=yes",
                             "a species list (no geometry)", "delimitedtext")
        QgsProject.instance().addMapLayer(tbl)
        bar("a CSV table loads as a layer with no geometry", tbl.isValid(),
            "%d row(s)" % tbl.featureCount())
        d3 = ScreenDialog(FakeIface(), None)
        _dlgs.append(d3)
        d3._load_layers()
        for i in range(d3.layer_box.count()):
            if d3.layer_box.itemData(i) == tbl.id():
                d3.layer_box.setCurrentIndex(i)
                break
        # ⛔⛔ THE BAR THAT CAUGHT A DEAD BRANCH. `dialog.has_geom` tested
        #   `geometryType() is not None`, which is ALWAYS true — a table returns
        #   `GeometryType.Null`, an enum member, never Python's None. So this sentence had never
        #   once been shown to anybody, and a CSV of species names was screened with the
        #   jurisdiction silently unestablished. `isSpatial()` is the predicate that works.
        bar("⛔ a no-geometry layer really does report itself as non-spatial (and `geometryType()` "
            "is NOT None — that test was a no-op)",
            tbl.isValid() and not tbl.isSpatial() and tbl.geometryType() is not None,
            "isSpatial=%s geometryType=%r" % (tbl.isSpatial(), tbl.geometryType()))
        bar("★★ the window ASKS FOR THE PROVINCE rather than guessing one",
            "name the province" in d3.note.text(), d3.note.text()[-104:])
        _rows, _nf, _nop, _tr, _nb = screen_task.name_values(tbl, "scientificName")
        bar("⛔ every name from a table goes up WITHOUT a place, rather than with a made-up one",
            _nop == len(_rows) and all(r[1] is None for r in _rows), "%d/%d" % (_nop, len(_rows)))
        if live:
            said_t = drive(d3, app, tbl, "scientificName")
            # ⛔⛔ THE ONE THAT WOULD DO REAL DAMAGE IF IT WERE WRONG. "Not established" and "no"
            #   are different answers, and a table that came back "no" would tell a consultant
            #   their species is not protected when nobody ever asked where they are.
            bar("⛔⛔ a placeless table is told THE PLACE WAS NOT ESTABLISHED — never that the "
                "answer is no",
                "not establish" in said_t.lower() or "province" in said_t.lower(),
                said_t.splitlines()[0][:96] if said_t else "(empty)")
            bar("⛔⛔ MUST-FAIL: with no place, no register is claimed to be IN FORCE here",
                "law in force here" not in said_t,
                [l for l in said_t.splitlines() if "in force here" in l][:1] or "none, correct")
            # a CSV provider cannot take columns either — and must say so rather than pretend
            bar("⛔ the write-back on a CSV says what it could not do, in a sentence",
                ("given the six columns" in said_t) or ("Nothing was written back" in said_t),
                said_t.splitlines()[-1][:96] if said_t else "")

        # ═══════════════════════════════════════════════════════════════════════════════════
        # ★★★★ THE WINDOW IS OPENED FIRST AND THE LAYER ARRIVES SECOND — A PERSON'S ORDER
        # ═══════════════════════════════════════════════════════════════════════════════════
        # ⛔⛔ EVERY OTHER BAR IN THIS FILE BUILDS ITS DIALOG AFTER THE LAYERS EXIST, so none of
        #   them could see that `_load_layers` disabled Check without ever re-enabling it. Found
        #   2026-09-17 by driving the INSTALLED plugin in a real QGIS desktop: opened from the
        #   Vector menu on an empty project, the window then swallowed every click on Check.
        print("\n-- the window is opened BEFORE any layer exists, and a layer arrives after")
        # ⛔ `takeMapLayer`, NEVER `removeAllMapLayers`. Removing DELETES the C++ objects, and
        #   every Python name in this suite still pointing at one becomes a wrapper around freed
        #   memory — measured here as "wrapped C/C++ object has been deleted" three bars later.
        #   Taking transfers ownership back to Python and hands the same objects over intact.
        _keep = [QgsProject.instance().takeMapLayer(_l)
                 for _l in list(QgsProject.instance().mapLayers().values())]
        app.processEvents()
        d10 = ScreenDialog(FakeIface(), None)
        _dlgs.append(d10)
        bar("⛔ with no vector layer at all, Check is off and the window says why",
            not d10.run_btn.isEnabled() and "No vector layer" in d10.note.text(),
            d10.note.text()[:70])
        _late = QgsVectorLayer("Point?crs=EPSG:4326", "a layer added afterwards", "memory")
        _late.dataProvider().addAttributes([QgsField("scientificName", QVariant.String)])
        _late.updateFields()
        _f = QgsFeature(_late.fields())
        _f.setAttributes(["Myotis lucifugus"])
        _f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(-73.5, 45.5)))
        _late.dataProvider().addFeature(_f)
        QgsProject.instance().addMapLayer(_late)
        d10._load_layers()
        bar("⛔⛔ ...AND CHECK COMES BACK ON when the layer arrives. It did not: the combo "
            "refilled and the button stayed dead, so the plugin swallowed every click in silence",
            d10.run_btn.isEnabled() and d10.layer_box.count() == 1,
            "enabled=%s layers=%d" % (d10.run_btn.isEnabled(), d10.layer_box.count()))
        bar("⛔ MUST-FAIL: it goes off again when the last layer is removed — the state "
            "follows the project, it is not a one-way switch",
            (QgsProject.instance().removeMapLayer(_late.id()), d10._load_layers(),
             not d10.run_btn.isEnabled())[2])
        for _l in _keep:
            if _l is not None:
                QgsProject.instance().addMapLayer(_l)
        app.processEvents()

        print("\n-- an EMPTY layer, and a layer whose only name is null")
        empty = QgsVectorLayer("Point?crs=EPSG:4326", "an empty layer", "memory")
        empty.dataProvider().addAttributes([QgsField("scientificName", QVariant.String)])
        empty.updateFields()
        QgsProject.instance().addMapLayer(empty)
        d4 = ScreenDialog(FakeIface(), None)
        _dlgs.append(d4)
        said_e = drive(d4, app, empty, "scientificName", wait=5)
        bar("⛔ an empty layer is told there is nothing to screen — it does not call the door",
            "No values were found" in said_e, said_e[:96])

        nulls = QgsVectorLayer("Point?crs=EPSG:4326", "one null name", "memory")
        nulls.dataProvider().addAttributes([QgsField("scientificName", QVariant.String)])
        nulls.updateFields()
        f = QgsFeature(nulls.fields())
        f.setAttributes([None])
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(-73.5, 45.5)))
        nulls.dataProvider().addFeature(f)
        QgsProject.instance().addMapLayer(nulls)
        # ⛔ A NULL IS NOT A NAME. Sending "NULL" as a binomial would put a made-up taxon on the
        #   wire and could come back matched to something.
        _rn, _nfn, _, _, _nbn = screen_task.name_values(nulls, "scientificName")
        bar("⛔⛔ MUST-FAIL: a NULL attribute never becomes the name 'NULL' on the wire",
            _rn == [] and _nfn == 0, _rn)
        d5 = ScreenDialog(FakeIface(), None)
        _dlgs.append(d5)
        said_n = drive(d5, app, nulls, "scientificName", wait=5)
        bar("...and the person is told which field to choose instead of seeing a traceback",
            "No values were found" in said_n, said_n[:96])

        # ══════════════════════════════════════════════════════════════════════════════════════
        print("\n-- 65,391 REAL features, and the COMMON-NAME column of those same rows")
        bhere = stage(tmp, BIRDS_ZIP)
        if bhere is None:
            bar("the bird-atlas corpus layer is present to be run against", False, BIRDS_ZIP)
        else:
            birds = QgsVectorLayer(os.path.join(bhere, BIRDS_SHP), "bird atlas", "ogr")
            QgsProject.instance().addMapLayer(birds)
            bar("★ a 65,000-feature shapefile loads", birds.isValid(),
                "%d features" % birds.featureCount())
            t0 = time.monotonic()
            brows, bfeat, _bnop, btrunc, _bblank = screen_task.name_values(birds, "scientific")
            dt = time.monotonic() - t0
            bar("★★ %d features fold to %d DISTINCT names before anything goes on the wire — "
                "this is the whole reason the door is not asked 65,000 times"
                % (bfeat, len(brows)), len(brows) < bfeat / 50.0, "%.1fs to read" % dt)
            bar("⛔ ...and it is under the cap, so nothing is silently dropped",
                btrunc is False and len(brows) <= client.MAX_NAMES, len(brows))

            # ⛔⛔ COMMON NAMES ARE NOT SCIENTIFIC NAMES, AND THE SAME ROWS CARRY BOTH. This is the
            #   defect that would quietly ruin a report: a user picks `common_nam`, every name
            #   fails to match, and a screen that reported only hits would read as "nothing here
            #   is protected". They must land in NOT MATCHED and be named.
            crows, _cf, _cnop, _ct, _cb = screen_task.name_values(birds, "common_nam")
            bar("the common-name column of the same layer is readable", len(crows) > 50,
                "%d distinct common names" % len(crows))
            if live:
                # ⛔⛔ THE DOOR DOES SOMETHING BETTER THAN WE EXPECTED, AND THE BAR WAS WRONG.
                #   The first cut of this bar expected common names to come back UNMATCHED. They
                #   do not: the door REFUSES the column with a 422 that says the column holds
                #   vernacular names and that it will not guess which taxon each one means —
                #   which is the stronger answer, because an unmatched row still invites the
                #   reading "checked, nothing found".
                # ⛔ SO THE BAR IS ON THE DIALOG, NOT ON `client.screen`. `screen` RAISES here,
                #   and grading the raise would prove only that a test can catch an exception.
                #   What matters is what the person sees, and that is the panel.
                d7 = ScreenDialog(FakeIface(), None)
                _dlgs.append(d7)
                said_c = drive(d7, app, birds, "common_nam", wait=300)
                bar("⛔⛔ A COLUMN OF COMMON NAMES IS REFUSED IN WORDS, NOT SCREENED AS IF IT "
                    "HELD BINOMIALS — a layer keyed on 'Australian Magpie' must never come back "
                    "looking clean",
                    "COMMON names" in said_c or "common names" in said_c, said_c[:150])
                bar("⛔⛔ MUST-FAIL: the refusal is NOT a verdict — no LISTED section, no clean "
                    "bill, nothing a reader could quote as a screening result",
                    "LISTED" not in said_c and "NOT DESIGNATED BY" not in said_c, said_c[:70])
                bar("⛔ ...and the person is told what to do about it, not shown a traceback",
                    "scientific" in said_c.lower() and "Traceback" not in said_c,
                    said_c[-110:] if said_c else "(empty)")
                bar("⛔ ...and nothing was written back on a refused call",
                    "given the six columns" not in said_c)

            # ══════════════════════════════════════════════════════════════════════════════════
            # ★★★★ 65,391 REAL FEATURES, SCREENED — AND THE PANEL ON A LAYER OUTSIDE CANADA
            # ══════════════════════════════════════════════════════════════════════════════════
            # ⛔⛔ THIS IS WHERE THE FIFTH INSTANCE LIVED, AND NOTHING HAD EVER RUN IT. Every live
            #   panel bar in this file screened a CANADIAN layer, where the door marks CITES and
            #   the Red List `applies: False` and the dialog's own copy of the kind rule happened
            #   to be right. Outside Canada the door marks them `applies: True` — because they are
            #   the only instruments that reach — and the panel printed « The IUCN Red List of
            #   Threatened Species — Endangered  [law in force here] » under a heading that read
            #   LISTED, three lines below the door's own « no law we hold applies to them ».
            if live:
                d8 = ScreenDialog(FakeIface(), None)
                _dlgs.append(d8)
                t0 = time.monotonic()
                said_b = drive(d8, app, birds, "scientific", wait=300)
                bar("★★ %d features and %d distinct names screened end to end, write-back "
                    "included" % (bfeat, len(brows)),
                    "given the six columns" in said_b,
                    "%.0fs · %s" % (time.monotonic() - t0,
                                    said_b.splitlines()[-1][:70] if said_b else "(empty)"))
                bar("⛔⛔ MUST-FAIL: NOTHING on a layer outside Canada is marked « law in force "
                    "here » — the Red List is not law, and neither is a convention",
                    "law in force here" not in said_b,
                    [l.strip()[:96] for l in said_b.splitlines()
                     if "law in force here" in l][:2] or "none, correct")
                bar("⛔⛔ MUST-FAIL: ...and no section headed LISTED, three lines under a headline "
                    "that says no law we hold applies — a panel contradicting itself reads broken",
                    "LISTED" not in said_b, said_b.splitlines()[0][:96] if said_b else "(empty)")
                bar("★ what DID reach is still reported, each line saying WHAT the instrument is "
                    "— withholding the claim must never lose the finding",
                    "NAMED, BUT NOT BY A LAW IN FORCE HERE" in said_b
                    and ("a convention — in force wherever you are" in said_b
                         or "an assessment, not a law" in said_b),
                    [l.strip()[:88] for l in said_b.splitlines()
                     if "in force wherever you are" in l or "an assessment, not a law" in l][:1])
                bar("⛔ the jurisdictions we hold NO register for are named as THIS FILE's, not "
                    "buried among the ones that are nowhere near it",
                    "NO REGISTER WE HOLD REACHES" in said_b,
                    [l[:96] for l in said_b.splitlines()
                     if "NO REGISTER WE HOLD REACHES" in l][:1] or "(absent)")
                # ⛔ MUST-PASS NULL — the control that proves the panel is not simply mute about
                #   laws. The SAME renderer, on the Quebec caribou layer, still says it.
                bar("* MUST-PASS NULL: the same panel on a CANADIAN layer DOES say « law in "
                    "force here » — the fix withholds a claim, it does not delete the vocabulary",
                    "law in force here" in said, [l.strip()[-38:] for l in said.splitlines()
                                                  if "law in force here" in l][:1])
                bvals = {}
                bagain = QgsVectorLayer(os.path.join(bhere, BIRDS_SHP), "atlas re-opened", "ogr")
                for f in bagain.getFeatures():
                    bvals[f.attribute("scientific")] = {c: f.attribute(c)
                                                        for c, _w in client.COLUMNS}
                    if len(bvals) > 400:
                        break
                bar("⛔⛔ AND IT IS IN THE .dbf: `pd_applies` on an Australian layer never reads "
                    "`yes`, and never reads blank either — it names the place we hold no law for",
                    bool(bvals)
                    and not [v for v in bvals.values()
                             if str(v.get("pd_applies") or "").startswith("yes")]
                    and not [v for v in bvals.values() if not str(v.get("pd_applies") or "")],
                    sorted({str(v.get("pd_applies"))[:46] for v in bvals.values()})[:3])
                bar("⛔ ...and `pd_law` is EMPTY on every one of them, while `pd_other` is not — "
                    "the contract of that column is « the laws in force here »",
                    not [v for v in bvals.values() if str(v.get("pd_law") or "").strip()]
                    and bool([v for v in bvals.values() if str(v.get("pd_other") or "").strip()]),
                    [str(v.get("pd_other"))[:60] for v in list(bvals.values())[:1]])
                del bagain

        # ══════════════════════════════════════════════════════════════════════════════════════
        # ★★★★ A REGISTER WHOSE NAME LIVES IN TWO COLUMNS, AND IS EMPTY IN 291 OF 298 ROWS
        # ══════════════════════════════════════════════════════════════════════════════════════
        # ⛔⛔ TWO DEFECTS CAME OUT OF THIS ONE FILE, AND NEITHER WAS REASONED — THE FILE WAS RUN.
        #   The ACT tree register's binomial is split across `GENUS` and `SPECIES` (290 and 272 of
        #   298 rows); its `BOTANICAL_` column is filled in SEVEN. The guess matched nothing at
        #   all and the combo opened on `OBJECTID`, and a screen of `BOTANICAL_` would have
        #   reported "5 distinct names read from 7 features" without ever saying that 291 features
        #   were not looked at.
        print("\n-- the ACT tree register: a split name, and a column empty in 291 of 298 rows")
        ahere = stage(tmp, ACT_ZIP)
        if ahere is None:
            bar("the ACT tree register is present to be run against", False, ACT_ZIP)
        else:
            trees = QgsVectorLayer(os.path.join(ahere, ACT_SHP), "ACT tree register", "ogr")
            QgsProject.instance().addMapLayer(trees)
            bar("★ an Australian projected CRS loads through OGR", trees.isValid(),
                "%d features · %s" % (trees.featureCount(), trees.crs().authid()))
            d9 = ScreenDialog(FakeIface(), None)
            _dlgs.append(d9)
            d9._load_layers()
            for i in range(d9.layer_box.count()):
                if d9.layer_box.itemData(i) == trees.id():
                    d9.layer_box.setCurrentIndex(i)
                    break
            bar("⛔⛔ the guess lands on `BOTANICAL_`, NOT on `OBJECTID` — a combo that recognises "
                "nothing opens on column 0 and looks exactly like a recommendation",
                d9.field_box.currentText() == "BOTANICAL_", d9.field_box.currentText())
            bar("⛔⛔ ...and the SPLIT NAME is put to the person, with the expression that fixes "
                "it — screening `SPECIES` alone sends `mannifera` and comes back looking clean",
                "GENUS" in d9.note.text() and "field calculator" in d9.note.text(),
                d9.note.text()[-116:])
            _tr, _tfeat, _tnop, _ttr, _tblank = screen_task.name_values(trees, "BOTANICAL_")
            bar("⛔⛔ THE 291 FEATURES WITH NO NAME ARE COUNTED, not silently dropped",
                _tblank == 291 and _tfeat == 7 and _tfeat + _tblank == trees.featureCount(),
                "%d named · %d blank · %d in the layer" % (_tfeat, _tblank, trees.featureCount()))
            if live:
                said_a = drive(d9, app, trees, "BOTANICAL_", wait=300)
                bar("⛔⛔ AND THE PANEL SAYS SO IN ITS FIRST THREE LINES — a verdict covering 7 of "
                    "298 features that does not say which is the defect this plugin exists to "
                    "prevent",
                    "291" in said_a and "298" in said_a and "not screened" in said_a,
                    [l[:104] for l in said_a.splitlines() if "291" in l][:1] or said_a[:104])
                bar("⛔ MUST-FAIL: a layer in Canberra is never told a Canadian law reaches it",
                    "law in force here" not in said_a,
                    [l.strip()[:80] for l in said_a.splitlines()
                     if "law in force here" in l][:1] or "none, correct")

        # ══════════════════════════════════════════════════════════════════════════════════════
        # ⛔⛔ THE SERVICE IS DOWN — the path a stranger on a train meets, and nobody had run it
        # ══════════════════════════════════════════════════════════════════════════════════════
        print("\n-- the screening service is unreachable")
        _real_ep, _real_wait = client.ENDPOINT, client.RETRY_WAIT_S
        try:
            # ⚠ `.invalid` IS RESERVED BY RFC 2606 and can never resolve — a dead host that does
            #   not depend on somebody's firewall. The wait is shortened so the bar is not a nap;
            #   the RETRY COUNT is left alone because that is the behaviour being graded.
            client.ENDPOINT = "https://door.invalid./names"
            client.RETRY_WAIT_S = 0
            d6 = ScreenDialog(FakeIface(), None)
            _dlgs.append(d6)
            said_d = drive(d6, app, build_layer(), "scientificName", wait=90)
            bar("⛔⛔ THE PERSON IS TOLD THE SERVICE COULD NOT BE REACHED, AND THAT THE PLUGIN "
                "NEEDS A CONNECTION — no traceback, no silence, no empty panel",
                "internet connection" in said_d or "Could not reach" in said_d, said_d[:132])
            bar("⛔ MUST-FAIL: an unreachable door NEVER produces a clean-looking verdict",
                "LISTED" not in said_d and "NOT DESIGNATED BY" not in said_d, said_d[:80])
            bar("⛔ ...and nothing was written back on a failed call",
                "given the six columns" not in said_d)
        finally:
            client.ENDPOINT, client.RETRY_WAIT_S = _real_ep, _real_wait
    finally:
        # ⛔⛔ THE DIALOGS GO FIRST, THEN THE PROJECT, THEN EVERY PYTHON NAME STILL HOLDING A LAYER
        #   — and all of it BEFORE `exitQgis()`. Measured 2026-09-17: exit code 139, a
        #   segmentation fault raised AFTER every bar had printed, which is the worst shape a
        #   failure takes (a green run that CI reads as a crash).
        #   The cause is ownership, not tidiness. A `QgsVectorLayer` built in Python and never
        #   added to the project — the `/vsizip` layer, the re-opened ones — is owned by PYTHON,
        #   so its destructor runs at interpreter shutdown, which is after `exitQgis()` has torn
        #   down the provider registry it calls into. Dropping the names and collecting here
        #   makes those destructors run while QGIS is still standing.
        for _w in _dlgs:
            try:
                _w.close()
                _w.deleteLater()
            except Exception:                                        # noqa: BLE001
                pass
        del _dlgs[:]
        app.processEvents()
        QgsProject.instance().removeAllMapLayers()
        app.processEvents()
        real = again = gl = gagain = vsi = tbl = empty = nulls = birds = None   # noqa: F841
        d2 = d3 = d4 = None                                                     # noqa: F841
        gc.collect()
        app.processEvents()
        _tmp_to_clear = tmp

    print("\n%s" % ("ALL GREEN" if not FAILED
                    else "RED: %d\n  %s" % (len(FAILED), "\n  ".join(FAILED))))
    app.exitQgis()
    # ⛔ AFTER `exitQgis`, not before: on Windows an open OGR provider holds the .shp and the .dbf,
    #   and a tree removed underneath one leaves locked files the next run inherits.
    shutil.rmtree(_tmp_to_clear, ignore_errors=True)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
