"""Seed records for scenarios S1 (hero) and S2 (contrast)
(docs/PLAN.md §1b, §4, §5c).

All company, plant, material, supplier, vessel, and forwarder names are
fictional. S1 keeps the ratio locked in PLAN §1a: 38 t on hand against
20 t/day is 1.9 days of coverage, while the exception takes about 3 days.

Scale: plant 1100 is a mid-size integrated mill of roughly 1,000 to 1,500
air-dry tonnes of pulp per day. Bleaching uses about 13 to 20 kg of sodium
chlorate per tonne of hardwood pulp (chlorine dioxide made on site), which
gives the 20 t/day of CHEM-BX40; caustic soda use is of the same order.
These are assumptions for plausibility, not data from a real mill.
"""

from clear_tools import s4

BUYER = "PT Arunika Pulp & Paper"

PLANTS = {
    "1100": {"name": "Arunika West Mill", "region": "West Java, near Tanjung Priok"},
    "1200": {"name": "Arunika East Mill", "region": "East Java"},
}

MATERIALS = {
    "CHEM-BX40": {"text": "Bleaching agent BX-40", "cargo_category": "bleaching_chemical"},
    "CHEM-CX20": {"text": "Caustic agent CX-20", "cargo_category": "caustic"},
}

SUPPLIERS = {
    "17300101": {"name": "Veltrona Chemicals GmbH", "city": "Hamburg", "country": "Germany"},
    "17300102": {"name": "Sorvane Industrial Co., Ltd.", "city": "Qingdao", "country": "China"},
}

# Inbound purchase orders: one per scenario shipment.
PURCHASE_ORDERS = [
    {"number": "4500001021", "date": "2026-09-07", "supplier": "17300101",
     "material": "CHEM-BX40", "plant": "1100", "quantity": 120},
    {"number": "4500001022", "date": "2026-09-28", "supplier": "17300102",
     "material": "CHEM-CX20", "plant": "1100", "quantity": 350},
]

# (material, plant): (unrestricted stock t, safety stock t)
STOCK = {
    ("CHEM-BX40", "1100"): (38, 30),
    ("CHEM-BX40", "1200"): (60, 40),
    ("CHEM-CX20", "1100"): (300, 100),
    ("CHEM-CX20", "1200"): (140, 80),
}

# Daily chemical use per order. At plant 1100, CHEM-BX40 sums to 20 t/day for
# all orders, 15 t/day for critical + high, and 12 t/day for critical only.
DEMAND_ORDERS = [
    ("PRD-1101", "1100", "Liquid packaging board", "Export key account", "critical",
     {"CHEM-BX40": 5, "CHEM-CX20": 12}),
    ("PRD-1102", "1100", "Food-grade folding box board", "Domestic key account", "critical",
     {"CHEM-BX40": 4, "CHEM-CX20": 10}),
    ("PRD-1103", "1100", "Medical-grade tissue", "Healthcare contract", "critical",
     {"CHEM-BX40": 3, "CHEM-CX20": 8}),
    ("PRD-1104", "1100", "Copy paper A4 80 gsm", "Export distributor", "high",
     {"CHEM-BX40": 2, "CHEM-CX20": 5}),
    ("PRD-1105", "1100", "Coated art paper 120 gsm", "Domestic distributor", "high",
     {"CHEM-BX40": 1, "CHEM-CX20": 4}),
    ("PRD-1106", "1100", "Uncoated woodfree 70 gsm", "Domestic distributor", "normal",
     {"CHEM-BX40": 3, "CHEM-CX20": 6}),
    ("PRD-1107", "1100", "Newsprint 45 gsm", "Spot market", "normal",
     {"CHEM-BX40": 2, "CHEM-CX20": 5}),
    ("PRD-1201", "1200", "Corrugating medium", "Domestic key account", "critical",
     {"CHEM-BX40": 7, "CHEM-CX20": 15}),
    ("PRD-1202", "1200", "Kraft liner", "Spot market", "normal",
     {"CHEM-BX40": 5, "CHEM-CX20": 10}),
]

PARAMETERS = {
    "note": "Scenario assumptions, not measured values.",
    "plants": PLANTS,
    "port_to_plant_transit_days": {"Tanjung Priok": {"1100": 0.5, "1200": 2.0}},
    "sto_lead_time_days": {"1200": {"1100": 1.0}, "1100": {"1200": 1.0}},
    "transfer_cost_usd_per_t": {"1200": {"1100": 45.0}, "1100": {"1200": 45.0}},
    "baseline_min_group_size": 10,
}

REQUIRED_DOCUMENTS = ["commercial_invoice", "packing_list", "bill_of_lading", "certificate_of_analysis"]

SHIPMENTS = [
    {
        "shipment_id": "SHP-1001",
        "scenario": "S1",
        "purchase_order": "4500001021",
        "status": "in_transit",
        "mode": "sea",
        "vessel": "MV Northern Lumen",
        "voyage": "NL-2641",
        "port_of_loading": "Hamburg",
        "port_of_discharge": "Tanjung Priok",
        "eta": "2026-10-31T14:00:00+07:00",
        "forwarder": "FWD-B",
        "origin_country": "DE",
        "cargo_category": "bleaching_chemical",
        "required_documents": REQUIRED_DOCUMENTS,
        "exception": None,
        "events": [{"event_id": "EV-1001-01", "type": "departed",
                    "occurred_at": "2026-10-03T18:00:00+02:00", "description": "Departed Hamburg."}],
    },
    {
        "shipment_id": "SHP-1002",
        "scenario": "S2",
        "purchase_order": "4500001022",
        "status": "in_transit",
        "mode": "sea",
        "vessel": "MV Jade Meridian",
        "voyage": "JM-0917",
        "port_of_loading": "Qingdao",
        "port_of_discharge": "Tanjung Priok",
        "eta": "2026-10-30T08:00:00+07:00",
        "forwarder": "FWD-D",
        "origin_country": "CN",
        "cargo_category": "caustic",
        "required_documents": REQUIRED_DOCUMENTS,
        "exception": None,
        "events": [{"event_id": "EV-1002-01", "type": "departed",
                    "occurred_at": "2026-10-19T21:00:00+08:00", "description": "Departed Qingdao."}],
    },
]

# Prepared events for the demo's event feed (docs/PLAN.md §7a).
EVENT_CATALOG = [
    {
        "event_id": "S1-DOC-HOLD",
        "scenario": "S1",
        "type": "customs_document_hold",
        "shipment_id": "SHP-1001",
        "occurred_at": "2026-10-30T09:15:00+07:00",
        "description": "Pre-arrival customs check flagged SHP-1001: the shipping documents "
        "do not agree on quantity.",
        "details": {"exception_type": "document_discrepancy", "congestion_level": "normal",
                    "missing_documents": 0, "has_document_discrepancy": True},
    },
    {
        "event_id": "S1-ETA-SLIP",
        "scenario": "S1",
        "type": "eta_change",
        "shipment_id": "SHP-1001",
        "occurred_at": "2026-10-30T15:40:00+07:00",
        "description": "Berth congestion at Tanjung Priok: the carrier moved the ETA of "
        "MV Northern Lumen back by one day.",
        "details": {"new_eta": "2026-11-01T14:00:00+07:00", "congestion_level": "high"},
    },
    {
        "event_id": "S2-CONGESTION",
        "scenario": "S2",
        "type": "port_congestion",
        "shipment_id": "SHP-1002",
        "occurred_at": "2026-10-30T11:00:00+07:00",
        "description": "Yard congestion at Tanjung Priok is delaying discharge of SHP-1002.",
        "details": {"exception_type": "port_congestion", "congestion_level": "high",
                    "missing_documents": 0, "has_document_discrepancy": False},
    },
]


def s4_entity_sets() -> dict[str, list[dict]]:
    """Mock S/4HANA entity sets, keyed by store name."""
    return {
        s4.PO_HEADERS: [
            {"PurchaseOrder": po["number"], "PurchaseOrderType": s4.STANDARD_PO,
             "PurchaseOrderDate": po["date"], "Supplier": po["supplier"], "SupplyingPlant": ""}
            for po in PURCHASE_ORDERS
        ],
        s4.PO_ITEMS: [
            {"PurchaseOrder": po["number"], "PurchaseOrderItem": "10",
             "PurchaseOrderItemText": MATERIALS[po["material"]]["text"], "Material": po["material"],
             "Plant": po["plant"], "OrderQuantity": po["quantity"], "PurchaseOrderQuantityUnit": s4.TONNE}
            for po in PURCHASE_ORDERS
        ],
        s4.SUPPLIERS: [
            {"Supplier": number, "SupplierName": supplier["name"]} for number, supplier in SUPPLIERS.items()
        ],
        s4.STOCK: [
            {"Material": material, "Plant": plant, "InventoryStockType": s4.UNRESTRICTED,
             "MaterialBaseUnit": s4.TONNE, "MatlWrhsStkQtyInMatlBaseUnit": on_hand}
            for (material, plant), (on_hand, _) in STOCK.items()
        ],
        s4.SUPPLY_PLANNING: [
            {"Product": material, "Plant": plant, "SafetyStockQuantity": safety, "BaseUnit": s4.TONNE}
            for (material, plant), (_, safety) in STOCK.items()
        ],
    }


def demand_orders() -> list[dict]:
    return [
        {"order_id": order_id, "plant": plant, "product": product, "customer_segment": segment,
         "priority": priority, "consumption_t_per_day": consumption}
        for order_id, plant, product, segment, priority, consumption in DEMAND_ORDERS
    ]
