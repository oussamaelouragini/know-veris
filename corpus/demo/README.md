# Demo corpus

Real **public** banking-regulation documents used for the demo and the final
golden set. **Not committed** — only this README is tracked (see `.gitignore`).
The binaries are collected in parallel during weeks 1–2; the pipeline does not
depend on their *content*, only their *format*, so their absence blocks nothing.

Because the corpus is public, KnowVeris is demonstrable and publishable with **no
confidentiality risk** — a deliberate argument to make at the defense.

Target: **~10–15 documents, 20–80 pages each**, covering FR / EN / AR.

## Sources

Priority is the **GAFI / FATF 40 Recommendations**, published word-for-word in
**French, English and Arabic** — the ideal cross-lingual test material.

| #  | Source                                                        | Portal                    | Lang | Notes                |
| -- | ------------------------------------------------------------- | ------------------------- | ---- | -------------------- |
| 1  | GAFI/FATF —*40 Recommendations*                            | `fatf-gafi.org`         | FR   | Cross-lingual anchor |
| 2  | GAFI/FATF —*40 Recommendations*                            | `fatf-gafi.org`         | EN   | Same content as#1    |
| 3  | GAFI/FATF —*40 Recommendations*                            | `fatf-gafi.org`         | AR   | Same content as#1    |
| 4  | GAFI/FATF — methodology / guidance                           | `fatf-gafi.org`         | EN   |                      |
| 5  | ACPR / Banque de France — lignes directrices LCB-FT          | `acpr.banque-france.fr` | FR   |                      |
| 6  | ACPR — lignes directrices PPE / gel des avoirs               | `acpr.banque-france.fr` | FR   |                      |
| 7  | Comité de Bâle (BCBS) —*Sound management of ML/FT risks* | `bis.org`               | EN   |                      |
| 8  | EBA — guidelines on customer due diligence                   | `eba.europa.eu`         | EN   |                      |
| 9  | Bank Al-Maghrib — circulaire LCB-FT                          | `bkam.ma`               | AR   | AR real content      |
| 10 | SAMA / Banque centrale (Golfe) — AML circular                | central-bank portal       | AR   |                      |

Exact PDF deep-links and versions are recorded per file in `MANIFEST.md`
(created during collection) so any retrieval result stays reproducible against a
known document version.

## Licensing

All sources are official public regulatory publications, redistributed here only
locally for evaluation. Keep the original publication reference (issuer, title,
version, date, URL) for each file in `MANIFEST.md`.

## Layout

```
corpus/demo/
├── README.md      # this file (committed)
├── MANIFEST.md    # per-file provenance table (committed, added during collection)
├── fr/            # French PDFs/DOCX      (gitignored)
├── en/            # English PDFs/DOCX     (gitignored)
└── ar/            # Arabic PDFs/DOCX      (gitignored)
```

## Status

- [X] Sources identified and prioritised (week 0)
- [ ] GAFI 40 Recommendations FR/EN/AR downloaded
- [ ] ACPR + BCBS + EBA downloaded
- [ ] AR central-bank circulars downloade d
- [ ] `MANIFEST.md` provenance table filled
- [ ] Golden set built on demo corpus (week 2, J5)
