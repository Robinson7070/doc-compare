"""Generate synthetic PO / invoice / delivery-note test sets for doc-compare.
Each set folder gets three PDFs and answer.txt (the ground truth)."""
import os, io, random, subprocess, tempfile
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from PIL import Image, ImageFilter
import numpy as np

W, H = A4
def money(x): return f"{x:,.2f}"

def page(path, title, sub=None):
    c = canvas.Canvas(path, pagesize=A4)
    c.setFont("Helvetica-Bold", 14); c.drawCentredString(W/2, H-60, "MERIDIAN VEHICLE PARTS CO." if True else "")
    if sub: c.setFont("Helvetica", 8); c.drawCentredString(W/2, H-74, sub)
    c.setFont("Helvetica-Bold", 12); c.drawCentredString(W/2, H-100, title)
    return c

def kv(c, y, pairs):
    for (k1, v1), (k2, v2) in pairs:
        c.setFont("Helvetica", 9); c.drawString(50, y, k1); c.drawString(135, y, v1)
        if k2: c.drawString(330, y, k2); c.drawString(430, y, v2)
        y -= 16
    return y

def table(c, y, heads, xs, rows, right=()):
    c.setFont("Helvetica-Bold", 9)
    for h, x in zip(heads, xs): c.drawString(x, y, h)
    c.line(50, y-4, W-50, y-4); y -= 18
    c.setFont("Helvetica", 9)
    for r in rows:
        for i, (v, x) in enumerate(zip(r, xs)):
            if i in right: c.drawRightString(x+40, y, str(v))
            else: c.drawString(x, y, str(v))
        y -= 16
    return y

def totals(c, y, labels):
    for lab, val, bold in labels:
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 9)
        c.drawRightString(W-150, y, lab); c.drawRightString(W-55, y, val); y -= 16
    return y

def build(folder, s):
    """s: dict describing one set. Doc values may differ from each other on purpose."""
    os.makedirs(folder, exist_ok=True)
    po_lines, inv_lines, dn_lines = s["po"], s["inv"], s["dn"]
    # purchase order
    c = page(f"{folder}/{s['po_no']}.pdf", "PURCHASE ORDER ACCEPTANCE")
    y = kv(c, H-135, [(("PO Ref:", s["po_no"]), ("Date:", s["po_date"])), (("Bill To:", s["customer"]), ("Buyer Contact:", s["buyer"])), (("Ship To:", s["ship"]), ("", ""))])
    rows = [(i+1, l["part"], l["desc"], l["qty"], money(l["unit"]), money(l["qty"]*l["unit"] if "total" not in l else l["total"])) for i, l in enumerate(po_lines)]
    y = table(c, y-14, ["Line","Part No.","Description","Qty","Unit £","Line Total £"], [50,90,160,350,400,470], rows, right=(3,4,5))
    sub = sum(l["qty"]*l["unit"] for l in po_lines); vat = round(sub*0.2, 2)
    totals(c, y-10, [("Subtotal:", money(sub), 0), ("VAT @ 20%:", money(vat), 0), ("GRAND TOTAL:", money(sub+vat), 1)])
    c.setFont("Helvetica", 9); c.drawString(50, 120, "Terms: NET 30 DAYS FROM INVOICE DATE"); c.drawString(50, 106, f"Approved: {s['buyer'].split(',')[0]}")
    c.save()
    # invoice
    c = page(f"{folder}/{s['inv_no']}.pdf", "INVOICE", "Registered Office: 14 Forge Lane, Walsall | VAT Reg: GB 884 2210 77")
    y = kv(c, H-135, [(("Invoice No:", s["inv_no"]), ("Invoice Date:", s["inv_date"])), (("Customer PO:", s["po_no"]), ("Due Date:", s["due"])), (("Customer:", s["customer"]), ("", ""))])
    rows = []
    for i, l in enumerate(inv_lines):
        tot = l["total"] if "total" in l else l["qty"]*l["unit"]
        rows.append((i+1, l["part"], l.get("inv_desc", l["desc"]), l["qty"], money(l["unit"]), money(tot)))
    y = table(c, y-14, ["Line","Part No.","Description","Qty","Unit £","Line Total £"], [50,90,160,350,400,470], rows, right=(3,4,5))
    sub = sum((l["total"] if "total" in l else l["qty"]*l["unit"]) for l in inv_lines); vat = round(sub*0.2, 2)
    totals(c, y-10, [("Subtotal:", money(sub), 0), ("VAT @ 20%:", money(vat), 0), ("AMOUNT DUE:", money(sub+vat), 1)])
    c.setFont("Helvetica", 9); c.drawString(50, 120, "Please remit payment to account ending 4471 within terms.")
    c.save()
    # delivery note
    c = page(f"{folder}/{s['dn_no']}.pdf", "DELIVERY NOTE")
    y = kv(c, H-135, [(("DN No:", s["dn_no"]), ("Date Delivered:", s["dn_date"])), (("Linked Invoice:", s["inv_no"]), ("Linked PO:", s["po_no"])), (("Delivered To:", s["customer"]+", "+s["ship"]), ("", "")), (("Received By:", s["recv"]), ("", ""))])
    rows = [(l["part"], l["desc"], l["qty"], l.get("delivered", l["qty"]), l.get("cond", "Good")) for l in dn_lines]
    y = table(c, y-14, ["Part No.","Description","Qty Ordered","Qty Delivered","Condition"], [50,130,330,400,470], rows, right=(2,3))
    c.setFont("Helvetica", 9); c.drawString(50, y-16, "Remarks: " + s.get("remarks", "Delivery complete, no shortages or damage."))
    c.save()
    open(f"{folder}/answer.txt", "w").write(s["answer"])
    if s.get("scan"): scanify(folder, s["scan"])

def scanify(folder, seed):
    """Turn each PDF into a rotated, noisy raster PDF, like a phone scan."""
    rnd = random.Random(seed); np.random.seed(seed)
    for fn in [f for f in os.listdir(folder) if f.endswith(".pdf")]:
        p = f"{folder}/{fn}"
        with tempfile.TemporaryDirectory() as t:
            subprocess.run(["pdftoppm", "-r", "150", "-gray", "-png", p, f"{t}/p"], check=True)
            png = sorted(os.listdir(t))[0]
            im = Image.open(f"{t}/{png}").convert("L")
            im = im.rotate(rnd.uniform(-1.6, 1.6), expand=False, fillcolor=235, resample=Image.BICUBIC)
            im = im.filter(ImageFilter.GaussianBlur(0.7))
            a = np.asarray(im).astype(float)
            a = a*0.92 + 14 + np.random.normal(0, 7, a.shape)
            grad = np.linspace(0, 18, a.shape[1])[None, :]
            a = np.clip(a - grad, 0, 255).astype("uint8")
            Image.fromarray(a).save(p, "PDF", resolution=150)

CUST, SHIP = "Apex Logistics Ltd", "Unit 4, Riverside Industrial Estate, Birmingham, B12 0PQ"
base = dict(customer=CUST, ship=SHIP, buyer="J. Okafor, Procurement Manager", recv="T. Adeyemi (Warehouse Supervisor)")
BRK = dict(part="VP-204", desc="Brake Pad Set (Front)")
FLT = dict(part="VP-318", desc="Oil Filter (Heavy Duty)")
BLT = dict(part="VP-422", desc="Serpentine Belt 6PK")
WPR = dict(part="VP-107", desc="Wiper Blade Pair 24in")
def L(p, qty, unit, **kw): d = dict(p); d.update(qty=qty, unit=unit); d.update(kw); return d

sets = {}
# 03 short delivery: invoice bills ordered qty, delivery shorter
sets["set03_short_delivery"] = dict(base, po_no="PO-2026-3001", inv_no="INV-MV-8203", dn_no="DN-9203", po_date="14 April 2026", inv_date="22/04/2026", due="22/05/2026", dn_date="20/04/2026",
  po=[L(FLT,120,6.80), L(BLT,30,14.25)], inv=[L(FLT,120,6.80), L(BLT,30,14.25)], dn=[L(FLT,120,6.80), L(BLT,30,14.25, delivered=24, cond="Good")],
  remarks="Delivery incomplete, VP-422 short by 6 units, balance to follow.",
  answer="short delivery: VP-422 Serpentine Belt 6PK, PO 30 units, delivery note 24 delivered, invoice bills 30 units, 6 units billed but not delivered (£85.50 ex VAT)")
# 04 quantity mismatch on invoice
sets["set04_quantity_mismatch"] = dict(base, po_no="PO-2026-3002", inv_no="INV-MV-8204", dn_no="DN-9204", po_date="16 April 2026", inv_date="24/04/2026", due="24/05/2026", dn_date="22/04/2026",
  po=[L(WPR,50,4.90), L(BRK,20,42.00)], inv=[L(WPR,60,4.90), L(BRK,20,42.00)], dn=[L(WPR,50,4.90), L(BRK,20,42.00)],
  answer="quantity mismatch: VP-107 Wiper Blade Pair 24in, PO 50 units, delivery note 50 delivered, invoice bills 60 units, 10 units overbilled (£49.00 ex VAT)")
# 05 invoice omits a line
sets["set05_missing_invoice_line"] = dict(base, po_no="PO-2026-3003", inv_no="INV-MV-8205", dn_no="DN-9205", po_date="20 April 2026", inv_date="28/04/2026", due="28/05/2026", dn_date="26/04/2026",
  po=[L(BRK,25,42.00), L(FLT,40,6.80), L(BLT,15,14.25)], inv=[L(BRK,25,42.00), L(BLT,15,14.25)], dn=[L(BRK,25,42.00), L(FLT,40,6.80), L(BLT,15,14.25)],
  answer="missing invoice line: VP-318 Oil Filter (Heavy Duty), on PO (40 units at £6.80) and delivered (40), not on invoice, £272.00 ex VAT unbilled")
# 06 arithmetic error on invoice line total
sets["set06_line_total_error"] = dict(base, po_no="PO-2026-3004", inv_no="INV-MV-8206", dn_no="DN-9206", po_date="23 April 2026", inv_date="01/05/2026", due="31/05/2026", dn_date="29/04/2026",
  po=[L(BLT,60,14.25)], inv=[L(BLT,60,14.25, total=885.00)], dn=[L(BLT,60,14.25)],
  answer="arithmetic error: VP-422 Serpentine Belt 6PK, 60 units at £14.25 is £855.00, invoice line total shows £885.00, £30.00 overcharge before VAT")
# 07 messy: scanned, price mismatch on line 2
sets["set07_scanned_price_mismatch"] = dict(base, po_no="PO-2026-3005", inv_no="INV-MV-8207", dn_no="DN-9207", po_date="27 April 2026", inv_date="05/05/2026", due="04/06/2026", dn_date="03/05/2026",
  po=[L(WPR,80,4.90), L(FLT,60,6.80)], inv=[L(WPR,80,4.90), L(FLT,60,7.40)], dn=[L(WPR,80,4.90), L(FLT,60,6.80)],
  answer="price mismatch: VP-318 Oil Filter (Heavy Duty), PO £6.80 per unit, invoice £7.40 per unit, 60 units, £36.00 overcharge (scanned copies, rotated and noisy)", scan=7)
# 08 messy: consistent but invoice abbreviates descriptions
sets["set08_abbreviated_descriptions"] = dict(base, po_no="PO-2026-3006", inv_no="INV-MV-8208", dn_no="DN-9208", po_date="30 April 2026", inv_date="08/05/2026", due="07/06/2026", dn_date="06/05/2026",
  po=[L(BRK,15,42.00), L(WPR,35,4.90)], inv=[L(BRK,15,42.00, inv_desc="Brk Pad Set Frnt"), L(WPR,35,4.90, inv_desc="Wiper Blade Pr 24in")], dn=[L(BRK,15,42.00), L(WPR,35,4.90)],
  answer="consistent, no mismatches (invoice abbreviates the descriptions, part numbers, quantities and prices all agree)")
# hold-out sets
hold = {}
hold["set09_holdout_wrong_part"] = dict(base, po_no="PO-2026-3007", inv_no="INV-MV-8209", dn_no="DN-9209", po_date="04 May 2026", inv_date="12/05/2026", due="11/06/2026", dn_date="10/05/2026",
  po=[L(BRK,30,42.00), L(BLT,10,14.25)], inv=[L(BRK,30,42.00), L(BLT,10,14.25)], dn=[L(BRK,30,42.00), dict(L(BLT,10,14.25), part="VP-423", desc="Serpentine Belt 8PK")],
  answer="wrong part: PO and invoice have VP-422 Serpentine Belt 6PK, delivery note shows VP-423 Serpentine Belt 8PK, 10 units, wrong item delivered")
hold["set10_holdout_clean_three_lines"] = dict(base, po_no="PO-2026-3008", inv_no="INV-MV-8210", dn_no="DN-9210", po_date="07 May 2026", inv_date="15/05/2026", due="14/06/2026", dn_date="13/05/2026",
  po=[L(BRK,18,42.00), L(FLT,75,6.80), L(WPR,40,4.90)], inv=[L(BRK,18,42.00), L(FLT,75,6.80), L(WPR,40,4.90)], dn=[L(BRK,18,42.00), L(FLT,75,6.80), L(WPR,40,4.90)],
  answer="consistent, no mismatches")

out = os.environ.get("OUT", "out")
for n, s in sets.items(): build(f"{out}/test_sets/{n}", s)
for n, s in hold.items(): build(f"{out}/test_sets/holdout/{n}", s)
