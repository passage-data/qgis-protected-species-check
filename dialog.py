# -*- coding: utf-8 -*-
"""dialog.py — one window, one question, one answer.

⛔ THE DIALOG SAYS WHAT WAS CHECKED AND WHAT WAS NOT. A screen that reports only hits reads as
   "nothing else is protected", which is a claim about the registers we are not entitled to make.
⛔ NO .ui FILE. A compiled resource is one more thing that can be stale in a zip; the window is
   small enough to be read as code.
"""
from qgis.core import QgsApplication, QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                                 QFormLayout, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar,
                                 QPushButton, QVBoxLayout)

import time

from . import client, screen_task

# ⛔⛔ THE SCOPED ENUM FORM, ON PURPOSE, AND IT IS NOT STYLE. QGIS 4 ships PyQt6, where the
#   unscoped spellings this file first used simply do not exist: `Qt.PlainText` and
#   `QDialogButtonBox.Close` both raised AttributeError at dialog CONSTRUCTION, so the window
#   never opened at all — every QGIS 4 user, on the first click, measured 2026-09-17 against
#   4.2.2 / PyQt 6.11. `Qt.TextFormat.PlainText` and `QDialogButtonBox.StandardButton.Close`
#   resolve under both bindings. `QgsTask.CanCancel` and `QVariant.String` were checked the same
#   way and are correct as they stand — the scoped forms of THOSE two are the ones that break.

# The places the registers cover, as the door names them — Canada and the United Kingdom, because
# those are the countries whose registers the service holds. "Read it from the layer" is first
# because a layer with coordinates answers this question better than a person can.
# ⛔ EVERY CODE HERE IS ONE THE DOOR CAN PLACE, and a live bar in `client_selftest` screens each
#   one and fails on any that comes back unplaced — a dropdown entry the service cannot place is a
#   promise the window makes and the answer breaks.
PLACES = [
    ("", "Read it from the layer's coordinates (recommended)"),
    ("CA-QC", "Quebec"), ("CA-ON", "Ontario"), ("CA-BC", "British Columbia"),
    ("CA-AB", "Alberta"), ("CA-SK", "Saskatchewan"), ("CA-MB", "Manitoba"),
    ("CA-NB", "New Brunswick"), ("CA-NS", "Nova Scotia"), ("CA-PE", "Prince Edward Island"),
    ("CA-NL", "Newfoundland and Labrador"), ("CA-YT", "Yukon"),
    ("CA-NT", "Northwest Territories"), ("CA-NU", "Nunavut"),
    # ⛔ THE LABEL SAID "federal law and the conventions only", WHICH IS NOT WHAT HAPPENS.
    #   Measured 2026-09-17 on the live door with `province=CA`: the federal Act answers, and the
    #   eleven provincial and territorial Acts we hold come back NOT ASKED — the file names the
    #   country and no subdivision, so there is no answer to give about them. "Only" read as a
    #   scope, when it is a limit of our placing; the cells now say `not established` and so
    #   does this.
    ("CA", "Canada — the federal Acts; the provincial ones cannot be asked without a province"),
    # ★★ #526 PUT EIGHT UNITED KINGDOM SCHEDULES IN THE CARDS, AND THIS LIST COULD NOT NAME THEM.
    #   A British table with no coordinates had no way to say where it is, so every instrument
    #   read `not established` — the one thing the dropdown exists to prevent. Measured live the
    #   same day: `GB-ENG` answers with the Wildlife and Countryside Act Schedule 5, `GB-SCT` with
    #   the 1994 Regulations' Schedule 2, and `GB-NIR` with `not covered`, naming Northern Ireland.
    #  ⛔ THE COUNTRY ITSELF IS NOT OFFERED. Schedule 5 extends to England and Wales and not to
    #   Northern Ireland, so a bare `GB` can only be answered « we did not ask » — an entry that
    #   guarantees a non-answer is a trap, not a choice.
    ("GB-ENG", "England"), ("GB-WLS", "Wales"), ("GB-SCT", "Scotland"),
    ("GB-NIR", "Northern Ireland"),
]


class ScreenDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self._task = None
        self._guess_says = ""            # set by `_layer_changed`, read by the note
        self._sent = []                  # set by `_run`, reconciled against the answer
        self._answer = None              # the door's own answer, kept so a bar can read it
        self._caveats, self._provenance = [], ""   # set by `_run`, carried into `_report`
        self.setWindowTitle("Protected Species Check")
        self.setMinimumWidth(620)

        self.layer_box = QComboBox()
        self.field_box = QComboBox()
        self.place_box = QComboBox()
        for code, label in PLACES:
            self.place_box.addItem(label, code)
        self.write_back = QCheckBox("Write the verdict back as six attribute columns")
        self.write_back.setChecked(True)

        form = QFormLayout()
        form.addRow("Layer", self.layer_box)
        form.addRow("Scientific name field", self.field_box)
        form.addRow("Where are these records?", self.place_box)

        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setTextFormat(Qt.TextFormat.PlainText)

        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setMinimumHeight(240)
        self.out.setPlaceholderText("The answer will appear here, register by register.")

        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.hide()

        self.run_btn = QPushButton("Check")
        self.run_btn.setDefault(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        row = QHBoxLayout()
        row.addWidget(self.run_btn)
        row.addStretch(1)
        row.addWidget(buttons)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.write_back)
        lay.addWidget(self.note)
        lay.addWidget(self.bar)
        lay.addWidget(self.out)
        lay.addLayout(row)

        self.layer_box.currentIndexChanged.connect(self._layer_changed)
        self.run_btn.clicked.connect(self._run)
        self._load_layers()

    # ── the two combos ───────────────────────────────────────────────────────────────────────
    def _load_layers(self):
        self.layer_box.clear()
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsVectorLayer) and lyr.isValid():
                self.layer_box.addItem(lyr.name(), lyr.id())
        # ⛔⛔ RE-ENABLED, NOT ONLY DISABLED. This read `if not count: setEnabled(False)` and
        #   had no path back on, so a window opened from the Vector menu on an empty project —
        #   which is what a person does, because the menu is right there — stayed dead after the
        #   layer was added. Measured 2026-09-17 driving the INSTALLED plugin in a real QGIS 4.2.2
        #   desktop: the combo refilled, the button did not, and Check swallowed every click in
        #   silence. A control that cannot come back is worse than one that is never offered.
        self.run_btn.setEnabled(bool(self.layer_box.count()))
        if not self.layer_box.count():
            self.note.setText("No vector layer is loaded. Add the layer holding your species "
                              "names — this window will pick it up.")
        self._layer_changed()

    def _current_layer(self):
        lid = self.layer_box.currentData()
        lyr = QgsProject.instance().mapLayer(lid) if lid else None
        return lyr if isinstance(lyr, QgsVectorLayer) else None

    def _sample_of(self, layer, n=25):
        """→ a `values_for(field)` that reads the first `n` non-empty values, once per field.

        ⚠ BOUNDED AND CACHED. This runs every time the layer combo changes, on layers of 65,000
          features; reading the whole column to decide which column to read would be a freeze the
          person cannot explain.
        """
        cache = {}

        def values_for(field):
            if field in cache:
                return cache[field]
            out = []
            idx = layer.fields().indexOf(field)
            if idx >= 0:
                for f in layer.getFeatures():
                    v = screen_task._text(f.attribute(idx))
                    if v:
                        out.append(v)
                    if len(out) >= n:
                        break
            cache[field] = out
            return out
        return values_for

    def _layer_changed(self):
        self.field_box.clear()
        lyr = self._current_layer()
        if lyr is None:
            return
        names = [f.name() for f in lyr.fields()]
        self.field_box.addItems(names)
        # ⛔ THE GUESS IS `client.guess_name_field`, AND IT USED TO MISS EVERY REAL LAYER WE
        #   HOLD. It compared case-sensitively against a list with `SCIENTIFIC` and `NOM_LATIN`
        #   in it, while the corpus carries `scientific`, `NOM_SCIEN` and `BOTANICAL_`. A combo
        #   that recognises nothing opens on column 0 — which on the bird atlas is `common_nam`.
        # ⛔ THE VALUES ARE SAMPLED, NOT JUST THE NAMES. Swept across 730 corpus layers, the
        #   name-only guess recommended `TaxonID` on four and `taxonid_left` — holding
        #   `100, 130, 150…` — on two more. A recommendation is worth nothing if it can point at
        #   a join key, and the column's own contents settle it in twenty-five reads.
        guessed, self._guess_says = client.guess_name_field(names, self._sample_of(lyr))
        if guessed in names:
            self.field_box.setCurrentIndex(names.index(guessed))
        # ⛔⛔ `geometryType() is not None` WAS ALWAYS TRUE, so this branch never once fired.
        #   Measured under QGIS 4.2.2: a layer with no geometry returns `GeometryType.Null`
        #   (value 4) — an enum MEMBER, never Python's `None`. So a CSV of species names was
        #   told nothing, the province was never asked for, and the screen came back with the
        #   jurisdiction unestablished and no explanation of why. `isSpatial()` is QGIS's own
        #   name for this exact question and is the only honest test.
        has_geom = lyr.isSpatial() and lyr.featureCount() > 0
        # ⛔⛔ NO COUNT OF REGISTERS LIVES HERE, AND THAT IS THE FIX. This read "Ten laws and
        #   three assessment lists… a layer outside Canada gets the conventions and the Red List
        #   only", and by 2026-09-17 both halves were false: the door's own cards carry 22 laws
        #   (14 Canada, 8 United Kingdom), and a UK layer comes back `pd_applies: yes` with the
        #   Wildlife and Countryside Act 1981 named in `pd_law` — measured, not reasoned.
        #   A number the plugin cannot verify goes stale on its own, which is how this one got to
        #   "Ten". The panel prints CHECKED AGAINST after every run, from the door's own
        #   `coverage.screened`, and that list cannot drift from what was actually screened.
        self.note.setText(
            "Laws in force where your records are, with the CITES and CMS Appendices beside them "
            "as conventions, and assessment lists that are never law. Every answer names the "
            "instrument, its edition, and what it was checked against."
            + ("" if has_geom else
            "  This layer has no geometry, so name the province — otherwise we cannot say which "
            "law is in force where your records are, and we will say that instead of guessing.")
            # ⛔ THE SPLIT-NAME SENTENCE IS THE ONLY USEFUL THING WE CAN SAY ABOUT A LAYER WHOSE
            #   binomial lives in two columns. Screening `SPECIES` alone matches nothing and
            #   reads as a clean layer; saying so and naming the calculator expression does not.
            + (("  " + self._guess_says) if self._guess_says else ""))

    # ── the run ──────────────────────────────────────────────────────────────────────────────
    def _run(self):
        lyr = self._current_layer()
        if lyr is None:
            return
        field = self.field_box.currentText()
        if not field:
            self.out.setPlainText("Choose the field that holds the scientific names.")
            return
        rows, n_feat, n_no_place, truncated, n_blank = screen_task.name_values(lyr, field)
        # ⛔⛔ A FILTER IS A LIMIT THAT EATS INFORMATION, AND IT WAS INVISIBLE HERE. QGIS honours a
        #   subset string everywhere, including in `getFeatures()`, so a filtered layer is screened
        #   in part and the answer reads as if it covered the file. Worse on the empty path: the
        #   window blamed the FIELD — "choose the field that holds one scientific name" — for a
        #   layer whose field was right and whose rows were simply hidden.
        subset = ""
        try:
            subset = (lyr.subsetString() or "").strip()
        except Exception:                                            # noqa: BLE001
            pass                                                     # a provider without filters
        if not rows:
            self.out.setPlainText(
                ("No values were found under “%s” — but a FILTER is active on this layer "
                 "(%s), so its rows are hidden from this window exactly as they are from the "
                 "map. Clear the filter, or choose the field that holds one scientific name "
                 "per feature." % (field, client._short(subset, 90))) if subset else
                ("No values were found under “%s”. Choose the field that holds one "
                 "scientific name per feature." % field))
            return
        # ⛔⛔ THESE SURVIVE THE ANSWER. Until 0.1.5 `_done` replaced the whole panel with the
        #   report, so the truncation notice and the "no usable geometry" count existed only
        #   while the panel read "Checking…" — a caveat that disappears the moment the verdict
        #   arrives is a caveat nobody has ever read.
        # ⛔ THE COUNT SAYS SENT WHEN IT MEANS SENT. Over the cap `rows` is already cut, so this
        #   read "5000 distinct names read from 5001 features" — understating what was READ by
        #   exactly the number that was dropped, on the one path where that number matters.
        self._provenance = ("%d distinct name%s read from %d feature%s under “%s”%s."
                            % (truncated or len(rows), "" if (truncated or len(rows)) == 1 else "s",
                               n_feat, "" if n_feat == 1 else "s", field,
                               (", and the first %d sent" % client.MAX_NAMES) if truncated else ""))
        self._caveats = []
        if subset:
            # ⚠ THE COUNT IS THE ONE WE CAN STAND BEHIND: the features this run actually read.
            #   The layer's own `featureCount()` honours the filter too, so the number hidden is
            #   not ours to state, and a made-up denominator would be worse than none.
            self._caveats.append(
                "⚠ A FILTER IS ACTIVE ON THIS LAYER (%s). This verdict covers the %d feature(s) "
                "it shows, not the whole file."
                % (client._short(subset, 90), n_feat + n_blank))
        # ⛔⛔ A SELECTION IS IGNORED, AND THAT WAS SILENT. Measured 2026-09-17: one feature of
        #   four selected, four screened, and the panel said "4 distinct names read from 4
        #   features" — true, and read by somebody who believes they screened their selection.
        #   QGIS puts "Selected features only" on half its processing tools, so the expectation
        #   is the software's own. We do not honour it (a screening is about the NAMES in a file,
        #   and a name outside the selection is still in the file the person will publish), and
        #   §4 says a choice we do not honour has to change what the caller sees. It is named,
        #   not overridden — the same ruling the filter got in 0.1.7, from the other direction:
        #   a filter LIMITS what we read and is reported as a limit; a selection does not, and is
        #   reported as not honoured.
        n_selected = 0
        try:
            n_selected = int(lyr.selectedFeatureCount())
        except Exception:                                            # noqa: BLE001
            pass                                                     # a provider without selection
        if n_selected and n_selected < n_feat + n_blank:
            self._caveats.append(
                "⚠ %d feature%s selected on this layer, and this screening does NOT stop at the "
                "selection — it covers all %d. Every name in the file is a name you will publish."
                % (n_selected, " is" if n_selected == 1 else "s are", n_feat + n_blank))
        lead = [self._provenance]
        if n_blank:
            # ⛔⛔ THE FEATURES THAT CARRY NO NAME ARE NAMED, IN THE FIRST THREE LINES. Measured
            #   2026-09-17 on the ACT tree register: 291 of its 298 features have nothing under
            #   `BOTANICAL_`, and the panel reported "5 distinct names read from 7 features"
            #   with no hint that 98% of the layer had not been looked at.
            self._caveats.append(
                "⛔ %d more feature%s carry NO value under “%s” — they were not screened "
                "at all. Pick the column that holds a name for them, or accept that this "
                "verdict covers %d of the layer's %d features."
                % (n_blank, "" if n_blank == 1 else "s", field, n_feat, n_feat + n_blank))
        if truncated:
            # ⛔⛔ THE NUMBER LEFT OVER, NOT JUST THE CAP. « Only the first 5000 were sent » does
            #   not tell a person whether one name is missing or fourteen hundred, and that is the
            #   difference between finishing and shipping a verdict over a third of a checklist.
            self._caveats.append(
                "⛔ This layer holds %d distinct names and only the first %d were sent — %d "
                "%s NOT screened. That is one pass; split the layer and run the rest."
                % (truncated, client.MAX_NAMES, truncated - client.MAX_NAMES,
                   "name was" if truncated - client.MAX_NAMES == 1 else "names were"))
        if n_no_place:
            # ⛔⛔ "THEIR PLACE COMES FROM THE LAYER" PROMISED A FALLBACK THAT DOES NOT EXIST.
            #   Measured 2026-09-17 on Belfast's street-tree register read as the CSV it is: all
            #   189 names carry no usable geometry and the layer states no place either, so there
            #   was no layer place for them to come from. The sentence read as reassurance two
            #   lines above the one that says the jurisdiction was never established.
            #   ALL of them and SOME of them are different findings and they had one sentence.
            # ⛔⛔ A PLACE THE PERSON CHOSE IS WHERE THE PLACE CAME FROM. The choice travels as a
            #   `stateProvince` constant on every row, and the door reads a column before it reads
            #   a coordinate — so once a place is chosen it answers for every name, placed or not,
            #   and « the rest of the layer » is a source that played no part.
            chosen = self.place_box.currentData()
            self._caveats.append(
                ("⚠ %d of them carry no usable geometry — this run answers every name about "
                 "the place you chose, %s, not about its features."
                 % (n_no_place, self.place_box.currentText())) if chosen else
                ("⛔ NONE of the %d name%s in this layer carries a usable position, and no "
                 "province was named — so nothing in this run states where these records are."
                 % (n_no_place, "" if n_no_place == 1 else "s"))
                if n_no_place == len(rows) else
                ("⚠ %d of them carry no usable geometry, so their place comes from the rest of "
                 "the layer, not from the feature." % n_no_place))
        self.out.setPlainText("\n".join(lead + self._caveats) + "\n\nChecking…")
        QApplication.processEvents()

        self.run_btn.setEnabled(False)
        self.bar.show()
        # ⛔ WHAT WE PUT ON THE WIRE, KEPT, so the answer can be reconciled against the question.
        #   Without it a name the service drops has no witness anywhere (`client.unanswered`).
        self._sent = [r[0] for r in rows]
        province = self.place_box.currentData() or None
        self._task = screen_task.ScreenTask(rows, province, self._done)
        QgsApplication.taskManager().addTask(self._task)

    def _done(self, answer, error):
        self.bar.hide()
        self.run_btn.setEnabled(True)
        if error:
            self.out.setPlainText(error)
            return
        checked_on = time.strftime("%Y-%m-%d")
        self._answer = answer
        self.out.setPlainText(self._report(answer, self._caveats, self._provenance))
        if not self.write_back.isChecked():
            return
        lyr = self._current_layer()
        n, why = screen_task.write_back(lyr, self.field_box.currentText(), answer, checked_on)
        tail = ("\n\n%d feature%s given the six columns: %s."
                % (n, "" if n == 1 else "s", ", ".join(c for c, _w in client.COLUMNS))
                if n else "\n\n⛔ Nothing was written back: %s." % why)
        self.out.setPlainText(self.out.toPlainText() + tail)

    # ── the answer, in the door's own words ──────────────────────────────────────────────────
    def _instrument_lines(self, cards, kinds):
        """→ one indented line per instrument that named this taxon, EACH SAYING WHAT IT IS.

        ⛔⛔ THE SORT IS `client.sort_designations`, NOT A SECOND COPY OF IT. This method used to
          decide for itself what counted as a law — `[d for d in designations if applies is not
          False]` — and that test is wrong for exactly the two kinds the door marks as applying
          when it is not a jurisdiction's Act. Measured 2026-09-17 against the live door on a
          Philippine layer: « The IUCN Red List of Threatened Species — Endangered  [law in force
          here] », under a section headed LISTED, three lines under the door's own headline
          « no law we hold applies to them ». The Red List is not law; the panel said it was.
        ⚠ A QUALIFIED LISTING SAYS SO ON EVERY KIND OF LINE, not only on a law's. CITES names
          *Pterocarpus indicus* in Appendix II only under its African populations — a reader
          screening a Philippine stand needs that clause as much as a caribou reader does.
        """
        out = []
        for d in kinds["law"]:
            # ⛔ `law in force here` beside a status the Act gives only to another population is
            #   the same assertion the attribute cell was making, on screen, where it is read
            #   first — so the qualification rides on the line, never in a footnote.
            ed = client._edition(cards, d.get("register"))
            out.append("      %s — %s%s  [%s%s]"
                       % (client._short(client._label(cards, d.get("register")), 58),
                          d.get("status") or "listed", client._qualification(d),
                          "law in force here" if d.get("applies") is True else "not established",
                          (", ed. " + ed) if ed else ""))
        # ⛔ THREE THINGS, THREE SENTENCES. A convention reaches you and does not lead; another
        #   jurisdiction's Act does not reach you at all; an assessment is not law anywhere.
        for key, said in (("convention", "a convention — in force wherever you are"),
                          ("elsewhere", "named, but not law where these records are"),
                          ("assessment", "an assessment, not a law")):
            for d in kinds[key]:
                out.append("      %s — %s%s  [%s]"
                           % (client._short(client._label(cards, d.get("register")), 58),
                              d.get("status") or "listed", client._qualification(d), said))
        for a in kinds["assessed"]:
            out.append("      %s — %s  [%s]"
                       % (client._short(client._label(cards, a.get("register")), 58),
                          a.get("status"), client.kind_says(cards, a.get("register"))))
        return out

    def _report(self, answer, caveats=(), provenance=""):
        cards = answer.get("register_cards") or []
        # ⛔ THE HEADLINE STILL LEADS. What the door chose to say first is the product; a count
        #   of how many rows we read is provenance and goes at the foot. But a caveat about what
        #   was NOT screened belongs directly under the headline, which is as far as a hurried
        #   reader gets — and is where the place question has always gone.
        lines = [answer.get("headline") or "", ""]
        if caveats:
            lines += list(caveats) + [""]
        if answer.get("place_established") is False:
            lines += ["⛔ " + (answer.get("place_says") or
                      "This layer states no place, so we did not establish which of these "
                      "instruments are in force where your records are."), ""]
        # ⛔⛔ AN ACT WE HOLD AND DID NOT ASK IS SAID HERE, ONCE. The door writes that sentence on
        #   every designation it could not gate (a file placed in a country and no subdivision),
        #   and the cells can only read « not established » — the reason has to reach the page,
        #   because a limit that eats information changes what the caller sees. An unplaced
        #   file's sentence is `place_says`, printed above, so it is not repeated.
        if answer.get("place_established") is not False:
            unasked = []
            for n in answer.get("names") or ():
                for d in n.get("designations") or ():
                    s = d.get("applies_says") if d.get("applies") is None else None
                    if s and s not in unasked and s != answer.get("place_says"):
                        unasked.append(s)
            lines += ["⛔ " + s for s in unasked] + ([""] if unasked else [])
        if answer.get("n_conflict"):
            lines += ["⚠ " + (answer.get("conflict_says") or ""), ""]

        # ⛔⛔ THREE BUCKETS, NOT TWO, AND THE MIDDLE ONE IS WHY THE FIX IS NOT JUST A FILTER.
        #   Narrowing LISTED to laws alone would drop a Philippine tiger's CITES Appendix I into
        #   "ON NO REGISTER WE HOLD", which is a worse lie than the one being fixed: withholding
        #   a claim must never lose a finding.
        listed, noted, clean, unmatched = [], [], [], []
        n_qualified = 0
        for n in answer.get("names") or ():
            kinds = client.sort_designations(n, cards)
            if not n.get("hit"):
                unmatched.append(n)
            elif kinds["law"]:
                listed.append((n, kinds))
                # ⛔⛔ THE HEADLINE AND THIS LIST COUNT DIFFERENT THINGS, AND A READER CANNOT
                #   KNOW THAT. Measured 2026-09-17 on Quebec's caribou range layer: the door's
                #   first line read "0 of your 1 species are listed under a law that applies in
                #   Québec" and the section directly beneath it was headed LISTED, naming SARA
                #   and the LEMV. The door's tally counts SETTLED listings; a listing qualified
                #   to a population the layer does not state is a QUESTION and is not counted —
                #   which is right, and invisible.
                #   A panel that contradicts itself is read as broken, and the reading a hurried
                #   person takes away is the big number at the top: "0 — nothing here".
                # ⛔ COUNTED OVER LAWS THAT REACH, AND ONLY THOSE. This sentence says "a law that
                #   reaches you"; it heard from a convention until 0.1.5 and said that about
                #   CITES' African populations of a Philippine tree.
                if any(client._qualification(d) for d in kinds["law"]
                       if d.get("applies") is True):
                    n_qualified += 1
            elif any(kinds[k] for k in ("convention", "elsewhere", "assessment")):
                noted.append((n, kinds))
            else:
                clean.append(n)
        if n_qualified:
            lines += ["⚠ %d of these %s named by a law that reaches you ONLY under a "
                      "population or subspecies your layer does not state — a question, not a "
                      "finding. %s listed below, and %s NOT counted in the line above. Settle it "
                      "by naming the population, or by reading the entry the instrument cites."
                      % (n_qualified, "is" if n_qualified == 1 else "are",
                         "It is" if n_qualified == 1 else "They are",
                         "it is" if n_qualified == 1 else "they are"), ""]

        # ⛔⛔ THE HEADING MAY NOT ASSERT WHAT THE ROWS UNDER IT DENY. It read
        #   "LISTED UNDER A LAW IN FORCE HERE" unconditionally, and on a file that states no place
        #   every row beneath it is marked `[not established]` — measured on Belfast's street-tree
        #   register, where the door had already said in its own words that it could not establish
        #   whether the instrument reaches those records. A reader takes the heading and goes.
        #   The `law` bucket holds `applies` True or None only (False sorts to `elsewhere`), so
        #   these three cases are the whole space.
        _reaches = {d.get("applies") is True for _n, _k in listed for d in _k["law"]}
        listed_head = ("LISTED UNDER A LAW IN FORCE HERE" if _reaches == {True} else
                       "LISTED BY A LAW — BUT WHERE IT IS IN FORCE WAS NOT ESTABLISHED"
                       if _reaches == {False} else
                       "LISTED BY A LAW WE HOLD — EACH LINE SAYS WHETHER IT REACHES YOU")
        # ⛔⛔ THE EIGHTH INSTANCE, AND IT IS THE SIXTH ONE'S TWIN. `LISTED` was fixed to follow
        #   its rows; the heading three inches below it was not. « NAMED, BUT NOT BY A LAW IN
        #   FORCE HERE » asserts what is in force here — measured 2026-09-17 on Belfast's own
        #   street-tree register, which states no place: the panel printed it over 19 taxa,
        #   two lines under the service's own sentence saying the place was NOT ESTABLISHED.
        #   An `elsewhere` row is the only member of this bucket that IS a law, and `elsewhere`
        #   exists only when a place gated it out — so the rows decide the heading, and the
        #   stronger form is sayable exactly when one of them is there.
        _noted_law = any(_k["elsewhere"] for _n, _k in noted)
        noted_head = ("NAMED, BUT NOT BY A LAW IN FORCE HERE" if _noted_law else
                      "NAMED, BUT BY NO LAW WE HOLD")
        for bucket, head in ((listed, listed_head), (noted, noted_head)):
            if not bucket:
                continue
            lines.append("%s  (%d)" % (head, len(bucket)))
            if bucket is noted:
                lines.append("  A convention, another jurisdiction's Act, or an assessment. Each "
                             "line says which. %s"
                             % ("None of them is a law where your records are."
                                if _noted_law else "None of them is a law we hold."))
            for n, kinds in bucket:
                lines.append("  %s" % n.get("value"))
                lines += self._instrument_lines(cards, kinds)
                c = n.get("conflict") or {}
                if c.get("says"):
                    lines.append("      ⚠ %s" % c["says"])
            lines.append("")
        if clean:
            # ⛔ "ON NO REGISTER WE HOLD" WAS FALSE FOR ANY COMMON SPECIES. Measured
            #   2026-09-17: *Acer saccharum* comes back with the Red List’s "Least Concern"
            #   in `assessed` — which `pd_other` prints in the very table beside this panel.
            #   The register holds it; nothing DESIGNATES it. That is the claim we may make.
            lines.append("NOT DESIGNATED BY ANY REGISTER WE HOLD  (%d): %s"
                         % (len(clean), ", ".join(n.get("value") for n in clean[:24])))
            if any(client.sort_designations(n, cards)["assessed"] for n in clean):
                lines.append("  Some carry an assessment STATUS all the same — the Red "
                             "List’s “Least Concern” and the like. It is in `pd_other`, "
                             "and it is not a designation.")
            lines.append("")
        if unmatched:
            lines.append("NOT MATCHED TO THE BACKBONE  (%d): %s"
                         % (len(unmatched), ", ".join(n.get("value") for n in unmatched[:24])))
            lines.append("  These were not screened. A common name or a misspelling lands here.")
            lines.append("")

        if provenance:
            lines.append(provenance)
        cov = answer.get("coverage") or {}
        # ⛔ THIS GOES ABOVE THE WALL OF REGISTER NAMES, NOT UNDER IT. `CHECKED AGAINST` is 28
        #   truncated instrument names on one line; the sentence that says we hold nothing for
        #   where the reader actually is was landing beneath all of it, where nobody reaches.
        here = client.uncovered_places(cov)
        if here:
            lines.append("⛔ NO REGISTER WE HOLD REACHES %s — where these records are. Silence "
                         "about them is about us, never about your species; `pd_applies` says so "
                         "in the table." % ", ".join(here[:12]))
        if cov.get("screened"):
            lines.append("CHECKED AGAINST: " + ", ".join(
                client._short(client._label(cards, r), 44) for r in cov["screened"]))
        # ⛔ THE PLACES IN THIS FILE COME FIRST AND ARE NAMED AS SUCH. `not_covered` also carries
        #   jurisdictions nowhere near the layer (Nunavut and PEI come back on a Quebec file), and
        #   running the two together let the one that matters — "we hold no law for where YOU
        #   are" — read as a footnote about somewhere else.
        missing = [p.get("name") for p in (cov.get("not_covered") or [])
                   if p.get("name") and not p.get("in_this_file")]
        if missing:
            lines.append("NO REGISTER HELD FOR: " + ", ".join(missing[:12])
                         + " — silence about these is about us, never about your species.")
        if answer.get("not_screened"):
            lines.append("NOT SCREENED THIS PASS: %s name(s)." % answer["not_screened"])
        # ⛔⛔ THE QUESTION AND THE ANSWER ARE RECONCILED, AND THE DIFFERENCE IS NAMED. 189 names
        #   went up from Belfast's tree register and 188 came back; `not_screened` read 0, because
        #   a value the service refuses as a name was never in its count. A missing row is a
        #   silent drop — exactly the shape §4 forbids — until somebody counts both ends.
        gone = client.unanswered(self._sent, answer)
        if gone:
            lines.append(
                "⛔ %d value%s we sent came back with NO row of its own, so %s not screened: %s. "
                "The service does not read %s as a scientific name — a null marker, a note or a "
                "blank stand-in. Nothing above counts %s."
                % (len(gone), "" if len(gone) == 1 else "s",
                   "it was" if len(gone) == 1 else "they were",
                   ", ".join('“%s”' % g for g in gone[:12]),
                   "it" if len(gone) == 1 else "them",
                   "it" if len(gone) == 1 else "them"))
        return "\n".join(lines).rstrip()
