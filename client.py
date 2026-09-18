# -*- coding: utf-8 -*-
"""client.py — the one call this plugin makes, and the shape it hands back.

⛔ NOTHING HERE DECIDES A STATUS. The door screens against the registers and returns the
   instrument, the edition and whether it is in force where the records are; this file carries
   bytes and reshapes them. A status written by the plugin would be a status nobody can cite.
⛔ NO THIRD-PARTY IMPORTS. The QGIS plugin guidelines discourage external dependencies, and a
   plugin that needs `pip install` is a plugin most people cannot run.
"""
import json
import time
import urllib.error
import urllib.request
import uuid

ENDPOINT = "https://kedu21-beep--fieldscope-sniff-api-web.modal.run/names"
TIMEOUT_S = 300
# ★★★★ THE PRODUCT TOKEN IS HOW THE DOOR CAN TELL A PLUGIN CALL FROM ANY OTHER CALL, and until
#   2026-09-17 nothing on the other end read it — so "is anyone running this" had no answer and
#   every go/no-go number written about this plugin was unfalsifiable.
# ⛔ THE VERSION HERE WAS 0.1.0 WHILE `metadata.txt` SAID 0.1.1, and nothing noticed because
#   nothing read either. `client_selftest` now bars the two against each other.
# ⛔ THE TOKEN ITSELF MAY NOT DRIFT: `funnel_meter.QGIS_PLUGIN_UA` prefix-matches it at the door,
#   and a rename here without one there silently reclassifies every install as `other` — which
#   looks exactly like nobody using the plugin. Barred in `client_selftest` against that file.
# ⛔ NOTHING ABOUT THE MACHINE RIDES HERE. `urllib` would otherwise send `Python-urllib/3.x`; a
#   token of ours replaces it rather than appending to it, and no QGIS build, OS or host is added.
USER_AGENT = "passage-data-qgis-protected-species-check/0.1.10"

# ⛔⛔ WHAT THE BARS SEND, SO THAT THE PRODUCT'S NUMBER IS THE PRODUCT'S. Both suites screen
#   against the LIVE door — that is the point of them — and until 2026-09-17 they did it under
#   the product token, so `client.qgis_plugin` counted our own runs and "is anyone using this"
#   had no honest answer. `funnel_meter.SELFTEST_UA` tags these apart, on the same argument the
#   deploy probe already had: our own hand is counted so that it can be subtracted.
# ⛔ IT IS NOT A PREFIX OF THE PRODUCT TOKEN, AND THE PRODUCT TOKEN IS NOT A PREFIX OF IT —
#   the door prefix-matches, so either would put the suites straight back into the product's
#   count. Barred in `client_selftest`, against `funnel_meter` itself.
SELFTEST_USER_AGENT = "passage-data-qgis-selftest/0.1.10"

# ⛔⛔ MEASURED, NOT GUESSED (2026-09-17, live door): 100 / 400 / 900 / 2,000 / 5,000 distinct
#   names all returned whole, `not_screened: 0`, the slowest pass 34.6 s. The first cut of this
#   plugin capped at 400 out of caution and would have refused the one thing the people asking
#   for this actually asked for — GBIF's own forum: "hitting the API for a single species at a
#   time is very time-consuming for lists with 100s to 1000s of species". A cap below what the
#   door can do is a refusal we invented.
#   The timeout carries ~9x headroom over the slowest measured pass, for a cold container.
MAX_NAMES = 5000

# ⛔ THREE TRIES, NOT MORE. Two cover a cold start; a third covers a container dying mid-scale.
#   Past that the service is down, and a plugin that hangs for a minute pretending otherwise is
#   lying to the person waiting.
RETRIES = 3
RETRY_WAIT_S = 3


class ScreenError(Exception):
    """A call that could not be made, or an answer that was not an answer."""


def _multipart(fields, files):
    """→ (body, content_type). Hand-rolled because `requests` is not available in QGIS."""
    boundary = "----PassageData%s" % uuid.uuid4().hex
    out = []
    for name, value in fields.items():
        if value is None:
            continue
        out.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                    % (boundary, name, value)).encode("utf-8"))
    for name, (filename, data, ctype) in files.items():
        out.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                    "Content-Type: %s\r\n\r\n" % (boundary, name, filename, ctype)).encode("utf-8"))
        out.append(data)
        out.append(b"\r\n")
    out.append(("--%s--\r\n" % boundary).encode("utf-8"))
    return b"".join(out), "multipart/form-data; boundary=%s" % boundary


def csv_name(name):
    """→ the name AS WE SEND IT. ⛔ ONE SANITISER, because two callers compare its output.

    A double quote would open a quoted field and a comma would open a fourth column, so both are
    rewritten — which means the string the door answers about is not always the string the
    layer holds, and anything matching one against the other has to fold the same way.
    `unanswered` is that second caller, and it was an inline copy of this line until it existed.
    """
    return str(name).replace('"', "'").replace(",", " ").replace("\n", " ").strip()


def build_csv(rows):
    """→ the bytes we send. `rows` is [(name, lat, lon)] with lat/lon None when unknown.

    ⛔ THE COORDINATES ARE WHY THE JURISDICTION CAN BE ESTABLISHED AT ALL. The door reads the
      place from the file's own coordinates; without them every register comes back
      "not established" and the answer is about the taxon, not about where you are.
    """
    head = "scientificName,decimalLatitude,decimalLongitude\n"
    body = []
    for name, lat, lon in rows:
        safe = csv_name(name)
        if lat is None or lon is None:
            body.append("%s,,\n" % safe)
        else:
            body.append("%s,%.6f,%.6f\n" % (safe, lat, lon))
    return (head + "".join(body)).encode("utf-8")


def screen(rows, province=None, endpoint=None, timeout=None):
    """→ the door's answer as a dict. Raises `ScreenError` with a sentence a person can read.

    `province` is an ISO code or a name the depositor chose; it rides as the whole-file constant
    the door already takes, and is only needed when the layer carries no coordinates.

    ⛔⛔ `endpoint` AND `timeout` RESOLVE AT CALL TIME, NOT AT IMPORT. They were written as
      `endpoint=ENDPOINT` — a default evaluated once when this module is first imported — so
      setting `client.ENDPOINT` afterwards changed NOTHING and every call still went to the
      live door. Measured 2026-09-17: a bar that pointed `ENDPOINT` at a dead host to grade the
      offline path got a real screening answer back and graded THAT.
      The failure that matters is not the test's. `ScreenTask` calls `screen(rows, province=…)`
      with no endpoint, so a module constant that cannot actually be repointed is a constant
      that lies about being one — and the offline path stays ungradeable for as long as it does.
    """
    endpoint = endpoint or ENDPOINT
    timeout = TIMEOUT_S if timeout is None else timeout
    if not rows:
        raise ScreenError("No names were found in that field.")
    fields = {}
    if province:
        fields["constants"] = json.dumps({"stateProvince": province})
    body, ctype = _multipart(fields, {"file": ("layer_names.csv", build_csv(rows), "text/csv")})
    raw = None
    last = ""
    # ⛔⛔ A COLD CONTAINER 500s, AND THE FIRST CLICK IS THE ONE THAT MATTERS. Measured under QGIS
    #   4.2.2 on 2026-09-17: the identical call returned 500, then succeeded unretried moments
    #   later. The service scales to zero, so the first request after a quiet period pays a cold
    #   start and can fail. A stranger who installs this plugin, clicks Check and is told "the
    #   service answered 500" uninstalls it; they do not click twice.
    # ⛔ ONLY 5xx AND ONLY THE TRANSPORT ARE RETRIED. A 4xx is the door REFUSING — a bad column, a
    #   file it will not read — and retrying a refusal would turn one honest answer into three
    #   identical ones and a longer wait.
    for attempt in range(RETRIES):
        req = urllib.request.Request(endpoint, data=body,
                                     headers={"Content-Type": ctype, "User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            break
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = "  ".join(json.loads(e.read().decode("utf-8")).get("refusals") or [])
            except Exception:                                        # noqa: BLE001
                pass
            if e.code < 500 or attempt == RETRIES - 1:
                raise ScreenError("The screening service answered %s. %s" % (e.code, detail[:400]))
            last = "HTTP %s" % e.code
        except urllib.error.URLError as e:
            if attempt == RETRIES - 1:
                raise ScreenError("Could not reach the screening service (%s). This plugin needs "
                                  "an internet connection." % (getattr(e, "reason", e),))
            last = str(getattr(e, "reason", e))
        time.sleep(RETRY_WAIT_S * (attempt + 1))                     # the second wait is longer
    if raw is None:                                                  # pragma: no cover
        raise ScreenError("The screening service did not answer (%s)." % last)
    try:
        answer = json.loads(raw.decode("utf-8"))
    except ValueError:
        raise ScreenError("The screening service sent something that was not an answer.")
    if not answer.get("ok"):
        why = "  ".join(answer.get("refusals") or []) or "no reason was given"
        raise ScreenError("The screening service refused this layer: %s" % why[:400])
    return answer


# ═════════════════════════════════════════════════════════════════════════════════════════
# ★★★★ WHICH COLUMN HOLDS THE NAME — MEASURED ON THREE REAL LAYERS, WHICH IT MISSED ALL THREE
# ══════════════════════════════════════════════════════════════════════════════════════════
#: Known spellings, case-FOLDED. The list this replaced compared case-sensitively and held
#: `SCIENTIFIC` and `NOM_LATIN`; the three real layers in `reports/corpus/` carry `scientific`,
#: `NOM_SCIEN` and `BOTANICAL_`, so it matched none of them — measured 2026-09-17.
NAME_FIELD_WANTS = (
    "scientificname", "scientific_name", "scientific", "sci_name", "sciname", "scientifique",
    "nom_scientifique", "nom_scien", "nomscientifique", "nom_latin", "nomlatin",
    "taxonname", "taxon_name", "taxon", "binomial", "latin_name", "latinname",
    "botanical_name", "botanicalname", "botanical", "espece_scientifique", "species_name",
    "speciesname", "acceptedname", "verbatimscientificname",
)
#: A column whose name CONTAINS one of these. Second chance, because a real dBASE name is
#: truncated to 10 characters (`BOTANICAL_`) and a real database name carries a prefix.
NAME_FIELD_HINTS = ("scientif", "botanic", "binomial", "taxon", "nom_scien", "nom_latin")


def _words(fold):
    """→ the alphanumeric words of a folded field name. `BOTANICAL_` is one; an Irish employment
    statistic is ten, and that is the whole difference between a column name and a sentence."""
    out, cur = [], ""
    for ch in fold:
        if ch.isalnum():
            cur += ch
        elif cur:
            out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return out


#: ⛔ A COLUMN WHOSE NAME ENDS THIS WAY IS AN IDENTIFIER, WHATEVER ELSE IT CONTAINS. Measured
#: across all 730 corpus layers: `TaxonID` was recommended on four of them, because the hint
#: `taxon` matches an identifier exactly as happily as it matches a name.
IDENTIFIER_TAILS = ("id", "key", "code")


def _is_identifier(fold):
    """→ True when this column NAME reads as an identifier rather than a name."""
    words = _words(fold)
    return bool(words) and (words[-1] in ("id", "fid", "gid", "oid", "uid", "no", "nr", "num")
                            or fold.endswith(IDENTIFIER_TAILS))


def _mostly_numbers(values):
    """→ True when the sampled values are overwhelmingly numeric — a name never is.

    ⛔ THE VALUES ARE THE ONLY THING THAT CATCHES `taxonid_left`, whose name gives nothing away
      and whose contents are `100, 130, 150, 160…`. An EMPTY sample decides nothing: a column
      nobody filled is not thereby an identifier, and the panel already says when a field holds
      no values at all.
    """
    seen = [str(v).strip() for v in (values or ()) if str(v or "").strip()]
    if not seen:
        return False
    n_num = 0
    for v in seen:
        try:
            float(v.replace(",", ""))
            n_num += 1
        except ValueError:
            pass
    return n_num >= 0.8 * len(seen)


def guess_name_field(fields, values_for=None):
    """→ (the field that most likely holds a binomial or None, a sentence for the person).

    ⛔⛔ THE DEFAULT IT REPLACED LANDED ON THE COMMON-NAME COLUMN. A `QComboBox` opens on index
      0, so a layer whose scientific-name column was not recognised left the person on whatever
      column happened to be first — and on the bird atlas that is `common_nam`, the one column
      the door refuses outright. "Nothing was recognised" must not look like "this one".
    ⛔ `species` IS NOT A NAME WHEN A `genus` COLUMN SITS BESIDE IT. The ACT tree register's
      `SPECIES` holds `mannifera`; the binomial is `GENUS || ' ' || SPECIES`, in 290 of its 298
      rows, while its `BOTANICAL_` column is filled in 7. An epithet screened as a name matches
      nothing and reads as a clean layer, so the pair is NAMED to the person instead.
    ⚠ `values_for(field) → [value]` IS OPTIONAL AND THE CALLER SUPPLIES IT. Without it the guess
      is made on column names alone, which is all a caller holding no layer can do; with it, a
      candidate whose contents are numbers is passed over. The dialog always supplies it.
    """
    by_fold = {}
    for f in fields or ():
        by_fold.setdefault(str(f).strip().lower(), f)
    genus = by_fold.get("genus") or by_fold.get("genre")
    epithet = (by_fold.get("species") or by_fold.get("specificepithet")
               or by_fold.get("specific_epithet") or by_fold.get("epithet"))
    advice = ""
    if genus and epithet:
        advice = (u"This layer splits the name across “%s” and “%s” — neither column holds a "
                  u"binomial on its own. Build one with the field calculator (%s || ' ' || %s) "
                  u"and screen that field." % (genus, epithet, genus, epithet))
    def rejected(fold, original):
        """→ True when this candidate is an identifier by name, or a number column by content."""
        if _is_identifier(fold):
            return True
        return values_for is not None and _mostly_numbers(values_for(original))

    for want in NAME_FIELD_WANTS:
        if want in by_fold and not rejected(want, by_fold[want]):
            return by_fold[want], advice
    for fold, original in by_fold.items():
        # ⛔⛔ A HINT MAY MATCH A COLUMN NAME, NEVER A SENTENCE. Measured 2026-09-17 against a
        #   random corpus file: `Dublin Employment ('000) - Professional, scientific and technical
        #   activities (M)` contains "scientif", and a plugin that recommends a column of
        #   employment statistics has made its recommendation worth nothing. A real name column
        #   is one to three words — `BOTANICAL_`, `nom scientifique`, `Scientific name (accepted)`.
        # ⛔ AND THIS FREE TEST COMES FIRST. `rejected()` reads the column, which on a sparse one
        #   is a full scan; asking it about every column of every layer before asking whether the
        #   NAME is even plausible cost thirty scans to learn nothing, measured on the corpus
        #   sweep. A candidate is only worth opening once its name has earned it.
        if len(_words(fold)) <= 3 and any(h in fold for h in NAME_FIELD_HINTS) \
                and not rejected(fold, original):
            return original, advice
    if epithet and not genus and not rejected(str(epithet).strip().lower(), epithet):
        return epithet, advice                       # a lone `species` column usually IS the name
    return None, advice or (u"No column here looks like it holds a scientific name. Choose the "
                            u"one that does — one binomial per feature.")


# ── RESHAPING THE ANSWER INTO COLUMNS ────────────────────────────────────────────────────────
# ⛔ SHAPEFILE TRUNCATES A FIELD NAME AT 10 CHARACTERS. Every name below is already within it, so
#   the columns a shapefile gets are the columns this plugin promised.
COLUMNS = [
    # ⛔⛔ THE SEVENTH INSTANCE, AND IT WAS THIS LABEL. It read "the laws in force here that
    #   list this taxon" — a reach claim, on a cell whose reach `pd_applies` may report as
    #   `not established`. Measured 2026-09-17 on the live door, a placeless file: *Myotis
    #   lucifugus* filled `pd_law` with TWELVE acts across twelve jurisdictions — SARA, the
    #   LEMV, Ontario, New Brunswick, Alberta, Manitoba, Nova Scotia, Newfoundland, the
    #   Northwest Territories and three United Kingdom instruments — beside `pd_applies: not
    #   established`. "In force here" was false for at least eleven of the twelve, and the
    #   column beside it said so. A LABEL IS READ BEFORE THE CELL AND INSTEAD OF IT.
    ("pd_law", "the laws we hold that list this taxon, with the status each carries — "
               "`pd_applies` says whether they reach these records"),
    # ⛔ FOUR VALUES, NOT THREE, AND THE FOURTH IS THE ONE THAT MATTERS. `yes (qualified)` means
    #   every law that reaches you names this taxon ONLY under a population or subspecies your
    #   layer does not state. It is a QUESTION, and collapsing it into `yes` asserts a status the
    #   register never gave. `yes%` still selects everything positive, so a filter written against
    #   the old three values does not silently start missing rows.
    # ⛔ SIX VALUES. `not established` (the layer states no place), `not covered` (we
    #   hold no register for where these records are) and `not checked` (this name was never
    #   put to a register) were ALL one empty cell until 0.1.5 — and so was a taxon we
    #   screened and cleared. Four findings, one blank, in the column a consultant filters on.
    ("pd_applies", "yes · yes (qualified) · no · not established · not covered · not checked"),
    # ⛔ NOT "assessments". Ontario's Act naming a taxon is a LAW; it is simply not the law where
    #   these records are. Calling it an assessment is the same error the engine was just fixed
    #   for, one layer up.
    ("pd_other", "the conventions (in force wherever you are, but they do not lead), other "
                 "jurisdictions' Acts, and the assessments"),
    ("pd_conflic", "where the COSEWIC assessment is not the status Schedule 1 carries"),
    ("pd_match", "what the GBIF backbone answered about the name"),
    ("pd_check", "the date screened, and the edition of each instrument cited"),
]


def _kind(cards, register):
    """→ "law" · "convention" · "assessment" · None, from the register's OWN card.

    ⛔ A CONVENTION IS NOT A FOREIGN ACT. CITES and CMS are legal instruments whose
      jurisdiction is GLOBAL: the engine keeps them out of `applies` because a convention never
      LEADS a headline (`law_tally`), not because they stop at a border. Rendering that
      `applies: False` as "not law where these records are" told a reader the CITES Appendices do
      not reach Quebec — measured 2026-09-17 in the dialog's own output, and it is the same
      error as calling Ontario's Act an assessment, one layer up.
    """
    for c in cards or ():
        if c.get("register") == register:
            if c.get("legal_instrument") is False:
                return "assessment"
            return "convention" if str(c.get("jurisdiction") or "").upper() == "GLOBAL" else "law"
    return None


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ★★★★ ONE SORTER — AND IT IS THE FIX FOR THE DEFECT CLASS, NOT FOR THE FIFTH DEFECT
# ══════════════════════════════════════════════════════════════════════════════════════════════
def sort_designations(name, cards):
    """→ {"law", "elsewhere", "convention", "assessment", "assessed"} → [designation]

    ⛔⛔ THE DEFECT WAS NEVER A DEFECT. IT WAS A SECOND COPY OF THIS RULE. Telling a law, a
      convention and an assessment apart had been written out by hand in `columns_for` and AGAIN
      in the dialog's `_report`. The fourth instance was fixed in the first on 2026-09-17 and
      stayed live in the second, where a reader meets it FIRST: measured the same day against the
      live door on a Philippine layer, the panel printed

          LISTED
            Panthera tigris
                The IUCN Red List of Threatened Species — Endangered  [law in force here]

      directly beneath the door's own headline "no law we hold applies to them". The Red List is
      not law, the panel said it was, and the panel contradicted the headline three lines up.
      Two renderings of one rule is how this class survives its own fix. There is one rule here
      now, and both callers read it.
    ⛔ `applies` SORTS NOTHING UNTIL THE KIND IS KNOWN. A convention is in force wherever you are
      and simply never leads a jurisdiction's headline, so the door marks CITES `applies: False`
      on a Quebec file and `applies: True` on a Philippine one — both measured 2026-09-17.
      Reading that flag before the card is exactly what put the Red List in `pd_law`.
    ⚠ `assessed` STAYS ITS OWN BUCKET because it is not a listing: it is the door reporting which
      registers were consulted and what they say. It is sorted by the same cards at the point of
      use, so an entry whose card says "law" can never be captioned "an assessment".
    """
    out = {"law": [], "elsewhere": [], "convention": [], "assessment": [], "assessed": []}
    for d in name.get("designations") or ():
        kind = _kind(cards, d.get("register"))
        if kind == "assessment":
            out["assessment"].append(d)
        elif kind == "convention":
            out["convention"].append(d)
        elif d.get("applies") is False:
            out["elsewhere"].append(d)
        else:
            out["law"].append(d)                      # applies True, or place not established
    for a in name.get("assessed") or ():
        if a.get("status"):
            out["assessed"].append(a)
    return out


def kind_says(cards, register):
    """→ the phrase naming WHAT an instrument is, for a line the door did not mark `applies`.

    ⛔ THE DEFAULT IS THE DOOR'S OWN BUCKET NAME, and it is only overridden by a card that
      disagrees with it. An entry the door put under `assessed` whose card says `legal_instrument`
      is a LAW must not be captioned "an assessment, not a law" — that is the same conflation
      this file exists to stop, arriving from the other direction.
    """
    return {"convention": "a convention — in force wherever you are",
            "law": "a law — we did not establish that it is in force here",
            }.get(_kind(cards, register), "an assessment, not a law")


def _label(cards, register):
    """→ the register's own instrument name, or its id when the door sent no card for it."""
    for c in cards or ():
        if c.get("register") == register:
            return (c.get("instrument") or c.get("title") or register)
    return register


def _edition(cards, register):
    for c in cards or ():
        if c.get("register") == register:
            return c.get("edition")
    return None


def _qualification(d):
    """→ the clause that marks a QUALIFIED listing, or "" when the listing is settled.

    ⛔⛔ A QUALIFIED LISTING IS A QUESTION, NEVER A FINDING — AND NEVER AN ABSENCE. Both readings
      are wrong and both have happened. Reading it as an absence once told a reader the fin whale
      is not protected federally. Reading it as a FINDING is what this function exists to stop:
      measured 2026-09-17 against Quebec's own caribou range layer, the plugin wrote
      `ca_sara: Threatened Species` and `pd_applies: yes` into a shapefile — while SARA Schedule 1
      names this taxon only under the *Southern Mountain* and *Northern Mountain* populations, and
      the layer is the *Gaspesie* population, which SARA carries separately and as ENDANGERED.
      The cell asserted a status for a population the register had not named, in a file a
      consultant would hand to a regulator.
    ⚠ THE POPULATIONS ARE NAMED, NOT COUNTED. "Qualified" alone sends the reader back to the Act;
      the population names are what let them settle it themselves in one look."""
    if not str(d.get("outcome") or "").endswith("_qualified"):
        return ""
    only = [str(x).strip() for x in (d.get("only") or ()) if str(x or "").strip()]
    if not only:
        return " — QUALIFIED: named only under a population or subspecies your layer does not state"
    return " — QUALIFIED, a question not a finding: named only under %s" % _short("; ".join(only), 96)


def piece(cards, d):
    """→ "«the instrument's own name»: «status»«the qualification, when there is one»".

    ⛔ ONE SPELLING OF A DESIGNATION, for the same reason there is one sorter: the panel and the
      attribute cell disagreeing about what an instrument said is a defect nobody can see.
    """
    return "%s: %s%s" % (_label(cards, d.get("register")), d.get("status") or "listed",
                         _qualification(d))


def _short(text, n=72):
    text = str(text or "")
    return text if len(text) <= n else text[:n - 1] + "…"


def _join(pieces, cap=254):
    """→ as many WHOLE pieces as fit, then how many were left.

    ⛔ AN INSTRUMENT NAME IS NEVER CUT IN HALF. `O. Reg. 60/26` truncated to `O. Reg. 60/…` has
      lost the regulation number, which is the part a reader would go and check — a mangled
      citation is worse than an absent one. A piece is carried whole or it is counted.
    """
    out, used = [], 0
    for i, p in enumerate(pieces):
        add = len(p) + (2 if out else 0)
        tail = "" if i == len(pieces) - 1 else "; +%d more" % (len(pieces) - i - 1)
        if used + add + len(tail) > cap:
            if out:
                out.append("+%d more" % (len(pieces) - i))
            return "; ".join(out)
        out.append(p)
        used += add
    return "; ".join(out)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ★★★★ WHERE WE HOLD NOTHING — the difference between "no law lists you" and "we hold no law"
# ══════════════════════════════════════════════════════════════════════════════════════════════
def uncovered_places(coverage):
    """→ the jurisdictions IN THIS FILE that no register we hold reaches, by name.

    ⛔ `in_this_file` IS THE WHOLE TEST. `coverage.not_covered` also names jurisdictions we hold
      no register for that are nowhere near the layer — Nunavut and Prince Edward Island come back
      on a Quebec file, measured 2026-09-17 — and reading those as this file's would tell a Quebec
      user their own records are outside our coverage.
    """
    out = []
    for p in (coverage or {}).get("not_covered") or ():
        if p.get("in_this_file") and (p.get("name") or p.get("jurisdiction")):
            out.append(str(p.get("name") or p.get("jurisdiction")))
    return out


def wholly_uncovered(coverage):
    """→ those jurisdictions IF they are every place in the file, else [].

    ⛔⛔ A NAME CARRIES NO PLACE OF ITS OWN — MEASURED, NOT ASSUMED. The door answers per NAME
      (`value`, `designations`, `assessed`, `hit`…) and a name's row is the whole file's answer
      for that taxon; there is no per-record jurisdiction in it to read. So a file that straddles
      a covered place and an uncovered one CANNOT have the two told apart in one cell, and this
      is all-or-nothing on purpose: the cell may say "not covered" only when every place in the
      file is one we hold nothing for. A straddling file falls back to `no`, which is the weaker
      claim, and the panel still names the uncovered jurisdictions in full.
    """
    out = uncovered_places(coverage)
    if not out:
        return []
    missing = {str(p.get("jurisdiction") or "") for p in (coverage or {}).get("not_covered") or ()
               if p.get("in_this_file")}
    places = [str(p) for p in ((coverage or {}).get("places") or ())]
    if [p for p in places if p not in missing]:
        return []                                    # part of this file IS covered — say `no`
    return out



# ══════════════════════════════════════════════════════════════════════════════════════════
# ★★★★ A NAME WE SENT AND GOT NO ROW FOR — THE OFF-BY-ONE NOBODY COULD EXPLAIN
# ══════════════════════════════════════════════════════════════════════════════════════════
def unanswered(sent, answer):
    """→ the names we PUT ON THE WIRE that came back with no row of their own.

    ⛔⛔ MEASURED, ON A REAL FILE, 2026-09-17. Belfast's street-tree register holds 189 distinct
      values under `SPECIES`; the panel said "189 of them carry no usable geometry" and the door
      answered about 188 names, with `not_screened: 0`. The 189th is the literal string `N/A`,
      which the service reads as a null marker and removes — correctly, it is not a name — but it
      left the answer with one fewer row than the question had, and nothing anywhere said so. A
      reader counting the panel against their own column finds a number that does not reconcile
      and no sentence to explain it.
    ⚠ `not_screened` DOES NOT COVER THIS. That counter is the budget's (#529) and read 0 on the
      same run: a name the door never accepted as a name was never in its denominator.
    ⛔ THE COMPARISON IS ON THE SANITISED FORM, because that is what we sent. Belfast also holds
      `Taxus baccata "Fastigiata"`, which reaches the door as `Taxus baccata 'Fastigiata'` and
      comes back spelled that way — the same name, and comparing raw layer values would report
      two false drops for every one real one.
    """
    answered = {str(n.get("value") or "").strip() for n in (answer or {}).get("names") or ()}
    out = []
    for v in sent or ():
        name = csv_name(v)
        if name and name not in answered and v not in answered:
            out.append(v)
    return out

def unchecked_says(name):
    """→ why this name was NOT screened, or "" when it was.

    ⛔⛔ "WE FOUND NOTHING" AND "WE DID NOT LOOK" ARE DIFFERENT ANSWERS AND THEY HAD THE SAME
      CELL. A name the GBIF backbone did not match is never put to a register — the registers are
      keyed on accepted names — so it came back with no designations, and `pd_applies` was blank
      for exactly the same reason a screened-and-clean species was blank. A reader filtering a
      shapefile saw an empty cell in both rows. The panel has always said so under NOT MATCHED TO
      THE BACKBONE; the column a consultant actually filters on did not.
    ⛔ THE BUDGET IS THE OTHER ONE. Under a taxon budget the door can stop answering partway
      (#529); a name it never reached must not read as a name it cleared.
    """
    if name.get("budget_expired") or name.get("throttled"):
        return "not checked (the screening budget ran out before this name)"
    if name.get("answered") is False:
        return "not checked (the service did not answer for this name)"
    if not name.get("hit"):
        return "not checked (this name was not matched to the GBIF backbone)"
    return ""


def columns_for(name, cards, checked_on, coverage=None):
    """→ {column: value} for one screened name. ⛔ EVERY CELL IS THE DOOR'S OWN WORDS OR EMPTY.

    `coverage` is the answer's own `coverage` block. It is optional only so a caller holding one
    name and no answer can still render it; `screen_task.write_back` always passes it, and
    without it a layer outside our registers cannot be told from a layer we screened and cleared.
    """
    kinds = sort_designations(name, cards)
    laws, others, conventions, editions = [], [], [], []
    applies_seen = set()
    # ⛔ AT LEAST ONE LAW THAT REACHES YOU NAMES THIS TAXON OUTRIGHT. Tracked separately from
    #   `applies_seen` because a taxon can carry one settled listing and one qualified one, and
    #   the settled one is what decides whether `pd_applies` may say plain `yes`.
    settled = False
    # ══════════════════════════════════════════════════════════════════════════════════════════
    # ⛔⛔ WHAT A REGISTER *IS* DECIDES THE COLUMN. WHETHER IT *APPLIES* DECIDES NOTHING HERE.
    # ══════════════════════════════════════════════════════════════════════════════════════════
    # That is `sort_designations`' whole job, and it is the only place the three are told apart.
    # ⛔ NEITHER A CONVENTION NOR AN ASSESSMENT MAY TOUCH `pd_applies`. That cell answers *does a
    #   law reach these records*; an assessment answering it « yes » made a plain `yes` out of a
    #   listing whose only instrument was QUALIFIED.
    for d in kinds["law"]:
        applies = d.get("applies")
        applies_seen.add(applies)
        laws.append(piece(cards, d))
        if applies is True:
            if not _qualification(d):
                settled = True
            ed = _edition(cards, d.get("register"))
            if ed:
                editions.append("%s ed. %s" % (d.get("register"), ed))
    for d in kinds["elsewhere"]:
        applies_seen.add(False)
        others.append(piece(cards, d))
    for d in kinds["convention"]:
        conventions.append(piece(cards, d))          # in force wherever you are; it does not lead
    for d in kinds["assessment"]:
        others.append(piece(cards, d))
    for a in kinds["assessed"]:
        # sorted by the SAME cards — a law the door merely consulted is not an "assessment"
        k = _kind(cards, a.get("register"))
        if k == "convention":
            conventions.append(piece(cards, a))
        elif k == "law":
            applies_seen.add(None)
            laws.append(piece(cards, a))
        else:
            others.append(piece(cards, a))

    # ⛔⛔ SIX ANSWERS, AND THE THREE THAT USED TO BE ONE BLANK CELL. `pd_applies` was empty
    #   whenever no law designation came back — which covers a name nobody screened, a place we
    #   hold no register for, and a taxon we screened and cleared. Those are three different
    #   findings and a consultant filtering a shapefile could not tell them apart.
    unchecked = unchecked_says(name)
    far = wholly_uncovered(coverage)
    if unchecked:
        applies = unchecked
    elif applies_seen:
        if True in applies_seen:
            applies = "yes" if settled else "yes (qualified)"
        elif applies_seen == {None}:
            applies = "not established"
        else:
            applies = "no"
    elif far:
        # ⛔ SILENCE ABOUT THESE IS ABOUT US, NEVER ABOUT THE SPECIES. `no` here would claim we
        #   looked at the laws in force where these records are; we hold none of them.
        applies = "not covered (no register we hold reaches %s)" % _join(far, 120)
    else:
        # screened against the laws in force here, and none of them names this taxon
        applies = "no"

    conflict = name.get("conflict") or {}
    match = name.get("match") or "NONE"
    accepted = name.get("name") or name.get("accepted") or ""
    checked = checked_on + ((" · " + "; ".join(sorted(set(editions)))) if editions else "")

    return {
        "pd_law": _join(laws),
        "pd_applies": applies[:254],
        "pd_other": _join(conventions + others),
        "pd_conflic": _short(conflict.get("says") or "", 254),
        "pd_match": ("%s · %s" % (match, accepted)).strip(" ·")[:120],
        "pd_check": checked[:254],
    }
