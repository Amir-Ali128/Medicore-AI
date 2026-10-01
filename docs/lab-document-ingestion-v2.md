# Lab Document Ingestion v2

PDF, photographed tables and scanned pages share a read-only pipeline. Existing
`/simple-case/labs/pdf` and `/simple-case/labs/image` routes still return
`LabResultInput[]`; authentication, API providers, model settings and secret
configuration remain in place.

1. **Document Normalizer** opens every PDF page or verifies the image. PDFs over
   20 pages and images over 24 megapixels are rejected instead of truncated.
2. **Page / Image Processor** honors EXIF orientation and optional explicit
   clockwise rotation. It bounds raster size, crops/rectifies a clearly detected
   sheet only when the outside region is sufficiently clear, and reports blur,
   low resolution and low contrast. Ambiguous borders are kept unchanged.
3. **Table extraction** uses the existing native text parser on each separate PDF
   page when available, then the existing extraction-only Claude reader and
   OpenAI fallback. Laboratory tables never enter the radiology interpretation
   fallback. Models transcribe all visible rows, exact source reference text and
   explicit source flags, and report a visible-row count when readable. At most
   two pages are extracted concurrently. A 120-second extraction budget cancels
   unfinished requests and returns an error instead of a seemingly complete subset.
   Claude table reading has a dedicated 75-second default instead of the generic
   AI call timeout (`LAB_DOCUMENT_READ_TIMEOUT_SECONDS`, bounded to 30–80s).
   A small table whose visible-row count matches its extracted rows skips the
   extra audit. Missing/unknown counts may trigger a 15-second audit; its failure
   retains the first reading with a review warning. SDK retries are disabled so
   they cannot consume the document budget.
4. **RawLabRow / validation / merge** retains missing or conflicting observations
   for review, checks name/value/unit/status and reference bounds, and merges
   exact repeated rows while retaining every source page/row location. Dates,
   reference cells and flags participate in identity. Different observations are
   retained. Re-uploading the same document is also deduplicated in the UI.
5. **Canonical Lab Model** carries the original file SHA-256, raw name/value,
   reference, source flag, source locations and review reasons. Document-level
   warnings and page counts travel in `source_metadata`. This path does not call
   the retired native C++ runtime or compute result classifications.
6. **UI classification** derives normal/high/low from exact, safely comparable
   source intervals or explicitly printed flags. Ambiguous inequalities,
   conflicting observations, incompatible units and demographic intervals that
   lack context remain unclassified. This display grouping never filters AI input.
7. **Clinical Brain** receives every lab result, including normal, qualitative,
   unclassified and review-needed rows, plus source flags and ingestion warnings.
   Clinical inference is separate from source transcription. Oversized model
   inputs are rejected with an explanation, never silently sliced.

## Limits and verification

Visible-row counts are extraction audits, not independent proof of completeness.
`completeness_verified` stays false. Missing/count-mismatched pages and unknown
row counts are visible to the user. A partly readable document may return its
readable results with warnings; a document with no rows returns a validation
error. Review warnings must be resolved against the original document.

EXIF is the automatic orientation source; images without reliable orientation
metadata can be rotated using the upload control. Perspective correction is
heuristic and deliberately conservative. Providers, the full source document
and human review remain necessary for ambiguous photographs.

Tests use synthetic images/PDFs and mocked providers. No production patient file
or paid model request is used by CI.
