"""Clearly SYNTHETIC data for the Mock Swiggy MCP.

Nothing here is real Swiggy data. Names, prices, ratings and delivery times
are invented for local development and testing only.
"""

RESTAURANTS = [
    {"id": "r-001", "name": "Demo Biryani House (Synthetic)", "cuisines": ["Biryani", "North Indian"],
     "area": "Demo Area A", "rating": 4.2, "delivery_time_min": 35, "price_for_two_inr": 500, "is_open": True},
    {"id": "r-002", "name": "Sample Dosa Corner (Synthetic)", "cuisines": ["South Indian", "Breakfast"],
     "area": "Demo Area A", "rating": 4.4, "delivery_time_min": 25, "price_for_two_inr": 250, "is_open": True},
    {"id": "r-003", "name": "Test Pizza Lab (Synthetic)", "cuisines": ["Pizza", "Italian"],
     "area": "Demo Area B", "rating": 4.0, "delivery_time_min": 40, "price_for_two_inr": 600, "is_open": True},
    {"id": "r-004", "name": "Mock Noodle Bar (Synthetic)", "cuisines": ["Chinese", "Asian"],
     "area": "Demo Area B", "rating": 3.9, "delivery_time_min": 30, "price_for_two_inr": 400, "is_open": True},
    {"id": "r-005", "name": "Fake Burger Shack (Synthetic)", "cuisines": ["Burgers", "Fast Food"],
     "area": "Demo Area C", "rating": 4.1, "delivery_time_min": 28, "price_for_two_inr": 350, "is_open": True},
    {"id": "r-006", "name": "Placeholder Sweets (Synthetic)", "cuisines": ["Desserts", "Sweets"],
     "area": "Demo Area C", "rating": 4.5, "delivery_time_min": 20, "price_for_two_inr": 200, "is_open": False},
    {"id": "r-007", "name": "Sample Hyderabadi Kitchen (Synthetic)", "cuisines": ["Biryani", "Hyderabadi"],
     "area": "Demo Area A", "rating": 4.3, "delivery_time_min": 32, "price_for_two_inr": 450, "is_open": True},
]


def _item(rid, n, name, price, veg, category, available=True):
    return {"id": f"m-{rid[2:]}-{n:02d}", "restaurant_id": rid, "name": name,
            "price_inr": price, "veg": veg, "category": category, "available": available}


MENUS = {
    "r-001": [
        _item("r-001", 1, "Chicken Dum Biryani", 280, False, "Main"),
        _item("r-001", 2, "Veg Biryani", 220, True, "Main"),
        _item("r-001", 3, "Paneer Tikka", 240, True, "Starter"),
        _item("r-001", 4, "Raita", 40, True, "Side"),
        _item("r-001", 5, "Gulab Jamun (2 pc)", 80, True, "Dessert"),
    ],
    "r-002": [
        _item("r-002", 1, "Masala Dosa", 90, True, "Main"),
        _item("r-002", 2, "Idli (3 pc)", 60, True, "Main"),
        _item("r-002", 3, "Medu Vada (2 pc)", 70, True, "Starter"),
        _item("r-002", 4, "Filter Coffee", 40, True, "Beverage"),
        _item("r-002", 5, "Rava Kesari", 60, True, "Dessert", available=False),
    ],
    "r-003": [
        _item("r-003", 1, "Margherita Pizza", 260, True, "Main"),
        _item("r-003", 2, "Pepperoni Pizza", 340, False, "Main"),
        _item("r-003", 3, "Garlic Bread", 120, True, "Side"),
        _item("r-003", 4, "Pasta Alfredo", 230, True, "Main"),
    ],
    "r-004": [
        _item("r-004", 1, "Veg Hakka Noodles", 170, True, "Main"),
        _item("r-004", 2, "Chicken Fried Rice", 200, False, "Main"),
        _item("r-004", 3, "Veg Manchurian", 160, True, "Starter"),
        _item("r-004", 4, "Spring Rolls (4 pc)", 130, True, "Starter"),
    ],
    "r-005": [
        _item("r-005", 1, "Classic Veg Burger", 120, True, "Main"),
        _item("r-005", 2, "Chicken Burger", 160, False, "Main"),
        _item("r-005", 3, "French Fries", 90, True, "Side"),
        _item("r-005", 4, "Cola", 50, True, "Beverage"),
    ],
    "r-006": [
        _item("r-006", 1, "Kaju Katli (250 g)", 300, True, "Dessert"),
        _item("r-006", 2, "Rasmalai (2 pc)", 110, True, "Dessert"),
    ],
    "r-007": [
        _item("r-007", 1, "Hyderabadi Chicken Biryani", 250, False, "Main"),
        _item("r-007", 2, "Hyderabadi Veg Biryani", 190, True, "Main"),
        _item("r-007", 3, "Mutton Biryani", 330, False, "Main"),
        _item("r-007", 4, "Mirchi Ka Salan", 60, True, "Side"),
        _item("r-007", 5, "Soft Drink (Cola)", 40, True, "Beverage"),
        _item("r-007", 6, "Double Ka Meetha", 70, True, "Dessert"),
    ],
}

DELIVERY_FEE_INR = 30  # synthetic flat fee
ORDER_CAP_INR = 1000   # mirrors the documented Builders Club cart cap so the demo behaves like the real thing

# Synthetic addresses. No phone numbers: the real API returns one per address, which is PII we never keep.
ADDRESSES = [
    {"id": "addr-001", "category": "Home", "address_line": "Flat 101, Demo Apartments, Demo Area A (Synthetic)"},
    {"id": "addr-002", "category": "Work", "address_line": "Demo Office Park, Demo Area B (Synthetic)"},
]

ORDERS = {
    "ORD-DEMO-1001": {"order_id": "ORD-DEMO-1001", "restaurant_id": "r-002", "status": "DELIVERED",
                      "items": [{"item_id": "m-002-01", "quantity": 2}], "total_inr": 210},
    "ORD-DEMO-1002": {"order_id": "ORD-DEMO-1002", "restaurant_id": "r-001", "status": "OUT_FOR_DELIVERY",
                      "items": [{"item_id": "m-001-01", "quantity": 1}, {"item_id": "m-001-04", "quantity": 1}],
                      "total_inr": 350},
}
