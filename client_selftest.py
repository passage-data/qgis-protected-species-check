# -*- coding: utf-8 -*-
r"""client_selftest.py — THE BARS FOR THE COLUMNS THIS PLUGIN WRITES (INV-6).

    py qgis_plugin/passage_species_status/client_selftest.py            the fixtures
    py qgis_plugin/passage_species_status/client_selftest.py --live     …and one real call

⛔ NO QGIS IS IMPORTED HERE. `client.py` is deliberately free of QGIS so the half that decides what
  a cell says can be graded without a GUI; `screen_task.py` and `dialog.py` hold everything that
  needs QGIS and hold no verdict.
⛔ THE THING THESE BARS PROTECT: a cell that reads as a legal status when it is not one. Every
  must-fail below is a way that could happen.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import client                                                        # noqa: E402

FAILED = []


def bar(what, ok, detail=""):
    print("  %-4s %s%s" % ("ok" if ok else "FAIL", what, ("  — %s" % detail) if detail else ""))
    if not ok:
        FAILED.append(what)


CARDS = [
    {"register": "ca_sara", "instrument": "Species at Risk Act, S.C. 2002, c. 29, Schedule 1",
     "jurisdiction": "CA", "legal_instrument": True, "edition": "2026-02-26"},
    {"register": "on_pso", "instrument": "Species Conservation Act, 2025 (Ontario), O. Reg. 60/26",
     "jurisdiction": "CA-ON", "legal_instrument": True, "edition": "2026-03-30"},
    {"register": "cosewic", "instrument": "Committee on the Status of Endangered Wildlife in Canada",
     "jurisdiction": "CA", "legal_instrument": False, "edition": "2025-12-05"},
]


def name(value, designations, assessed=(), conflict=None, match="EXACT", accepted="",
         hit=True):
    # ⛔⛔ `hit` IS WHETHER THE GBIF BACKBONE MATCHED THE NAME — NOT WHETHER A REGISTER LISTED
    #   IT. This helper derived it from `designations`, so every screened-and-clean species built
    #   here claimed the backbone had never matched it, and the bars beneath graded that. The
    #   defect was invisible while `pd_applies` was blank for both; it is not invisible now that
    #   "we found nothing" and "we did not look" say different things.
    n = {"value": value, "designations": list(designations), "assessed": list(assessed),
         "match": match, "name": accepted, "hit": hit}
    if conflict:
        n["conflict"] = conflict
    return n


def main():
    print("-- a law in force here leads, and everything else stands apart")
    n = name("Asio flammeus",
             [{"register": "ca_sara", "outcome": "listed", "status": "Special Concern",
               "applies": True},
              {"register": "on_pso", "outcome": "listed", "status": "Threatened",
               "applies": False}],
             assessed=[{"register": "cosewic", "status": "Threatened"}],
             conflict={"kind": "status_differs_from_the_act",
                       "says": "COSEWIC assesses this taxon as Threatened; SARA Schedule 1 "
                               "carries it as Special Concern."},
             accepted="Asio flammeus (Pontoppidan, 1763)")
    c = client.columns_for(n, CARDS, "2026-09-17")
    bar("the applying law is in `pd_law`, by its own instrument name",
        "Species at Risk Act" in c["pd_law"] and "Special Concern" in c["pd_law"], c["pd_law"])
    bar("⛔ MUST-FAIL: a law that does NOT bind here never reaches `pd_law`",
        "Ontario" not in c["pd_law"] and "O. Reg" not in c["pd_law"], c["pd_law"])
    bar("…it is in `pd_other` instead, with its regulation number intact",
        "O. Reg. 60/26" in c["pd_other"], c["pd_other"])
    bar("⛔ MUST-FAIL: no instrument name is ever cut mid-citation",
        "60/…" not in c["pd_other"] and "60/…" not in c["pd_law"], c["pd_other"])
    bar("the assessment is in `pd_other` too, never in `pd_law`",
        "Committee on the Status" in c["pd_other"] and "Committee" not in c["pd_law"])
    bar("`pd_applies` reads yes", c["pd_applies"] == "yes", c["pd_applies"])
    bar("the edition of the APPLYING instrument rides in `pd_check`",
        "2026-02-26" in c["pd_check"], c["pd_check"])
    bar("⛔ MUST-FAIL: the edition of a non-applying instrument does NOT",
        "2026-03-30" not in c["pd_check"], c["pd_check"])
    bar("the conflict sentence is carried whole", "Schedule 1" in c["pd_conflic"])

    print("\n-- a file that states no place gets 'not established', never 'yes'")
    u = name("Asio flammeus",
             [{"register": "ca_sara", "outcome": "listed", "status": "Special Concern",
               "applies": None},
              {"register": "on_pso", "outcome": "listed", "status": "Threatened",
               "applies": None}])
    cu = client.columns_for(u, CARDS, "2026-09-17")
    bar("★ `pd_applies` is 'not established'", cu["pd_applies"] == "not established",
        cu["pd_applies"])
    bar("⛔ MUST-FAIL: it is never 'yes'", cu["pd_applies"] != "yes")
    bar("…both registers are shown, because neither was ruled out",
        "Species at Risk Act" in cu["pd_law"] and "O. Reg" in cu["pd_law"])
    bar("⛔ MUST-FAIL: no edition is claimed for an instrument we did not establish reaches you",
        "2026-02-26" not in cu["pd_check"] and "2026-03-30" not in cu["pd_check"], cu["pd_check"])

    print("\n-- a taxon on no register, and a name the backbone did not match")
    clean = client.columns_for(name("Acer saccharum", [], assessed=[], match="EXACT",
                                    accepted="Acer saccharum Marshall"), CARDS, "2026-09-17")
    bar("nothing is claimed in `pd_law`", clean["pd_law"] == "", clean["pd_law"])
    # ⛔ THIS BAR READ `== ""` UNTIL 0.1.5, AND THE BLANK WAS THE DEFECT. A taxon put to every
    #   law in force here and found on none of them has an answer, and the answer is `no`; the
    #   empty cell it used to get was indistinguishable from a name nobody screened.
    bar("a taxon screened against the laws in force here and found on none of them reads `no`",
        clean["pd_applies"] == "no", clean["pd_applies"])
    miss = client.columns_for(name("Caribou tarandus", [], match="NONE", hit=False), CARDS,
                              "2026-09-17")
    bar("an unmatched name says NONE and claims nothing else",
        miss["pd_match"].startswith("NONE") and not miss["pd_law"] and not miss["pd_other"])

    print("\n-- the columns fit a shapefile, and the CSV is what the door reads")
    bar("every column name is within the 10-character dBASE cap",
        all(len(c) <= 10 for c, _w in client.COLUMNS),
        [c for c, _w in client.COLUMNS if len(c) > 10])
    bar("every column name is unique", len({c for c, _w in client.COLUMNS}) == len(client.COLUMNS))
    csv = client.build_csv([("Myotis lucifugus", 45.5, -73.57), ("No place", None, None)]).decode()
    bar("the header is the three Darwin Core terms the door reads",
        csv.splitlines()[0] == "scientificName,decimalLatitude,decimalLongitude")
    bar("a coordinate is written to six decimals", "45.500000,-73.570000" in csv, csv)
    bar("⛔ a name with no place writes EMPTY cells, never a 0,0 that reads as the Gulf of Guinea",
        "No place,,\n" in csv, csv)
    commaed = client.build_csv([("Genus, species", 1.0, 2.0)]).decode().splitlines()[1]
    bar("⛔ a comma inside a name cannot open a fourth column",
        commaed.count(",") == 2 and commaed.startswith("Genus"), commaed)

    print("\n-- the cap and the timeout are the door's measured reach, not our caution")
    bar("★ the cap carries the lists people actually hold (100s to 1000s of names)",
        client.MAX_NAMES >= 2000, client.MAX_NAMES)
    bar("…and the timeout leaves room for a cold container", client.TIMEOUT_S >= 300,
        client.TIMEOUT_S)

    print("\n-- a cold 500 is retried; a refusal never is")
    import io as _io
    import urllib.error as _ue
    calls = {"n": 0}

    class _Resp:
        def __init__(self, b): self.b = b
        def read(self): return self.b
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _fake(seq):
        """⛔ THE TRANSPORT IS FAKED, THE RULE IS NOT. Nothing here touches the live door, so
        the bar grades the retry POLICY rather than the weather."""
        calls["n"] = 0

        def _open(req, timeout=None):
            i = calls["n"]
            calls["n"] += 1
            what = seq[min(i, len(seq) - 1)]
            if what == "ok":
                return _Resp(b'{"ok":true,"names":[],"register_cards":[]}')
            raise _ue.HTTPError("u", what, "boom", {}, _io.BytesIO(b'{"refusals":["nope"]}'))
        return _open

    _orig, _wait = client.urllib.request.urlopen, client.RETRY_WAIT_S
    client.RETRY_WAIT_S = 0
    _rows = [("Genus species", 1.0, 2.0)]
    try:
        client.urllib.request.urlopen = _fake([500, "ok"])
        client.screen(_rows)
        bar("★ a cold 500 then success is ANSWERED, not refused — measured under QGIS "
            "4.2.2 on 2026-09-17, and the first click decides whether a stranger clicks twice",
            calls["n"] == 2, calls["n"])

        client.urllib.request.urlopen = _fake([500, 500, 500])
        try:
            client.screen(_rows)
            bar("three 500s must refuse rather than loop", False)
        except client.ScreenError:
            bar("…and three 500s stop, rather than hanging", calls["n"] == client.RETRIES,
                calls["n"])

        client.urllib.request.urlopen = _fake([422, "ok"])
        try:
            client.screen(_rows)
            bar("⛔ MUST-FAIL: a 4xx refusal retried into a success", False)
        except client.ScreenError:
            bar("⛔ MUST-FAIL: a 4xx REFUSAL is never retried — one call, one honest "
                "answer", calls["n"] == 1, calls["n"])
    finally:
        client.urllib.request.urlopen, client.RETRY_WAIT_S = _orig, _wait

    print("\n-- a register the door sent no card for degrades to its id, never to a guess")
    bar("unknown register falls back to its own id",
        client._label(CARDS, "qc_emv_faune") == "qc_emv_faune")
    bar("…and no edition is invented for it", client._edition(CARDS, "qc_emv_faune") is None)

    # ══════════════════════════════════════════════════════════════════════════════════════════
    # ★★★★ A LAW, A CONVENTION AND AN ASSESSMENT ARE THREE THINGS — THE FOURTH TIME
    # ══════════════════════════════════════════════════════════════════════════════════════════
    # ⛔⛔ `applies: True` DOES NOT MAKE SOMETHING A LAW. `columns_for` consulted `_kind` only in
    #   its `applies is False` branch, so anything the door marked as applying went into `pd_law`
    #   whatever it actually was. MEASURED 2026-09-17 against the live door on a Philippine
    #   *Pterocarpus indicus*: `pd_law` read « …Appendix II …; The IUCN Red List of Threatened
    #   Species: Endangered » and `pd_applies` said « yes ».
    # ⛔ AND IT WAS EVERY LAYER OUTSIDE CANADA, not a corner: that is exactly where the
    #   conventions and the Red List are the only instruments that reach, so that is exactly
    #   where the door marks them `applies: True`.
    print("\n-- a law, a convention and an assessment land in three different columns")
    OUTSIDE = CARDS + [
        {"register": "iucn", "instrument": "The IUCN Red List of Threatened Species",
         "jurisdiction": "GLOBAL", "legal_instrument": False, "edition": "2026-1"},
        {"register": "cites", "instrument": "CITES Appendices I, II and III",
         "jurisdiction": "GLOBAL", "legal_instrument": True, "edition": "2026-03-05"}]
    far = name("Pterocarpus indicus",
               [{"register": "cites", "outcome": "listed_qualified", "status": "Appendix II",
                 "only": ["African populations"], "applies": True},
                {"register": "iucn", "outcome": "listed", "status": "Endangered",
                 "applies": True}])
    fc = client.columns_for(far, OUTSIDE, "2026-09-17")
    bar("⛔⛔ AN ASSESSMENT MARKED `applies: True` IS NOT A LAW — the Red List must never appear "
        "in `pd_law`, whose contract is « the laws in force here »",
        "IUCN" not in fc["pd_law"] and "Red List" not in fc["pd_law"], fc["pd_law"][:80])
    # ⛔ `pd_applies` MUST NOT SAY `yes` HERE — that is the whole finding. What it says INSTEAD
    #   is a 0.1.5 matter: with the answer's `coverage` in hand it names the place we hold nothing
    #   for; without it, the weaker honest answer, `no`. Neither is a claim about a law.
    bar("⛔⛔ ...nor may it answer `pd_applies` `yes`, which asks whether a LAW reaches these "
        "records", not fc["pd_applies"].startswith("yes"), "%r" % fc["pd_applies"])
    fc_cov = client.columns_for(far, OUTSIDE, "2026-09-17",
                                {"places": ["PH"],
                                 "not_covered": [{"jurisdiction": "PH", "name": "Philippines",
                                                  "in_this_file": True}]})
    bar("★ ...and handed the answer's own `coverage`, it names the place we hold no law for",
        fc_cov["pd_applies"].startswith("not covered") and "Philippines" in fc_cov["pd_applies"],
        fc_cov["pd_applies"])
    bar("⛔ a convention marked `applies: True` is still not the jurisdiction's law",
        "CITES" not in fc["pd_law"] and "Appendices" not in fc["pd_law"], fc["pd_law"][:80])
    bar("★ both are REPORTED, in `pd_other` — this withholds a claim, it does not drop a finding",
        "Red List" in fc["pd_other"] and "Appendix II" in fc["pd_other"], fc["pd_other"][:90])
    bar("★ ...and the convention's QUALIFIED marker survives the move",
        "QUALIFIED" in fc["pd_other"] and "African populations" in fc["pd_other"])

    # ⛔ MUST-PASS NULL — the control that proves this is not simply blanking everything.
    near = name("Storeria dekayi",
                [{"register": "ca_sara", "outcome": "listed", "status": "Endangered Species",
                  "applies": True},
                 {"register": "iucn", "outcome": "listed", "status": "Least Concern",
                  "applies": True}],
                assessed=[{"register": "cosewic", "status": "Endangered"}])
    nc = client.columns_for(near, OUTSIDE, "2026-09-17")
    bar("* MUST-PASS NULL: a real law still lands in `pd_law` and still answers `yes`",
        "Species at Risk Act" in nc["pd_law"] and nc["pd_applies"] == "yes", nc["pd_applies"])
    bar("* MUST-PASS NULL: ...and the assessment beside it is still reported in `pd_other`",
        "Red List" in nc["pd_other"], nc["pd_other"][:80])
    # ⛔⛔ THE COMBINATION THAT MADE A QUALIFIED LISTING READ AS SETTLED: an ASSESSMENT supplied
    #   the unqualified `applies: True` that set `settled`, so `pd_applies` printed a plain `yes`
    #   for a taxon whose only instrument was qualified.
    mix = name("Mixed",
               [{"register": "ca_sara", "outcome": "listed_qualified", "status": "Threatened",
                 "only": ["Southern Mountain population"], "applies": True},
                {"register": "iucn", "outcome": "listed", "status": "Endangered",
                 "applies": True}])
    mc = client.columns_for(mix, OUTSIDE, "2026-09-17")
    bar("⛔⛔ an assessment cannot settle a QUALIFIED law — `pd_applies` reads `yes (qualified)`, "
        "not `yes`, when the only law that reaches is qualified",
        mc["pd_applies"] == "yes (qualified)", mc["pd_applies"])

    # ══════════════════════════════════════════════════════════════════════════════════════════
    # ★★★★ A QUALIFIED LISTING IS A QUESTION — NEVER A FINDING, AND NEVER AN ABSENCE
    # ══════════════════════════════════════════════════════════════════════════════════════════
    # ⛔⛔ THE FIXTURE IS WHAT THE LIVE DOOR ACTUALLY RETURNED on 2026-09-17 for Quebec's own
    #   caribou range layer (`reports/corpus/mailbox0821/`, NOM_SCIEN). Not an invention: SARA
    #   Schedule 1 names *Rangifer tarandus caribou* only under the Southern Mountain and
    #   Northern Mountain populations, and that shapefile is the GASPESIE population — which SARA
    #   carries separately, and as Endangered. The plugin wrote `pd_law: ca_sara: Threatened
    #   Species` and `pd_applies: yes`, which is a status the register never gave to this animal.
    print("\n-- a QUALIFIED listing: the caribou, as the live door returned it")
    CARIBOU_CARDS = CARDS + [
        {"register": "qc_emv_faune", "instrument": "Loi sur les espèces menacées ou vulnérables, "
         "RLRQ c. E-12.01 (faune)", "jurisdiction": "CA-QC", "legal_instrument": True,
         "edition": "2026-01-14"}]
    car = name("Rangifer tarandus caribou",
               [{"register": "ca_sara", "outcome": "listed_qualified", "status": "Threatened Species",
                 "only": ["Southern Mountain population", "Northern Mountain population"],
                 "applies": True},
                {"register": "qc_emv_faune", "outcome": "listed_qualified", "status": "menacée",
                 "only": ["le caribou des bois, écotype montagnard, population de la Gaspésie"],
                 "applies": True}],
               accepted="Rangifer tarandus caribou (Gmelin, 1788)")
    cc = client.columns_for(car, CARIBOU_CARDS, "2026-09-17")
    bar("⛔⛔ `pd_applies` does NOT read a bare `yes` when every applying listing is QUALIFIED — "
        "that cell asserted a SARA status belonging to two other populations",
        cc["pd_applies"] == "yes (qualified)", cc["pd_applies"])
    bar("⛔⛔ ...and `pd_law` NAMES the populations the Act actually listed, so the reader can "
        "settle it without opening the Act",
        "QUALIFIED" in cc["pd_law"] and "Southern Mountain" in cc["pd_law"],
        cc["pd_law"][:120])
    bar("★ the instrument is still named and the edition still rides",
        "Species at Risk Act" in cc["pd_law"] and "ed." in cc["pd_check"], cc["pd_check"][:60])
    # ⛔ MUST-PASS NULL — the control that proves the marker is not simply always on.
    plain = name("Myotis lucifugus",
                 [{"register": "ca_sara", "outcome": "listed", "status": "Endangered Species",
                   "applies": True}])
    pc = client.columns_for(plain, CARDS, "2026-09-17")
    bar("* MUST-PASS NULL: a SETTLED listing still reads a plain `yes`, with no qualification "
        "clause — the marker is not always-on",
        pc["pd_applies"] == "yes" and "QUALIFIED" not in pc["pd_law"], pc["pd_applies"])
    mixed = name("Mixed case",
                 [{"register": "ca_sara", "outcome": "listed", "status": "Endangered",
                   "applies": True},
                  {"register": "on_pso", "outcome": "listed_qualified", "status": "Threatened",
                   "only": ["Carolinian population"], "applies": True}])
    mc = client.columns_for(mixed, CARDS, "2026-09-17")
    bar("★ one SETTLED listing beside a qualified one still earns a plain `yes` — the question "
        "is about the qualified register, not about whether the taxon is protected",
        mc["pd_applies"] == "yes" and "QUALIFIED" in mc["pd_law"], mc["pd_applies"])
    bar("⛔ a qualified listing with no populations named still says it is qualified",
        "QUALIFIED" in client._qualification(
            {"outcome": "listed_qualified", "only": []}))
    bar("⛔ MUST-FAIL: `_qualification` is SILENT on a settled listing",
        client._qualification({"outcome": "listed", "only": ["x"]}) == "")

    # ⛔⛔ AND THE ABSENCE READING, WHICH IS THE ONE THAT ALREADY HAPPENED ONCE.
    bar("⛔⛔ MUST-FAIL: a qualified listing is never dropped from `pd_law` — reading it as an "
        "ABSENCE is what told a reader the fin whale is not protected federally",
        bool(cc["pd_law"]) and "ca_sara" not in cc["pd_applies"] and cc["pd_applies"] != "no",
        cc["pd_law"][:60])

    # ══════════════════════════════════════════════════════════════════════════════════════════
    # ★★★★ THE FIFTH TIME — AND A BAR FOR EVERY PLACE THE THREE ARE TOLD APART
    # ══════════════════════════════════════════════════════════════════════════════════════════
    # ⛔⛔ THE FOURTH FIX WAS REAL AND IT DID NOT HOLD, because the rule was written out twice.
    #   `columns_for` was corrected on 2026-09-17; the dialog's `_report` kept its own copy —
    #   `[d for d in designations if d.get("applies") is not False]` — and on a Philippine layer
    #   printed « The IUCN Red List of Threatened Species — Endangered  [law in force here] »
    #   under a heading that read LISTED, three lines below the door's own headline « no law we
    #   hold applies to them ». Every bar below names ONE place the three are told apart, and the
    #   census at the end is the one that would have caught the fifth instance.
    print("\n-- one sorter: every kind, and the census that says there is only one copy of it")
    SORT_CARDS = CARDS + [
        {"register": "iucn", "instrument": "The IUCN Red List of Threatened Species",
         "jurisdiction": "GLOBAL", "legal_instrument": False, "edition": "2026-1"},
        {"register": "cites", "instrument": "CITES Appendices I, II and III",
         "jurisdiction": "GLOBAL", "legal_instrument": True, "edition": "2026-03-05"}]
    every = name("Every kind at once",
                 [{"register": "ca_sara", "outcome": "listed", "status": "Endangered Species",
                   "applies": True},
                  {"register": "on_pso", "outcome": "listed", "status": "Threatened",
                   "applies": False},
                  {"register": "cites", "outcome": "listed", "status": "Appendix II",
                   "applies": True},
                  {"register": "iucn", "outcome": "listed", "status": "Endangered",
                   "applies": True}],
                 assessed=[{"register": "cosewic", "status": "Endangered"}])
    k = client.sort_designations(every, SORT_CARDS)
    bar("★ `sort_designations` · a LAW in force here sorts to `law` (MUST-PASS CONTROL: the "
        "mechanism is not simply emptying the bucket)",
        [d["register"] for d in k["law"]] == ["ca_sara"], [d["register"] for d in k["law"]])
    bar("⛔ `sort_designations` · a CONVENTION marked `applies: True` sorts to `convention`, "
        "never to `law` — this is the exact value the fifth instance read as a law",
        [d["register"] for d in k["convention"]] == ["cites"],
        [d["register"] for d in k["convention"]])
    bar("⛔ `sort_designations` · an ASSESSMENT marked `applies: True` sorts to `assessment`",
        [d["register"] for d in k["assessment"]] == ["iucn"],
        [d["register"] for d in k["assessment"]])
    bar("⛔ `sort_designations` · another jurisdiction's ACT sorts to `elsewhere` — a law that "
        "does not reach you is still a law, never an assessment",
        [d["register"] for d in k["elsewhere"]] == ["on_pso"],
        [d["register"] for d in k["elsewhere"]])
    bar("`sort_designations` · `assessed` stays its own bucket, sorted where it is used",
        [d["register"] for d in k["assessed"]] == ["cosewic"],
        [d["register"] for d in k["assessed"]])
    bar("⛔ MUST-FAIL: no register is in two buckets, and none was dropped",
        sum(len(v) for v in k.values()) == 5
        and len({d["register"] for v in k.values() for d in v}) == 5,
        {b: [d["register"] for d in v] for b, v in k.items()})

    bar("★ `kind_says` · a convention is captioned as one",
        client.kind_says(SORT_CARDS, "cites").startswith("a convention"),
        client.kind_says(SORT_CARDS, "cites"))
    bar("★ `kind_says` · an assessment is captioned as one",
        client.kind_says(SORT_CARDS, "iucn") == "an assessment, not a law",
        client.kind_says(SORT_CARDS, "iucn"))
    bar("⛔ `kind_says` · a LAW the door merely consulted is NOT captioned « an assessment » — "
        "the same conflation, arriving from the other direction",
        client.kind_says(SORT_CARDS, "ca_sara").startswith("a law"),
        client.kind_says(SORT_CARDS, "ca_sara"))

    # ⛔⛔ THE CENSUS — THE BAR THAT WOULD HAVE CAUGHT THE FIFTH INSTANCE. Every bar above grades
    #   the sorter; none of them can see a SECOND sorter written somewhere else, which is what
    #   the defect actually was. The kind of a register is decided by two facts on its card —
    #   `legal_instrument` and a `GLOBAL` jurisdiction — so any file that reads either of those
    #   for itself is deciding a kind for itself.
    # ⚠ A ZERO ON BOTH SIDES WOULD MEAN THE RIG NEVER READ A FILE, so the count INSIDE `client.py`
    #   is printed beside the count outside it. The mechanism-OFF number is the one on the left.
    print("\n-- the census: is there anywhere else in the shipped plugin that decides a kind?")
    _dir = os.path.dirname(os.path.abspath(__file__))
    _tells = ("legal_instrument", '"GLOBAL"', "_kind(")
    _inside, _outside = 0, {}
    for _fn in sorted(os.listdir(_dir)):
        if not _fn.endswith(".py") or _fn.endswith("_selftest.py"):
            continue
        _txt = io.open(os.path.join(_dir, _fn), encoding="utf-8").read()
        # the docstrings quote the defect they exist to prevent; only CODE decides anything
        _code = "\n".join(l for l in _txt.splitlines()
                          if not l.lstrip().startswith(("#", '"', "'")))
        _hits = sum(_code.count(t) for t in _tells)
        if _fn == "client.py":
            _inside = _hits
        elif _hits:
            _outside[_fn] = _hits
    bar("⛔⛔ THE KIND IS DECIDED IN ONE FILE. Nothing else in the shipped plugin reads "
        "`legal_instrument`, a `GLOBAL` jurisdiction or `_kind` for itself — a second copy of "
        "that rule IS the defect, five times over",
        not _outside, "outside client.py: %s  ·  inside it: %d occurrence(s)"
        % (_outside or "none", _inside))
    bar("* MUST-PASS NULL: the census really read the files — a 0 on the inside count would mean "
        "it matched nothing anywhere and the bar above passed for free",
        _inside >= 3, _inside)

    # ══════════════════════════════════════════════════════════════════════════════════════════
    # ★★★★ `pd_applies` — FOUR FINDINGS THAT USED TO SHARE ONE EMPTY CELL
    # ══════════════════════════════════════════════════════════════════════════════════════════
    print("\n-- `pd_applies` tells 'we found nothing' from 'we did not look' from 'we hold none'")
    PH_COV = {"places": ["PH"],
              "not_covered": [{"jurisdiction": "PH", "name": "Philippines", "country": "PH",
                               "in_this_file": True}]}
    QC_COV = {"places": ["CA-QC"],
              "not_covered": [{"jurisdiction": "CA-NU", "name": "Nunavut", "country": "CA",
                               "in_this_file": False}]}
    far = name("Pterocarpus indicus",
               [{"register": "cites", "outcome": "listed", "status": "Appendix II",
                 "applies": True},
                {"register": "iucn", "outcome": "listed", "status": "Endangered",
                 "applies": True}])
    far["hit"] = True
    fc = client.columns_for(far, SORT_CARDS, "2026-09-17", PH_COV)
    bar("⛔⛔ a layer where we hold NO register says so — `not covered`, naming the place. A "
        "blank cell here read exactly like a species we screened and cleared",
        fc["pd_applies"].startswith("not covered") and "Philippines" in fc["pd_applies"],
        fc["pd_applies"])
    bar("★ ...and what DID reach is still reported, so withholding the claim loses no finding",
        "Appendix II" in fc["pd_other"] and "Red List" in fc["pd_other"], fc["pd_other"][:90])
    clean_qc = name("Acer saccharum", [], assessed=[{"register": "iucn",
                                                     "status": "Least Concern"}])
    clean_qc["hit"] = True
    cq = client.columns_for(clean_qc, SORT_CARDS, "2026-09-17", QC_COV)
    bar("★ a taxon we screened against the laws in force here and did not find reads `no` — a "
        "blank told a reader nothing at all, and it is the commonest row in any layer",
        cq["pd_applies"] == "no", cq["pd_applies"])
    bar("⛔ MUST-FAIL CONTROL: `not covered` does NOT leak onto a Quebec file because the door "
        "named Nunavut — `in_this_file` is the whole test",
        "not covered" not in cq["pd_applies"], cq["pd_applies"])
    unmatched = name("Caribou tarandus", [], match="NONE")
    unmatched["hit"] = False
    uc = client.columns_for(unmatched, SORT_CARDS, "2026-09-17", QC_COV)
    bar("⛔⛔ a name the BACKBONE never matched reads `not checked`, never `no` — it was never "
        "put to a register at all, and the cell said the same thing as a cleared species",
        uc["pd_applies"].startswith("not checked") and "backbone" in uc["pd_applies"],
        uc["pd_applies"])
    starved = name("Never reached", [])
    starved["hit"] = True
    starved["budget_expired"] = True
    sc = client.columns_for(starved, SORT_CARDS, "2026-09-17", QC_COV)
    bar("⛔ a name the screening budget never reached reads `not checked`, with the reason",
        sc["pd_applies"].startswith("not checked") and "budget" in sc["pd_applies"],
        sc["pd_applies"])
    # ⛔ MUST-PASS NULL — the control that proves the new vocabulary did not swallow the old one.
    live = name("Myotis lucifugus", [{"register": "ca_sara", "outcome": "listed",
                                      "status": "Endangered Species", "applies": True}])
    lc = client.columns_for(live, SORT_CARDS, "2026-09-17", QC_COV)
    bar("* MUST-PASS NULL: a real listing still reads a plain `yes`, and still names the Act",
        lc["pd_applies"] == "yes" and "Species at Risk Act" in lc["pd_law"], lc["pd_applies"])
    placeless = name("Asio flammeus", [{"register": "ca_sara", "outcome": "listed",
                                        "status": "Special Concern", "applies": None}])
    pl = client.columns_for(placeless, SORT_CARDS, "2026-09-17", {})
    bar("* MUST-PASS NULL: a file that states no place still reads `not established`",
        pl["pd_applies"] == "not established", pl["pd_applies"])
    bar("⛔ MUST-FAIL: every value `pd_applies` can take fits the column and is filterable by "
        "its first word", all(len(v) <= 254 and v.split()[0] in
                              ("yes", "no", "not") for v in
                              (fc["pd_applies"], cq["pd_applies"], uc["pd_applies"],
                               sc["pd_applies"], lc["pd_applies"], pl["pd_applies"])),
        sorted({v.split()[0] for v in (fc["pd_applies"], cq["pd_applies"], uc["pd_applies"],
                                       lc["pd_applies"], pl["pd_applies"])}))
    bar("⛔⛔ MUST-FAIL: a FILE THAT STRADDLES a covered place and an uncovered one never claims "
        "`not covered` — one cell cannot say where one record is, and the weaker answer is the "
        "honest one",
        client.wholly_uncovered({"places": ["CA-QC", "PH"],
                                 "not_covered": [{"jurisdiction": "PH", "name": "Philippines",
                                                  "in_this_file": True}]}) == [],
        "straddling file → %r" % (client.wholly_uncovered(
            {"places": ["CA-QC", "PH"],
             "not_covered": [{"jurisdiction": "PH", "name": "Philippines",
                              "in_this_file": True}]}),))

    # ══════════════════════════════════════════════════════════════════════════════════════════
    # ★★★★ WHICH COLUMN HOLDS THE NAME — GRADED ON THE FIELD LISTS OF THREE REAL FILES
    # ══════════════════════════════════════════════════════════════════════════════════════════
    # ⛔⛔ THESE ARE THE ACTUAL COLUMN NAMES, read off the three shapefiles in `reports/corpus/`
    #   on 2026-09-17. The guess list this replaced matched NONE of them, and a QComboBox opens
    #   on index 0 — so the bird atlas opened on `common_nam`, the one column the door refuses.
    print("\n-- the name column, guessed on the field lists of three real layers")
    CARIBOU_FIELDS = ["EO_ID", "NOM_POP", "NOM_FRANCA", "AUTRES_NM", "NOM_ANGLA", "NOM_SCIEN",
                      "EOTYPE", "Rang_S", "LEMV", "Tempo", "METHODE", "SUP_KM2", "SUP_HA",
                      "DATE_MAJ", "Shape_Leng", "Shape_Area"]
    BIRD_FIELDS = ["common_nam", "scientific", "location", "start_date", "survey_tim", "search",
                   "accuracy_d", "gps_used", "lga", "species_nu", "long", "lat"]
    ACT_FIELDS = ["OBJECTID", "TREE_REGIS", "TREE_REFER", "STATUS", "CRITERIA", "REISTRATIO",
                  "REGISTRATI", "NUMBER_OF_", "APPROVAL_D", "BOTANICAL_", "GENUS", "SPECIES",
                  "NATIVE_OR_", "COMMON_NAM", "TREE_HEIGH", "CANOPY_DIA", "TRUNK_CIRC",
                  "LOCATION", "STREET_NUM", "STREET_NAM", "BLOCK", "SECTION", "DIVISION",
                  "DISTRICT", "LAND_USE", "LINK", "TREE_MANAG", "TREE_MAN_1", "GlobalID",
                  "Shape__Are", "Shape__Len"]
    g1, _s1 = client.guess_name_field(CARIBOU_FIELDS)
    bar("★ Quebec's caribou range layer: `NOM_SCIEN`, not `EO_ID` (the list held `NOM_LATIN`)",
        g1 == "NOM_SCIEN", g1)
    g2, _s2 = client.guess_name_field(BIRD_FIELDS)
    bar("⛔⛔ the bird atlas: `scientific`, NOT `common_nam` — a case-sensitive list matched "
        "nothing here, and column 0 of this layer is the one column the door refuses outright",
        g2 == "scientific", g2)
    g3, s3 = client.guess_name_field(ACT_FIELDS)
    bar("★ the ACT tree register: `BOTANICAL_`, the dBASE-truncated botanical name",
        g3 == "BOTANICAL_", g3)
    bar("⛔⛔ ...and the SPLIT NAME is named to the person. `SPECIES` there holds `mannifera`; "
        "screening an epithet matches nothing and reads as a clean layer",
        "GENUS" in s3 and "SPECIES" in s3 and "field calculator" in s3, s3[:104])
    bar("⛔ MUST-FAIL: `SPECIES` is never guessed while a `GENUS` column sits beside it",
        g3 != "SPECIES", g3)
    DUBLIN = ["field_1", "Dublin Employment ('000) - Construction (F)",
              "Dublin Employment ('000) - Professional, scientific and technical activities (M)",
              "Private Sector", "Total"]
    # ★★ THE FILE THE INSTALLED PLUGIN WAS ACTUALLY RUN ON, 2026-09-17: 31,666 Victorian frog
    #   census records, picked by a seeded shuffle of 877 corpus vector files and the first that
    #   loaded with a name column. Its column is two words with a SPACE, which no exact spelling
    #   in `NAME_FIELD_WANTS` holds — the hint path is what finds it, and this is the real file
    #   that proves the hint earns its place.
    FROG = ["OBJECTID", "Unique ID", "Date", "Time Start", "Latitude", "Longitude",
            "Type of observation", "Scientific name", "Common name", "Number", "x", "y"]
    g7, _s7 = client.guess_name_field(FROG)
    bar("★★ the frog census: “Scientific name” — two words and a space, found by the HINT, not "
        "by any exact spelling. This is the layer the INSTALLED plugin screened end to end",
        g7 == "Scientific name", g7)
    bar("⛔ MUST-FAIL: not “Common name”, and not “OBJECTID” — the two ways to be silently wrong "
        "on this file", g7 not in ("Common name", "OBJECTID"), g7)
    g6, _s6 = client.guess_name_field(DUBLIN)
    bar("⛔⛔ MUST-FAIL: a HINT may match a column name, never a sentence — this Irish "
        "employment table contains “scientific and technical activities” and would have been "
        "handed a column of statistics as its species names",
        g6 is None, g6)
    bar("* MUST-PASS NULL: the same hint still finds a real one-word column",
        client.guess_name_field(["id", "Scientific name (accepted)"])[0]
        == "Scientific name (accepted)",
        client.guess_name_field(["id", "Scientific name (accepted)"])[0])
    g4, s4 = client.guess_name_field(["id", "geom", "note", "count"])
    bar("⛔ a layer with no name-like column guesses NOTHING and says so, rather than opening "
        "on column 0 and looking like a choice", g4 is None and "Choose the one" in s4, s4[:72])
    g5, _s5 = client.guess_name_field(["id", "species", "date"])
    bar("* MUST-PASS NULL: a LONE `species` column with no genus beside it IS the name",
        g5 == "species", g5)

    # ══════════════════════════════════════════════════════════════════════════════════════════
    # ★★★★ THE PRODUCT TOKEN — THREE FILES THAT MUST AGREE, AND NOTHING USED TO CHECK ANY PAIR
    # ══════════════════════════════════════════════════════════════════════════════════════════
    # ⛔⛔ THE FAILURE THIS BARS IS SILENT AND LOOKS LIKE GOOD NEWS. If the token here drifts from
    #   `funnel_meter.QGIS_PLUGIN_UA`, every call from every install is tagged `other` — which on
    #   the traffic read is indistinguishable from nobody having installed the plugin at all, and
    #   would be read as a reason to kill it.
    print("\n-- the product token: what we send, what we claim, what the door matches")
    _here = os.path.dirname(os.path.abspath(__file__))
    _mv = ""
    for _line in io.open(os.path.join(_here, "metadata.txt"), encoding="utf-8").read().splitlines():
        if _line.startswith("version="):
            _mv = _line.split("=", 1)[1].strip()
            break
    bar("the User-Agent's version EQUALS metadata.txt's version (0.1.1 shipped with a 0.1.0 tag)",
        bool(_mv) and client.USER_AGENT.endswith("/" + _mv),
        "%s vs metadata %s" % (client.USER_AGENT, _mv or "(none)"))
    # ════════════════════════════════════════════════════════════════════════════════════════
    # ⛔⛔ AN ABSENT `qgisMaximumVersion` IS A CEILING, NOT THE ABSENCE OF ONE
    # ════════════════════════════════════════════════════════════════════════════════════════
    # QGIS substitutes the MINIMUM's major version plus ".99" when the maximum is missing, so
    # `qgisMinimumVersion=3.22` on its own declares 3.22–3.99 and a QGIS 4 desktop refuses the
    # plugin outright — measured 2026-09-17 against a real 4.2.2 install, which wrote
    # `passage_species_status=false` into its own profile. Every bar in this repo runs the code
    # through PyQGIS, which never consults the plugin registry, so nothing here could see it.
    _mn = _mx = ""
    for _line in io.open(os.path.join(_here, "metadata.txt"), encoding="utf-8").read().splitlines():
        if _line.startswith("qgisMinimumVersion="):
            _mn = _line.split("=", 1)[1].strip()
        if _line.startswith("qgisMaximumVersion="):
            _mx = _line.split("=", 1)[1].strip()

    def _v(text):
        parts = (text or "0").split(".")
        return tuple(int(p) if p.isdigit() else 0 for p in (parts + ["0", "0"])[:3])

    _RUN_ON = ("3.22.9", "3.44.14", "4.2.2")          # the three builds this repo measures on
    bar("⛔⛔ THE DECLARED RANGE COVERS EVERY BUILD THIS REPO RUNS ON. An absent "
        "`qgisMaximumVersion` is not « no ceiling » — QGIS reads it as the minimum's major "
        "version plus .99, which locked this plugin out of QGIS 4 entirely",
        bool(_mx) and all(_v(_mn) <= _v(b) <= _v(_mx) for b in _RUN_ON),
        "declares %s–%s; runs green on %s" % (_mn or "(none)", _mx or "(none)",
                                                ", ".join(_RUN_ON)))
    bar("⛔ MUST-FAIL CONTROL: the ceiling QGIS would have INVENTED does not cover 4.2.2 — "
        "this is the defect, stated as a number",
        not (_v(_mn) <= _v("4.2.2") <= _v("%s.99" % _mn.split(".")[0])),
        "invented ceiling would have been %s.99" % _mn.split(".")[0])
    bar("the User-Agent is one token and one version — no OS, no QGIS build, no host name",
        client.USER_AGENT.count("/") == 1 and " " not in client.USER_AGENT
        and "(" not in client.USER_AGENT, client.USER_AGENT)

    # ⛔ THE DOOR'S SIDE, READ FROM THE DOOR'S OWN FILE. Skipped — LOUDLY — outside the repo,
    #   because this file also ships inside the plugin zip, where `modal_training/` does not exist.
    _door = os.path.join(_here, "..", "..", "modal_training")
    if os.path.exists(os.path.join(_door, "funnel_meter.py")):
        sys.path.insert(0, os.path.abspath(_door))
        import funnel_meter                                          # noqa: E402
        bar("⛔⛔ the door's `QGIS_PLUGIN_UA` PREFIX-MATCHES what we actually send — a rename on "
            "one side alone tags every install `other`, which reads as nobody using it",
            funnel_meter.client_of(client.USER_AGENT) == "qgis_plugin",
            "%s → %s" % (funnel_meter.QGIS_PLUGIN_UA, funnel_meter.client_of(client.USER_AGENT)))
        bar("★★ the door tags the SUITE's token apart from the product's — without this, "
            "`client.qgis_plugin` counts our own bars and « is anyone running it » has no answer",
            funnel_meter.client_of(client.SELFTEST_USER_AGENT) == "selftest",
            "%s → %s" % (client.SELFTEST_USER_AGENT,
                          funnel_meter.client_of(client.SELFTEST_USER_AGENT)))
        bar("⛔⛔ MUST-FAIL: NEITHER TOKEN IS A PREFIX OF THE OTHER. The door prefix-matches, so "
            "one containing the other would put every suite call back into the product's count",
            not client.SELFTEST_USER_AGENT.startswith(funnel_meter.QGIS_PLUGIN_UA)
            and not client.USER_AGENT.startswith(funnel_meter.SELFTEST_UA),
            "%s | %s" % (funnel_meter.QGIS_PLUGIN_UA, funnel_meter.SELFTEST_UA))
        bar("⛔ …and the suite's tag is a counter the closed vocabulary already holds",
            (funnel_meter.CLIENT_PREFIX + "selftest") in funnel_meter.COUNTERS)
        bar("⛔ MUST-FAIL CONTROL: the door does NOT tag an ordinary caller as this plugin",
            funnel_meter.client_of("python-urllib/3.12") == "other"
            and funnel_meter.client_of("") == "other")
        bar("…and the tag it returns is a counter the closed vocabulary already holds",
            (funnel_meter.CLIENT_PREFIX
             + funnel_meter.client_of(client.USER_AGENT)) in funnel_meter.COUNTERS)
    else:                                                            # pragma: no cover
        print("  ⚠    the door's funnel_meter.py is not beside this checkout — the token bar was "
              "NOT run, and that is an absence, not a pass")

    # ════════════════════════════════════════════════════════════════════════════════════════
    # ⛔⛔ THE FRONT PAGE COUNTED THE LAWS, AND THE COUNT WAS FOUR SHORT
    # ════════════════════════════════════════════════════════════════════════════════════════
    # The README read "Ten laws in force", named five provinces of eleven, and counted the two
    # CONVENTIONS among the laws — on the page that becomes the plugin's public front page.
    # ⚠ `tools/ledger.py`'s surface check could not have caught it: that guard reads DIGITS, and
    #   this claim was spelled as a word. Same derivation, different reader.
    print("\n-- the README's count of laws, against the registers the repo actually holds")
    _WORDS = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven",
              8: "Eight", 9: "Nine", 10: "Ten", 11: "Eleven", 12: "Twelve", 13: "Thirteen",
              14: "Fourteen", 15: "Fifteen", 16: "Sixteen", 17: "Seventeen", 18: "Eighteen",
              19: "Nineteen", 20: "Twenty"}
    _tools = os.path.join(_here, "..", "..", "tools")
    _readme = os.path.join(_here, "README.md")
    if os.path.exists(os.path.join(_tools, "ledger.py")) and os.path.exists(_readme):
        sys.path.insert(0, os.path.abspath(_tools))
        import ledger                                                # noqa: E402
        _n_ca = ledger.laws_in_force("CA")[0]
        _text = io.open(_readme, encoding="utf-8").read()
        _want = "**%s laws in force in Canada**" % _WORDS.get(_n_ca, _n_ca)
        bar("⛔⛔ the README's LAW COUNT equals the registers we hold — it said « Ten » while "
            "the repo held fourteen, and counted the two conventions among them",
            _want in _text, "%s ← derived %d" % (_want, _n_ca))
        bar("⛔ MUST-FAIL CONTROL: the count the page used to carry is NOT still on it",
            "**Ten laws in force**" not in _text and "259 of 860" not in _text)
        bar("⛔ …and the conventions are named as conventions on that page, not as laws",
            # ⚠ EACH PROBE WITHIN ONE LINE. The README wraps at 100 columns, so a substring
            #   spanning its line break fails against a page that says exactly the right thing.
            "**The CITES and CMS Appendices, as conventions**" in _text
            and "another jurisdiction's Act." in _text)
    else:                                                            # pragma: no cover
        print("  ⚠    `tools/ledger.py` is not beside this checkout — the README's law count was "
              "NOT graded, and that is an absence, not a pass")

    if "--live" in sys.argv:
        print("\n-- one real call at the live door")
        # ⛔⛔ THE BARS DO NOT COUNT AS THE PRODUCT. Every live call below goes out under the
        #   SUITE's token, so `client.qgis_plugin` counts installs and this counts us. Swapped
        #   here rather than at the top of the file because the bars above read the real
        #   `USER_AGENT` and must go on reading it.
        _real_ua = client.USER_AGENT
        client.USER_AGENT = client.SELFTEST_USER_AGENT
        try:
            a = client.screen([("Myotis lucifugus", 45.50, -73.57), ("Acer saccharum", 45.52, -73.60)])
        except client.ScreenError as e:
            bar("the live door answered", False, str(e))
        else:
            bar("the live door answered with names", bool(a.get("names")))
            bar("…and with the register cards this plugin needs for its labels",
                len(a.get("register_cards") or []) >= 10, len(a.get("register_cards") or []))
            got = client.columns_for(a["names"][0], a.get("register_cards") or [], "2026-09-17")
            bar("…and the first name's `pd_law` names a real instrument",
                "Act" in got["pd_law"] or "Loi" in got["pd_law"], got["pd_law"][:90])
        finally:
            client.USER_AGENT = _real_ua

    print("\n%s" % ("ALL GREEN" if not FAILED else "RED: %d\n  %s" % (len(FAILED), "\n  ".join(FAILED))))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
