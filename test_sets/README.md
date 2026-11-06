# Test sets

Each folder holds a purchase order, an invoice and a delivery note (PDF) plus `answer.txt`, the ground truth.
All data is synthetic.

| Set | Planted problem |
|---|---|
| set01_clean | none |
| set02_price_mismatch | invoice unit price above PO |
| set03_short_delivery | fewer units delivered than billed |
| set04_quantity_mismatch | invoice bills more units than ordered |
| set05_missing_invoice_line | a delivered, ordered line is missing from the invoice |
| set06_line_total_error | invoice line total does not equal qty x unit price |
| set07_scanned_price_mismatch | price mismatch, documents are noisy rotated scans (no text layer) |
| set08_abbreviated_descriptions | consistent, but the invoice abbreviates descriptions |
| holdout/ | sets 09 and 10. Do not look at these or tune against them until the first version is finished |

`scripts/gen_sets.py` regenerates sets 03 to 10 (`OUT=. python3 scripts/gen_sets.py`).
