"""doc-compare v0.1: check a purchase order, invoice and delivery note against each other.

Rules only, no LLM. Works on PDFs with a text layer. Scanned PDFs are reported as unreadable (OCR comes in v0.2).

Usage:
    python doc_compare.py check test_sets/set02_price_mismatch
    python doc_compare.py evaluate test_sets            # scores every set against its answer.txt
    python doc_compare.py evaluate test_sets --holdout  # ONLY when v0.1 is finished
"""
import re, sys, json
from pathlib import Path
import pdfplumber

PART = r"[A-Z]{1,4}-\d+"
NUM = r"[\d,]+\.\d\d"
# PO / invoice line:  1  VP-204  Brake Pad Set (Front)  40  42.00  1,680.00
LINE = re.compile(rf"^\s*(\d+)\s+({PART})\s+(.+?)\s+(\d+)\s+({NUM})\s+({NUM})\s*$")
# delivery note line:  VP-204  Brake Pad Set (Front)  40  40  Good
DN_LINE = re.compile(rf"^\s*({PART})\s+(.+?)\s+(\d+)\s+(\d+)\s+(\w+)\s*$")


def money(s): return float(s.replace(",", ""))


def read_text(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    return text.strip()


def parse(pdf_path):
    """Return {'kind': 'po'|'invoice'|'dn', 'lines': [...], 'file': name} or {'kind': 'unreadable'}."""
    text = read_text(pdf_path)
    if len(text) < 20:
        return {"kind": "unreadable", "file": Path(pdf_path).name}
    up = text.upper()
    if "PURCHASE ORDER" in up: kind = "po"
    elif "DELIVERY NOTE" in up: kind = "dn"
    elif "INVOICE" in up: kind = "invoice"
    else: return {"kind": "unknown", "file": Path(pdf_path).name}
    lines = []
    for raw in text.splitlines():
        if kind == "dn":
            m = DN_LINE.match(raw)
            if m: lines.append(dict(part=m[1], desc=m[2], ordered=int(m[3]), delivered=int(m[4]), raw=raw.strip()))
        else:
            m = LINE.match(raw)
            if m: lines.append(dict(part=m[2], desc=m[3], qty=int(m[4]), unit=money(m[5]), total=money(m[6]), raw=raw.strip()))
    return {"kind": kind, "lines": lines, "file": Path(pdf_path).name}


def by_part(doc): return {l["part"]: l for l in doc["lines"]}


def check(folder):
    """Return (findings, problems). Each finding has a type, a message and the exact text quoted from each document."""
    docs = {}
    problems = []
    for pdf in sorted(Path(folder).glob("*.pdf")):
        d = parse(pdf)
        if d["kind"] in ("unreadable", "unknown"):
            problems.append(f"{d['file']}: {d['kind']} (no text layer; needs OCR)")
        else:
            docs[d["kind"]] = d
    if problems or len(docs) < 3:
        if not problems: problems.append(f"expected 3 documents, found {sorted(docs)}")
        return [], problems

    po, inv, dn = by_part(docs["po"]), by_part(docs["invoice"]), by_part(docs["dn"])
    F = []
    def add(t, msg, **quotes): F.append(dict(type=t, message=msg, quotes=quotes))

    # arithmetic on every priced line
    for name, src in (("po", po), ("invoice", inv)):
        for p, l in src.items():
            if round(l["qty"] * l["unit"], 2) != l["total"]:
                add("arithmetic error", f"{p}: {l['qty']} x {l['unit']:.2f} = {l['qty']*l['unit']:.2f}, {name} shows {l['total']:.2f}", **{name: l["raw"]})

    # wrong part: a part on the delivery note that is not on the PO, replacing one that is
    wrong_dn, missing_dn = set(dn) - set(po), set(po) - set(dn)
    for p in sorted(wrong_dn):
        add("wrong part", f"delivery note has {p}, not on the PO (PO parts missing from delivery: {', '.join(sorted(missing_dn)) or 'none'})", dn=dn[p]["raw"])
    for p in sorted(missing_dn) if not wrong_dn else []:
        add("missing delivery line", f"{p} on the PO but not on the delivery note", po=po[p]["raw"])

    # missing / extra invoice lines
    for p in sorted(set(po) - set(inv)):
        add("missing invoice line", f"{p} on the PO but not on the invoice", po=po[p]["raw"], **({"dn": dn[p]["raw"]} if p in dn else {}))
    for p in sorted(set(inv) - set(po)):
        add("extra invoice line", f"{p} on the invoice but not on the PO", invoice=inv[p]["raw"])

    for p in sorted(set(po) & set(inv)):
        a, b = po[p], inv[p]
        if a["unit"] != b["unit"]:
            add("price mismatch", f"{p}: PO {a['unit']:.2f}, invoice {b['unit']:.2f} per unit, {b['qty']} units, difference {(b['unit']-a['unit'])*b['qty']:.2f}", po=a["raw"], invoice=b["raw"])
        if a["qty"] != b["qty"]:
            add("quantity mismatch", f"{p}: PO {a['qty']}, invoice {b['qty']} units", po=a["raw"], invoice=b["raw"])

    # delivery against invoice
    for p in sorted(set(inv) & set(dn)):
        d = dn[p]
        if d["delivered"] < d["ordered"]:
            billed = inv[p]["qty"]
            add("short delivery", f"{p}: ordered {d['ordered']}, delivered {d['delivered']}, invoice bills {billed}", dn=d["raw"], invoice=inv[p]["raw"])
    return F, []


def expected_type(answer_text):
    t = answer_text.strip().lower()
    if t.startswith("consistent"): return "consistent"
    return t.split(":")[0].strip()


def evaluate(root, holdout=False):
    root = Path(root)
    sets = sorted(p for p in (root / "holdout").iterdir() if p.is_dir()) if holdout else sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith("set"))
    rows, correct = [], 0
    for s in sets:
        exp = expected_type((s / "answer.txt").read_text())
        findings, problems = check(s)
        got = sorted({f["type"] for f in findings})
        if problems: got_s, ok = "UNREADABLE", False
        else:
            got_s = ", ".join(got) or "consistent"
            ok = got_s == exp
        correct += ok
        rows.append((s.name, exp, got_s, "PASS" if ok else "FAIL"))
    w = max(len(r[0]) for r in rows)
    print(f"{'set'.ljust(w)}  {'expected'.ljust(24)} {'found'.ljust(24)} result")
    for r in rows: print(f"{r[0].ljust(w)}  {r[1].ljust(24)} {r[2].ljust(24)} {r[3]}")
    print(f"\n{correct}/{len(rows)} sets correct")
    return correct, len(rows)


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("check", "evaluate"):
        print(__doc__); sys.exit(1)
    if sys.argv[1] == "check":
        f, probs = check(sys.argv[2])
        for p in probs: print("PROBLEM:", p)
        if not probs and not f: print("Consistent: no mismatches found.")
        for x in f:
            print(f"- {x['type'].upper()}: {x['message']}")
            for doc, q in x["quotes"].items(): print(f"    {doc}: {q}")
    else:
        evaluate(sys.argv[2], holdout="--holdout" in sys.argv)
