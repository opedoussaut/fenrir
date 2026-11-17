# Mechanical

| Item | State |
|---|---|
| [Enclosure A, detail rev C](enclosure-a.md) | **Chosen concept (A, Precision), detail design in progress.** Closure, tolerances, parts list, assembly; CAD checks pass; open items block release |
| [`cad/fenrir_a.py`](cad/fenrir_a.py) | Concept A detail model: geometry, checks, renders, STEP per part |
| [Enclosure concepts, rev B](enclosure-concepts.md) | **Design study, 2026-11-17.** Three concepts (Precision, Technical, Ultralight) in CAD with review sheets and clearance checks; concept A recommended; none released |
| [Enclosure rev A](enclosure.md) | Superseded look (owner rejected it); kept for comparison |
| [`cad/fenrir_enclosure.py`](cad/fenrir_enclosure.py) | Parametric model (CadQuery). Exports go to `cad/out/` (git-ignored) |
| [`cad/concepts.py`](cad/concepts.py) | Rev B concepts: geometry, CAD checks, renders, STEP export |
| `drawings/` | Renders of rev A; `drawings/concepts/` holds the rev B review sheets. No dimensioned drawing yet |
| `assembly/` | **Empty** |

Load path, ratings and safety limits:
[docs/architecture/mechanical-load-path.md](../docs/architecture/mechanical-load-path.md).

The model uses catalogue dimensions, some of them assumed. It becomes printable only after the load
cell, eye bolts and boards have been received and measured (list in [enclosure.md](enclosure.md)).
