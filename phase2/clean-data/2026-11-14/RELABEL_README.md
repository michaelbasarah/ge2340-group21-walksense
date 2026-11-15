# Relabel the original recordings

Open [RELABEL_TEMPLATE.csv](RELABEL_TEMPLATE.csv) in Excel or LibreOffice. It has **49 actual files**, sorted by actual recording start time: **26 barometer/magnetometer stops and 23 accelerometer movements**. There are no copied-proxy or Wi-Fi rows. Existing Chris labels are deliberately absent from this new sheet.

- Find a file using its original ZIP filename, stable source recording ID and WhatsApp sent time. The separate actual start/end times come from recording metadata. `BM01` or `ACC15` identifies a source file, **not a location number**.
- For each barometer/magnetometer row, fill `confirmed_stop_name` and `confirmed_floor`. Add your own stop number if useful. Give all 26 recordings a name even if several recordings were at the same physical place.
- For each accelerometer row, fill `walking_from_stop_name` and `walking_to_stop_name`; optional stop numbers can match your new list. Original P filenames stay unchanged. ACC15 is the original **P16–18** file, not P15.
- If a recording repeats a place, fill `repeat_visit_of_source_id` if known. `recording_status` can say `valid`, `repeat` or `test`; explain uncertainty in `review_notes`. Do not remove a file merely because there are 26 recordings and 25 earlier descriptions. We cannot confidently identify a redundant physical visit from similar pressure/magnetic readings alone, and none of the 26 stop ZIPs is a byte-duplicate export.
- Leaving uncertain fields blank is fine. You can also provide a filename or raw source ID with its new name directly. Map coordinates, distances and compass work can wait.

The old candidate associations remain in historical manifests for provenance; they are **untrusted and awaiting replacement**, not confirmed labels. Filling this sheet does not automatically rewrite measured data or train a model. After the fresh labels are supplied, we will reconcile recording IDs and movement endpoints, and update the copied connector's endpoint names from that confirmed mapping. The proxy has not been remapped now.

`make_relabel_template.py` created this blank sheet from `sessions.csv` (sender contact details are withheld in this team copy). It refuses to overwrite an existing template, protecting any labels you enter. `relabel_template_validation.json` records the 49/26/23 count and source-identity/timestamp checks.
