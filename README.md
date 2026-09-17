# Protected Species Check — a QGIS plugin

**Which species in your layer are legally protected, under which law, and which edition.**

Pick a layer, pick the field holding scientific names, click Check. The plugin resolves each name
against the GBIF backbone, screens it against the registers that decide, and writes the verdict
back as six attribute columns.

## What it screens against

**Fourteen laws in force in Canada** — the federal *Species at Risk Act* Schedule 1 and the
*Migratory Birds Convention Act*; Québec's *Loi sur les espèces menacées ou vulnérables* (the fauna
and the flora regulations); and the Acts of Ontario, New Brunswick, Manitoba, Alberta, Nova Scotia,
British Columbia, Newfoundland and Labrador, Saskatchewan, the Northwest Territories and Yukon.

**The CITES and CMS Appendices, as conventions** — in force wherever you are, and never reported as
another jurisdiction's Act.

**Three assessment lists, shown as assessments and never as law** — the **IUCN Red List**,
**COSEWIC**, and the **BC Conservation Data Centre** list.

Every answer names the instrument and the edition it cites, and ends with the list of everything it
was actually checked against — so the coverage you get is the coverage the answer reports, not a
number on this page.

## The three things it does that a status column does not

**1 · It separates the law from the assessment.** COSEWIC assesses; SARA Schedule 1 lists. They are
different facts and they are frequently different words. The plugin flags every disagreement it
finds in your layer, because quoting the Committee's word as the legal status is the most common way
a report is wrong.

**2 · It only marks a law as applying where it is in force.** If your layer has coordinates, the
place comes from them, and Nova Scotia's Act is not reported as applying to a Québec record. If it
has no coordinates and you name no province, the plugin says the jurisdiction **was not
established** rather than implying that every register we hold applies to you.

**3 · It says what it could not do.** Names the backbone did not match are listed and marked as not
screened. Features whose name cell is empty are counted, so a verdict covering 7 of your 298 rows
says so. Jurisdictions we hold no register for are named. An empty result is a statement about the
registers we hold, never about your species — the *Species at Risk Act* register's own scope note
puts it plainly: *absence here is not absence of protection.*

## The columns it writes

| column | what it holds |
|---|---|
| `pd_law` | the laws in force where these records are that list this taxon, with each status |
| `pd_applies` | `yes` · `yes (qualified)` · `no` · `not established` · `not covered` · `not checked` |
| `pd_other` | registers that name it but do not lead here — other jurisdictions' Acts, the conventions, the assessments |
| `pd_conflic` | where the COSEWIC assessment is not the status Schedule 1 carries |
| `pd_match` | what the GBIF backbone answered about the name |
| `pd_check` | the date screened, and the edition of each instrument cited |

Field names are within the shapefile 10-character limit, so a shapefile gets the columns as named.

`pd_applies` is never blank. Four findings used to share one empty cell, and they are four different
answers: **`no`** (screened against the laws in force here, on none of them), **`not checked`** (this
name never reached a register — the backbone did not match it, or the screening budget ran out),
**`not covered`** (we hold no register with scope over where these records are), and **`not
established`** (the layer states no place, so which laws are in force was never settled).

## How many names

Measured on the live door 2026-09-17: **5,000 distinct names returned whole in 23.8 seconds**,
nothing dropped. 100, 400, 900 and 2,000 the same, the slowest pass 34.6 s. The plugin sends one
row per *distinct* name with that name's own mean position, so a 40,000-feature layer of 300
species is 300 rows on the wire, not 40,000.

## What it does not do

- It does not tell you whether a species is **present** at your site. It reads the names you give it.
- It does not hold occurrence data. For records near a site, ask the conservation data centre for
  your province — they hold that, we do not.
- Outside the jurisdictions whose registers we hold, you get the conventions and the assessments,
  and the answer names what it could not check.
- It does not sign anything. This is an input to work a qualified person signs, in the way a
  laboratory certificate is.

## Requirements

QGIS **3.22 or newer**, and an internet connection. The whole suite runs green on QGIS 3.22.9
(PyQt 5.15.4, GDAL 3.5.1), 3.44.14 (PyQt 5.15.13) and 4.2.2 (PyQt 6.11, GDAL 3.13.3) — the floor is
a version that was run, not one that was hoped for. The screening runs on the Passage Data service.
No account, no sign-up, and the plugin sends only the distinct scientific names and one
representative coordinate per name — never your attribute table.

## Installing

Download the `.zip` from [Releases](../../releases) and use **Plugins → Manage and Install Plugins →
Install from ZIP** in QGIS.

## Running the tests

```
py client_selftest.py            # what decides a cell — no QGIS needed
py client_selftest.py --live     # …and one real call at the service

QT_QPA_PLATFORM=offscreen <qgis-python> qgis_selftest.py            # the window, the layers, the write-back
QT_QPA_PLATFORM=offscreen <qgis-python> qgis_selftest.py --no-live  # …without touching the network
```

`qgis_selftest.py` drives the real dialog offscreen against real files, including a shapefile and a
GeoPackage of the same feature, a 65,391-feature layer, a table with no geometry, a layer whose only
name is null, and an unreachable service. Some of its bars need corpus files that are not in this
repository; those bars say so out loud rather than passing quietly.

## Licence

GPL-3.0-or-later. See `LICENSE`.
