"""Production plan and logistics assumptions (docs/PLAN.md §5c).

Not S/4HANA data. Demand orders carry a priority and the amount of each
chemical they consume per day. Parameters hold transit times, STO lead times,
and transfer costs, which are scenario assumptions rather than measured
values.
"""

from clear_tools.store import JsonStore

ORDERS = "planning/demand_orders"
PARAMETERS = "planning/parameters"

# Order priorities served at each priority level of a plan.
PRIORITY_LEVELS = {
    "all": ("critical", "high", "normal"),
    "critical_high": ("critical", "high"),
    "critical": ("critical",),
}


def orders(store: JsonStore, material: str, plant: str) -> list[dict]:
    """Orders at the plant that consume the material, with their daily use of it."""
    return [
        {
            "order_id": order["order_id"],
            "product": order["product"],
            "priority": order["priority"],
            "consumption_t_per_day": order["consumption_t_per_day"][material],
        }
        for order in store.read(ORDERS)
        if order["plant"] == plant and material in order["consumption_t_per_day"]
    ]


def split_orders(
    store: JsonStore, material: str, plant: str, priority_level: str
) -> tuple[list[dict], list[dict]]:
    """Orders served and orders deferred at the given priority level."""
    if priority_level not in PRIORITY_LEVELS:
        raise ValueError(f"priority_level must be one of {list(PRIORITY_LEVELS)}, got {priority_level!r}")
    served_priorities = PRIORITY_LEVELS[priority_level]
    all_orders = orders(store, material, plant)
    served = [o for o in all_orders if o["priority"] in served_priorities]
    deferred = [o for o in all_orders if o["priority"] not in served_priorities]
    return served, deferred


def consumption_per_day(store: JsonStore, material: str, plant: str, priority_level: str) -> float:
    served, _ = split_orders(store, material, plant, priority_level)
    return round(sum(o["consumption_t_per_day"] for o in served), 3)


def transit_days(store: JsonStore, port: str, plant: str) -> float:
    return _lookup(store, "port_to_plant_transit_days", port, plant)


def sto_lead_time_days(store: JsonStore, source_plant: str, plant: str) -> float:
    return _lookup(store, "sto_lead_time_days", source_plant, plant)


def transfer_cost_per_t(store: JsonStore, source_plant: str, plant: str) -> float:
    return _lookup(store, "transfer_cost_usd_per_t", source_plant, plant)


def baseline_min_group_size(store: JsonStore) -> int:
    return store.read(PARAMETERS)["baseline_min_group_size"]


def _lookup(store: JsonStore, table: str, origin: str, destination: str) -> float:
    try:
        return store.read(PARAMETERS)[table][origin][destination]
    except KeyError:
        raise LookupError(f"No {table} for {origin} -> {destination}") from None
