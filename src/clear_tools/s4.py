"""Mock S/4HANA (docs/PLAN.md §4a).

The only module that knows S/4HANA entity and field names. Each entity set
lives at s4/<OData service>/<entity set>, mirroring the service paths of the
real APIs, and keeps only the fields CLEAR uses. Names follow the API
definitions SAP publishes for API_PURCHASEORDER_PROCESS_SRV,
API_MATERIAL_STOCK_SRV, API_PRODUCT_SRV, and API_BUSINESS_PARTNER. Dates are
ISO strings and quantities JSON numbers, not the OData V2 wire format.

Replacing this module with an OData client for a real system leaves the
tools and the agent unchanged.
"""

from datetime import date

from clear_tools.store import JsonStore

PO_HEADERS = "s4/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrder"
PO_ITEMS = "s4/API_PURCHASEORDER_PROCESS_SRV/A_PurchaseOrderItem"
STOCK = "s4/API_MATERIAL_STOCK_SRV/A_MatlStkInAcctMod"
SUPPLY_PLANNING = "s4/API_PRODUCT_SRV/A_ProductSupplyPlanning"
SUPPLIERS = "s4/API_BUSINESS_PARTNER/A_Supplier"

UNRESTRICTED = "01"  # InventoryStockType: unrestricted-use stock
IN_TRANSIT = "06"  # InventoryStockType: stock in transit
STANDARD_PO = "NB"  # PurchaseOrderType: standard purchase order (SAP default customizing)
STO = "UB"  # PurchaseOrderType: stock transport order (SAP default customizing)
TONNE = "TO"  # Unit of measure key for tonne


def purchase_order(store: JsonStore, number: str) -> dict:
    """Header, items, and supplier of a purchase order, shaped as the APIs return them."""
    header = _find(store.read(PO_HEADERS), "purchase order", PurchaseOrder=number)
    items = [item for item in store.read(PO_ITEMS) if item["PurchaseOrder"] == number]
    supplier = next(
        (s for s in store.read(SUPPLIERS) if s["Supplier"] == header["Supplier"]), None
    )
    return {"A_PurchaseOrder": header, "A_PurchaseOrderItem": items, "A_Supplier": supplier}


def stock(store: JsonStore, material: str, plant: str, stock_type: str) -> float:
    return sum(
        row["MatlWrhsStkQtyInMatlBaseUnit"]
        for row in store.read(STOCK)
        if (row["Material"], row["Plant"], row["InventoryStockType"]) == (material, plant, stock_type)
    )


def safety_stock(store: JsonStore, material: str, plant: str) -> float:
    row = _find(store.read(SUPPLY_PLANNING), "supply planning record", Product=material, Plant=plant)
    return row["SafetyStockQuantity"]


def plants_holding(store: JsonStore, material: str) -> list[str]:
    return sorted({row["Plant"] for row in store.read(STOCK) if row["Material"] == material})


def post_stock_change(
    store: JsonStore, material: str, plant: str, stock_type: str, delta: float
) -> None:
    rows = store.read(STOCK)
    for row in rows:
        if (row["Material"], row["Plant"], row["InventoryStockType"]) == (material, plant, stock_type):
            row["MatlWrhsStkQtyInMatlBaseUnit"] = round(row["MatlWrhsStkQtyInMatlBaseUnit"] + delta, 3)
            break
    else:
        rows.append({
            "Material": material,
            "Plant": plant,
            "InventoryStockType": stock_type,
            "MaterialBaseUnit": TONNE,
            "MatlWrhsStkQtyInMatlBaseUnit": round(delta, 3),
        })
    store.write(STOCK, rows)


def insert_stock_transport_order(
    store: JsonStore, supplying_plant: str, plant: str, material: str, quantity: float, item_text: str
) -> str:
    """Create an STO (a purchase order of type UB) and return its number."""
    headers = store.read(PO_HEADERS)
    number = str(max(int(h["PurchaseOrder"]) for h in headers) + 1)
    headers.append({
        "PurchaseOrder": number,
        "PurchaseOrderType": STO,
        "PurchaseOrderDate": date.today().isoformat(),
        "Supplier": "",
        "SupplyingPlant": supplying_plant,
    })
    items = store.read(PO_ITEMS)
    items.append({
        "PurchaseOrder": number,
        "PurchaseOrderItem": "10",
        "PurchaseOrderItemText": item_text,
        "Material": material,
        "Plant": plant,
        "OrderQuantity": quantity,
        "PurchaseOrderQuantityUnit": TONNE,
    })
    store.write(PO_HEADERS, headers)
    store.write(PO_ITEMS, items)
    return number


def _find(rows: list[dict], what: str, **keys: str) -> dict:
    for row in rows:
        if all(row[k] == v for k, v in keys.items()):
            return row
    raise LookupError(f"No {what} for {keys}")
