# Bootstrap corpus

Short **synthetic** banking-compliance documents, hand-authored for KnowVeris.
Original text — no copyrighted source. Committed to git (small, deterministic).

Purpose: develop and test the full ingestion → chunking → embedding → retrieval →
guardrails pipeline without depending on the real demo corpus. Fast and
reproducible, they back the automated test suite.

## Documents

| File | Lang | Format | Topic |
|---|---|---|---|
| `fr-obligations-vigilance.pdf` | FR | PDF (2 p.) | Obligations de vigilance clientèle (CDD) |
| `en-customer-due-diligence.docx` | EN | DOCX | Customer Due Diligence procedure |
| `ar-alainaya-alwajiba.docx` | AR | DOCX | إجراءات العناية الواجبة (CDD) |
| `en-sanctions-screening.pdf` | EN | PDF (2 p.) | Sanctions screening process |
| `fr-declaration-soupcon.docx` | FR | DOCX | Déclaration de soupçon |

## Design notes

- **Both parsers exercised.** PDFs test the PyMuPDF path and per-page attribution
  (`page_number`); DOCX use Heading styles to test the python-docx path and
  section attribution (`section_title`). A chunk without source metadata is a bug.
- **Cross-lingual triplet.** The first three documents cover the *same* Customer
  Due Diligence content in FR / EN / AR — equivalent meaning across languages,
  like the real GAFI/FATF corpus will. This lets us test cross-lingual retrieval
  (an AR question retrieving the FR/EN passages via BGE-M3) on controlled content.
- **Three languages** present (FR / EN / AR), matching the multilingual requirement.
- Multi-page PDFs (2 pages) so page-boundary chunking and page citation are
  genuinely tested, not trivially page-1-only.

## Regenerating

The binaries are the deliverable and are committed. They were produced from a
generator script kept out of the repo; to rebuild identical files, regenerate
with PyMuPDF (`fitz.Story`) for the PDFs and `python-docx` for the DOCX.
