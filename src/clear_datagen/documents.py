"""Shipping documents rendered from templates (docs/PLAN.md §4b).

Invoice, packing list, bill of lading, and certificate of analysis per
shipment. Every problem shipment carries exactly one clear discrepancy: in
S1 the packing list (and the cargo actually loaded) shows 560 t while the
invoice and the purchase order say 600 t. S2's documents agree.
"""

from clear_datagen.scenarios import BUYER, MATERIALS, PLANTS, PURCHASE_ORDERS, SHIPMENTS, SUPPLIERS

# Values that differ per shipment. shipped_t is what the packing list states.
DOCUMENT_DATA = {
    "SHP-1001": {
        "ref": "VC-26-0917", "date": "2026-09-30", "unit_price": 540.00, "shipped_t": 560,
        "package_type": "IBC totes", "package_net_kg": 1_000, "package_tare_kg": 60,
        "batch": "BX40-2609-A",
        "analysis": [("Assay (as NaClO3)", ">= 99.0 %", "99.6 %"), ("Moisture", "<= 0.10 %", "0.07 %"),
                     ("Insolubles", "<= 0.01 %", "0.004 %")],
    },
    "SHP-1002": {
        "ref": "SV-26-1188", "date": "2026-10-16", "unit_price": 410.00, "shipped_t": 350,
        "package_type": "ISO tank containers", "package_net_kg": 25_000, "package_tare_kg": 3_800,
        "batch": "CX20-2610-07",
        "analysis": [("Assay (as NaOH)", ">= 48.0 %", "49.2 %"), ("Sodium chloride", "<= 0.02 %", "0.011 %"),
                     ("Iron (Fe)", "<= 5 ppm", "2 ppm")],
    },
}

COMMERCIAL_INVOICE = """\
COMMERCIAL INVOICE

Invoice No.: INV-{ref}
Invoice Date: {date}

Seller: {seller}, {seller_city}, {seller_country}
Buyer: {buyer}, {plant_name}, Indonesia

Buyer PO No.: {purchase_order}
Buyer Material No.: {material}
Description of Goods: {description}
Quantity: {invoiced_t:,} MT
Unit Price: USD {unit_price:,.2f} per MT
Total Amount: USD {total:,.2f}
Incoterms: CIF Tanjung Priok

Vessel / Voyage: {vessel} / {voyage}
Port of Loading: {port_of_loading}
Port of Discharge: {port_of_discharge}

We certify that this invoice is true and correct.
"""

PACKING_LIST = """\
PACKING LIST

Packing List No.: PL-{ref}
Date: {date}
Shipper: {seller}, {seller_city}, {seller_country}
Consignee: {buyer}, Indonesia

Buyer PO No.: {purchase_order}
Buyer Material No.: {material}
Description of Goods: {description}
Packages: {packages} {package_type}, {package_net_kg:,} kg net each
Quantity: {shipped_t:,} MT
Total Net Weight: {net_kg:,} kg
Total Gross Weight: {gross_kg:,} kg
"""

BILL_OF_LADING = """\
BILL OF LADING (NON-NEGOTIABLE COPY)

B/L No.: BL-{ref}
Shipper: {seller}, {seller_city}, {seller_country}
Consignee: {buyer}, Indonesia
Notify Party: Same as consignee

Vessel / Voyage: {vessel} / {voyage}
Port of Loading: {port_of_loading}
Port of Discharge: {port_of_discharge}

Description of Goods: {packages} {package_type} said to contain {description}
Gross Weight: {gross_kg:,} kg
Reference: Buyer PO No. {purchase_order}
Freight: Prepaid
"""

CERTIFICATE_OF_ANALYSIS = """\
CERTIFICATE OF ANALYSIS

Certificate No.: COA-{ref}
Product: {description}
Buyer Material No.: {material}
Batch No.: {batch}
Date of Analysis: {date}

{analysis}

Conclusion: The batch conforms to the agreed specification.
"""

TEMPLATES = {
    "commercial_invoice": COMMERCIAL_INVOICE,
    "packing_list": PACKING_LIST,
    "bill_of_lading": BILL_OF_LADING,
    "certificate_of_analysis": CERTIFICATE_OF_ANALYSIS,
}


def render_documents() -> dict[str, str]:
    """Document texts keyed by store name, e.g. documents/SHP-1001/packing_list.txt."""
    rendered = {}
    for shipment in SHIPMENTS:
        values = _values(shipment)
        for document_type, template in TEMPLATES.items():
            rendered[f"documents/{shipment['shipment_id']}/{document_type}.txt"] = template.format(**values)
    return rendered


def _values(shipment: dict) -> dict:
    data = DOCUMENT_DATA[shipment["shipment_id"]]
    po = next(p for p in PURCHASE_ORDERS if p["number"] == shipment["purchase_order"])
    supplier = SUPPLIERS[po["supplier"]]
    packages = data["shipped_t"] * 1_000 // data["package_net_kg"]
    rows = [f"{'Parameter':<22}{'Specification':<16}Result"]
    rows += [f"{name:<22}{spec:<16}{result}" for name, spec, result in data["analysis"]]
    return {
        **shipment,
        **data,
        "seller": supplier["name"],
        "seller_city": supplier["city"],
        "seller_country": supplier["country"],
        "buyer": BUYER,
        "plant_name": PLANTS[po["plant"]]["name"],
        "material": po["material"],
        "description": MATERIALS[po["material"]]["text"],
        "invoiced_t": po["quantity"],
        "total": po["quantity"] * data["unit_price"],
        "packages": packages,
        "net_kg": data["shipped_t"] * 1_000,
        "gross_kg": data["shipped_t"] * 1_000 + packages * data["package_tare_kg"],
        "analysis": "\n".join(rows),
    }
