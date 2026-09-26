"""
Seed menu, modelled on a third-wave specialty-coffee bar (lineup in the style of Third
Wave Coffee, India). Prices are approximate and held in paise.

`prep` is the seed prep time in seconds. The live value (`prepSecEwma`) is learned from
real orders once the barista board starts moving them through the queue.
"""

# Modifier groups. `delta` is a price change in paise. The first option is the default.
MODIFIERS = {
    "size": {
        "label": "Size",
        "options": [{"id": "regular", "label": "Regular", "delta": 0},
                    {"id": "large", "label": "Large", "delta": 4000}],
    },
    "milk": {
        "label": "Milk",
        "options": [{"id": "dairy", "label": "Whole milk", "delta": 0},
                    {"id": "oat", "label": "Oat milk", "delta": 6000},
                    {"id": "almond", "label": "Almond milk", "delta": 6000},
                    {"id": "soy", "label": "Soy milk", "delta": 4000}],
    },
    "shot": {
        "label": "Extra shot",
        "options": [{"id": "none", "label": "No extra shot", "delta": 0},
                    {"id": "extra", "label": "+1 shot", "delta": 5000}],
    },
    "sweetness": {
        "label": "Sweetness",
        "options": [{"id": "regular", "label": "Regular", "delta": 0},
                    {"id": "less", "label": "Less sweet", "delta": 0},
                    {"id": "none", "label": "No sugar", "delta": 0}],
    },
    "warm": {
        "label": "Warm it up",
        "options": [{"id": "yes", "label": "Warmed", "delta": 0},
                    {"id": "no", "label": "As is", "delta": 0}],
    },
}

MILK = ["size", "milk", "shot", "sweetness"]
BLACK = ["size", "shot", "sweetness"]


def _i(id, name, category, price, prep, desc, tags, dietary, mods=()):
    return {
        "id": id, "name": name, "category": category, "price": price * 100,
        "prepSecBase": prep, "description": desc, "tags": tags,
        "dietary": dietary, "modifiers": list(mods),
    }


MENU = [
    # ---- Hot coffee ------------------------------------------------------------------
    _i("espresso", "Espresso", "hot_coffee", 170, 60,
       "A double shot of our house blend: dark chocolate, caramel and a clean finish.",
       ["hot", "strong", "black", "espresso"], ["vegan"], ["shot", "sweetness"]),
    _i("americano", "Americano", "hot_coffee", 210, 80,
       "Double espresso lengthened with hot water. Bold, smooth, no milk.",
       ["hot", "strong", "black"], ["vegan"], BLACK),
    _i("cortado", "Cortado", "hot_coffee", 220, 110,
       "Equal parts espresso and silky steamed milk. Small and punchy.",
       ["hot", "strong", "milky"], ["veg", "dairy"], MILK),
    _i("cappuccino", "Cappuccino", "hot_coffee", 240, 140,
       "Espresso with steamed milk and a thick, velvety foam cap.",
       ["hot", "milky", "classic"], ["veg", "dairy"], MILK),
    _i("flat_white", "Flat White", "hot_coffee", 250, 130,
       "Ristretto shots with thin microfoam. More coffee-forward than a latte.",
       ["hot", "strong", "milky"], ["veg", "dairy"], MILK),
    _i("cafe_latte", "Cafe Latte", "hot_coffee", 250, 140,
       "Espresso and plenty of steamed milk with a light layer of foam.",
       ["hot", "milky", "mild", "classic"], ["veg", "dairy"], MILK),
    _i("hazelnut_latte", "Hazelnut Latte", "hot_coffee", 290, 150,
       "Our latte with toasted hazelnut syrup.",
       ["hot", "milky", "sweet", "nutty"], ["veg", "dairy"], MILK),
    _i("spanish_latte", "Spanish Latte", "hot_coffee", 290, 150,
       "Espresso sweetened with condensed milk. Rich and dessert-like.",
       ["hot", "milky", "sweet"], ["veg", "dairy"], ["size", "shot"]),
    _i("mocha", "Cafe Mocha", "hot_coffee", 290, 160,
       "Espresso, dark chocolate sauce and steamed milk.",
       ["hot", "milky", "sweet", "chocolate"], ["veg", "dairy"], MILK),
    _i("irish_latte", "Irish Latte", "hot_coffee", 290, 150,
       "Latte with a non-alcoholic Irish cream syrup.",
       ["hot", "milky", "sweet"], ["veg", "dairy"], MILK),

    # ---- Manual brew -----------------------------------------------------------------
    _i("pour_over", "V60 Pour Over", "manual_brew", 280, 300,
       "Single-origin Chikmagalur beans, hand-poured. Bright, fruity, tea-like body.",
       ["hot", "black", "fruity", "single_origin", "light"], ["vegan"], ["sweetness"]),
    _i("aeropress", "AeroPress", "manual_brew", 260, 210,
       "Full-bodied immersion brew with low acidity.",
       ["hot", "black", "smooth", "single_origin"], ["vegan"], ["sweetness"]),
    _i("french_press", "French Press", "manual_brew", 260, 270,
       "Heavy-bodied, rustic cup steeped for four minutes.",
       ["hot", "black", "bold"], ["vegan"], ["sweetness"]),

    # ---- Cold coffee -----------------------------------------------------------------
    _i("cold_brew", "Classic Cold Brew", "cold_coffee", 260, 40,
       "Steeped for 18 hours. Low acid, naturally sweet, chocolatey.",
       ["iced", "black", "smooth", "strong"], ["vegan"], ["size", "sweetness"]),
    _i("vietnamese_cold_brew", "Vietnamese Cold Brew", "cold_coffee", 290, 60,
       "Cold brew over condensed milk. Sweet, strong and very refreshing.",
       ["iced", "sweet", "strong", "milky"], ["veg", "dairy"], ["size"]),
    _i("cold_brew_tonic", "Cold Brew Tonic", "cold_coffee", 290, 60,
       "Cold brew over tonic water with an orange twist. Fizzy and bright.",
       ["iced", "black", "fizzy", "citrus", "light"], ["vegan"], ["size"]),
    _i("iced_americano", "Iced Americano", "cold_coffee", 230, 70,
       "Double espresso over ice and cold water.",
       ["iced", "black", "strong"], ["vegan"], BLACK),
    _i("iced_latte", "Iced Latte", "cold_coffee", 260, 100,
       "Espresso and cold milk over ice.",
       ["iced", "milky", "mild"], ["veg", "dairy"], MILK),
    _i("iced_spanish_latte", "Iced Spanish Latte", "cold_coffee", 300, 110,
       "Espresso, condensed milk and cold milk over ice.",
       ["iced", "milky", "sweet"], ["veg", "dairy"], ["size", "shot"]),
    _i("classic_cold_coffee", "Classic Cold Coffee", "cold_coffee", 280, 140,
       "Blended espresso, milk and ice. The café-style favourite.",
       ["iced", "milky", "sweet", "blended"], ["veg", "dairy"], MILK),
    _i("caramel_frappe", "Caramel Frappé", "cold_coffee", 320, 170,
       "Blended coffee, caramel and milk, topped with caramel drizzle.",
       ["iced", "sweet", "blended", "dessert"], ["veg", "dairy"], ["size", "milk"]),
    _i("mocha_frappe", "Mocha Frappé", "cold_coffee", 320, 170,
       "Blended coffee, dark chocolate and milk with chocolate shavings.",
       ["iced", "sweet", "blended", "chocolate", "dessert"], ["veg", "dairy"], ["size", "milk"]),

    # ---- Not coffee ------------------------------------------------------------------
    _i("hot_chocolate", "Signature Hot Chocolate", "not_coffee", 260, 140,
       "70% dark chocolate melted into steamed milk.",
       ["hot", "sweet", "chocolate", "caffeine_light", "milky"], ["veg", "dairy"], ["size", "milk"]),
    _i("matcha_latte", "Iced Matcha Latte", "not_coffee", 320, 110,
       "Ceremonial-grade matcha whisked over cold milk.",
       ["iced", "earthy", "milky", "caffeine_light"], ["veg", "dairy"], ["size", "milk", "sweetness"]),
    _i("masala_chai", "Masala Chai", "not_coffee", 180, 180,
       "Assam tea simmered with ginger, cardamom and milk.",
       ["hot", "spiced", "milky", "caffeine_light"], ["veg", "dairy"], ["size", "milk", "sweetness"]),
    _i("english_breakfast", "English Breakfast Tea", "not_coffee", 180, 90,
       "A robust black tea, served with milk on the side.",
       ["hot", "tea", "caffeine_light"], ["vegan"], ["sweetness"]),
    _i("chamomile", "Chamomile Tea", "not_coffee", 200, 90,
       "Caffeine-free floral infusion. Calming, great late in the day.",
       ["hot", "tea", "caffeine_free", "light", "floral"], ["vegan"], ["sweetness"]),
    _i("peach_iced_tea", "Peach Iced Tea", "not_coffee", 240, 60,
       "Black tea shaken with peach and ice.",
       ["iced", "fruity", "tea", "light", "sweet"], ["vegan"], ["size", "sweetness"]),

    # ---- Food ------------------------------------------------------------------------
    _i("butter_croissant", "Butter Croissant", "bakery", 190, 60,
       "All-butter, flaky, baked in-house every morning.",
       ["pastry", "breakfast", "light"], ["veg", "dairy", "gluten"], ["warm"]),
    _i("almond_croissant", "Almond Croissant", "bakery", 250, 60,
       "Twice-baked croissant with almond frangipane.",
       ["pastry", "sweet", "nutty", "breakfast"], ["veg", "dairy", "gluten", "nuts", "egg"], ["warm"]),
    _i("mushroom_croissant", "Mushroom & Cheese Croissant", "savoury", 310, 150,
       "Sautéed mushrooms, cheddar and herbs in a warm croissant.",
       ["savoury", "cheesy", "breakfast"], ["veg", "dairy", "gluten"], []),
    _i("chicken_pesto_sandwich", "Chicken Pesto Sandwich", "savoury", 340, 210,
       "Grilled chicken, basil pesto, tomato and mozzarella on sourdough.",
       ["savoury", "lunch", "filling", "cheesy"], ["non_veg", "dairy", "gluten", "nuts"], []),
    _i("paneer_tikka_sandwich", "Paneer Tikka Sandwich", "savoury", 320, 210,
       "Tandoori paneer, mint mayo and pickled onions on multigrain.",
       ["savoury", "lunch", "filling", "spicy"], ["veg", "dairy", "gluten"], []),
    _i("avocado_toast", "Avocado Toast", "savoury", 360, 180,
       "Smashed avocado, chilli flakes and seeds on sourdough.",
       ["savoury", "breakfast", "healthy", "light"], ["vegan", "gluten"], []),
    _i("blueberry_muffin", "Blueberry Muffin", "bakery", 210, 20,
       "Soft muffin loaded with blueberries and a crumble top.",
       ["sweet", "breakfast", "fruity"], ["veg", "dairy", "gluten", "egg"], ["warm"]),
    _i("banana_walnut_bread", "Banana Walnut Bread", "bakery", 190, 20,
       "Moist banana loaf with toasted walnuts.",
       ["sweet", "nutty", "breakfast"], ["veg", "dairy", "gluten", "nuts", "egg"], ["warm"]),
    _i("brownie", "Dark Chocolate Brownie", "dessert", 190, 20,
       "Fudgy, dense and very chocolatey.",
       ["sweet", "chocolate", "dessert"], ["veg", "dairy", "gluten", "egg"], ["warm"]),
    _i("cheesecake", "New York Cheesecake", "dessert", 290, 20,
       "Baked cheesecake on a buttery biscuit base.",
       ["sweet", "dessert", "creamy"], ["veg", "dairy", "gluten", "egg"], []),
    _i("tiramisu", "Tiramisu", "dessert", 320, 20,
       "Espresso-soaked ladyfingers with mascarpone cream.",
       ["sweet", "dessert", "coffee", "creamy"], ["veg", "dairy", "gluten", "egg"], []),
]

CATEGORIES = [
    {"id": "hot_coffee", "label": "Hot coffee"},
    {"id": "manual_brew", "label": "Manual brew"},
    {"id": "cold_coffee", "label": "Cold coffee"},
    {"id": "not_coffee", "label": "Not coffee"},
    {"id": "bakery", "label": "Bakery"},
    {"id": "savoury", "label": "Savoury"},
    {"id": "dessert", "label": "Dessert"},
]

CAFE = {
    "id": "koramangala",
    "name": "Cafe Companion · Koramangala",
    "address": "80 Feet Road, Koramangala 4th Block, Bengaluru",
    "lat": 12.9352,
    "lng": 77.6245,
    "timezone": "Asia/Kolkata",
    # Same hours every day: 8:00-23:00 local.
    "open": "08:00",
    "close": "23:00",
    "baristasOnShift": 2,
    "etaOverheadSec": 45,
    "connectEnabled": True,
}


# Approximate nutrition per regular serving: (kcal, protein g, sugar g, sodium mg).
# Used by the dietary filter ("low-sodium, high-protein") and shown on item details.
NUTRITION = {
    "espresso": (5, 0, 0, 10), "americano": (10, 0, 0, 15), "cortado": (70, 4, 5, 55),
    "cappuccino": (120, 7, 10, 95), "flat_white": (130, 7, 10, 100), "cafe_latte": (180, 10, 15, 140),
    "hazelnut_latte": (250, 10, 30, 150), "spanish_latte": (260, 9, 34, 130), "mocha": (290, 10, 32, 160),
    "irish_latte": (240, 10, 26, 150), "pour_over": (5, 0, 0, 5), "aeropress": (5, 0, 0, 5),
    "french_press": (5, 0, 0, 5), "cold_brew": (10, 0, 0, 10), "vietnamese_cold_brew": (220, 5, 32, 90),
    "cold_brew_tonic": (90, 0, 20, 30), "iced_americano": (10, 0, 0, 15), "iced_latte": (150, 8, 12, 120),
    "iced_spanish_latte": (260, 8, 34, 130), "classic_cold_coffee": (280, 8, 36, 150),
    "caramel_frappe": (390, 7, 58, 230), "mocha_frappe": (400, 8, 56, 240), "hot_chocolate": (330, 11, 38, 180),
    "matcha_latte": (190, 8, 20, 120), "masala_chai": (150, 5, 16, 70), "english_breakfast": (5, 0, 0, 5),
    "chamomile": (2, 0, 0, 2), "peach_iced_tea": (110, 0, 26, 15), "butter_croissant": (270, 5, 6, 320),
    "almond_croissant": (430, 10, 22, 360), "mushroom_croissant": (390, 13, 4, 620),
    "chicken_pesto_sandwich": (520, 32, 5, 980), "paneer_tikka_sandwich": (490, 22, 7, 890),
    "avocado_toast": (360, 9, 3, 480), "blueberry_muffin": (410, 6, 34, 380),
    "banana_walnut_bread": (380, 6, 26, 300), "brownie": (420, 5, 38, 210),
    "cheesecake": (450, 7, 32, 340), "tiramisu": (420, 7, 30, 120),
}

# Floor plan for dine-in: id -> (label, seats, zone).
TABLES = {
    "B1": ("Bar 1", 1, "bar"), "B2": ("Bar 2", 1, "bar"), "B3": ("Bar 3", 1, "bar"), "B4": ("Bar 4", 1, "bar"),
    "T1": ("Window 1", 2, "window"), "T2": ("Window 2", 2, "window"), "T3": ("Window 3", 2, "window"),
    "T4": ("Table 4", 2, "main"), "T5": ("Table 5", 4, "main"), "T6": ("Table 6", 4, "main"),
    "T7": ("Table 7", 4, "main"), "T8": ("Garden 8", 4, "garden"), "T9": ("Garden 9", 6, "garden"),
    "T10": ("Community table", 8, "main"),
}
