"""Curated frozen-dessert ingredient library (functional + provenance source).

This module is the human-authored source of truth for the ingredient set a
frozen-dessert formulator actually works with. The ETL (`build_ingredients.py`)
merges each entry with a real USDA FoodData Central nutrient vector when
`fdc_id` is set (lineage preserved), and otherwise uses the curated
`nutrients_per_100g` here.

Two kinds of data live here:

1. **Nutrient vectors** — pulled from FDC Foundation Foods where a match exists
   (dairy backbone, eggs). Isolated ingredients (refined sugars, polyols,
   protein isolates, gums, oils) are not in Foundation Foods; their nutrient
   values are curated from manufacturer specification sheets and USDA SR Legacy
   composite values, and are marked `source="curated"`.

2. **Functional properties** — PAC, POD, fat/protein type, stabilizer class,
   lactose. These are frozen-dessert domain knowledge and are ALWAYS curated;
   they do not exist in any nutrition database.

Functional value references:
  - PAC (freezing-point-depression factor, sucrose = 100) and POD (relative
    sweetness, sucrose = 100): Goff & Hartel, *Ice Cream*, 7th ed., ch. 2;
    manufacturer technical bulletins for polyols/allulose.
  - Structural ingredients (fats, stabilizers, bulking agents) contribute
    negligible freezing-point depression and are set pac = 0.0, pod = 0.0.

`nutrients_per_100g` fields: energy_kcal, protein_g, fat_g, carbs_g, sugars_g,
fiber_g, sodium_mg, potassium_mg, phosphorus_mg, calcium_mg, water_g.
All values are per 100 g of the ingredient as used.
"""
from __future__ import annotations

# fmt: off
CURATED_INGREDIENTS: list[dict] = [
    # ── Dairy backbone (FDC Foundation Foods) ─────────────────────────────────
    {
        "id": "cream_heavy", "name": "Cream, heavy (36% fat)", "role": "dairy_fat",
        "fdc_id": 2346386,
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": "dairy",
                       "protein_type": "dairy_mixed", "stabilizer_class": None,
                       "lactose_g": 2.8, "allergens": ["milk"], "cost_per_kg_usd": 6.5},
    },
    {
        "id": "milk_whole", "name": "Milk, whole, 3.25% fat", "role": "dairy_base",
        "fdc_id": None,
        "nutrients_per_100g": {"energy_kcal": 61.0, "protein_g": 3.15, "fat_g": 3.25,
            "carbs_g": 4.8, "sugars_g": 5.05, "fiber_g": 0.0, "sodium_mg": 43.0,
            "potassium_mg": 150.0, "phosphorus_mg": 84.0, "calcium_mg": 113.0,
            "water_g": 88.1},
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": "dairy",
                       "protein_type": "dairy_mixed", "stabilizer_class": None,
                       "lactose_g": 4.8, "allergens": ["milk"], "cost_per_kg_usd": 1.1},
    },
    {
        "id": "milk_skim", "name": "Milk, nonfat / skim", "role": "dairy_base",
        "fdc_id": 322559,
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": None,
                       "protein_type": "dairy_mixed", "stabilizer_class": None,
                       "lactose_g": 5.0, "allergens": ["milk"], "cost_per_kg_usd": 1.0},
    },
    {
        "id": "milk_2pct", "name": "Milk, reduced fat, 2%", "role": "dairy_base",
        "fdc_id": 321359,
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": "dairy",
                       "protein_type": "dairy_mixed", "stabilizer_class": None,
                       "lactose_g": 4.9, "allergens": ["milk"], "cost_per_kg_usd": 1.05},
    },
    {
        "id": "buttermilk_lowfat", "name": "Buttermilk, low fat", "role": "dairy_base",
        "fdc_id": 2259792,
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": "dairy",
                       "protein_type": "dairy_mixed", "stabilizer_class": None,
                       "lactose_g": 4.8, "allergens": ["milk"], "cost_per_kg_usd": 1.4},
    },
    {
        "id": "butter_unsalted", "name": "Butter, unsalted", "role": "dairy_fat",
        "fdc_id": 789828,
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": "dairy",
                       "protein_type": "dairy_mixed", "stabilizer_class": None,
                       "lactose_g": 0.1, "allergens": ["milk"], "cost_per_kg_usd": 8.0},
    },
    {
        "id": "cream_cheese", "name": "Cream cheese, full fat", "role": "dairy_fat",
        "fdc_id": 2346385,
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": "dairy",
                       "protein_type": "dairy_mixed", "stabilizer_class": None,
                       "lactose_g": 3.0, "allergens": ["milk"], "cost_per_kg_usd": 7.0},
    },
    {
        "id": "nonfat_dry_milk", "name": "Nonfat dry milk (MSNF source)", "role": "dairy_solids",
        "fdc_id": None,
        "nutrients_per_100g": {"energy_kcal": 362.0, "protein_g": 36.2, "fat_g": 0.77,
            "carbs_g": 52.0, "sugars_g": 52.0, "fiber_g": 0.0, "sodium_mg": 535.0,
            "potassium_mg": 1794.0, "phosphorus_mg": 968.0, "calcium_mg": 1257.0,
            "water_g": 3.2},
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": None,
                       "protein_type": "dairy_mixed", "stabilizer_class": None,
                       "lactose_g": 51.0, "allergens": ["milk"], "cost_per_kg_usd": 4.5},
    },

    # ── Dairy proteins (curated — manufacturer spec) ──────────────────────────
    {
        "id": "whey_protein_isolate", "name": "Whey protein isolate (90%)", "role": "protein",
        "fdc_id": None,
        "nutrients_per_100g": {"energy_kcal": 360.0, "protein_g": 90.0, "fat_g": 1.0,
            "carbs_g": 1.0, "sugars_g": 1.0, "fiber_g": 0.0, "sodium_mg": 200.0,
            "potassium_mg": 500.0, "phosphorus_mg": 150.0, "calcium_mg": 500.0,
            "water_g": 5.0},
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": None,
                       "protein_type": "dairy_whey", "stabilizer_class": None,
                       "lactose_g": 0.5, "allergens": ["milk"], "cost_per_kg_usd": 22.0},
    },
    {
        "id": "micellar_casein", "name": "Micellar casein (85%)", "role": "protein",
        "fdc_id": None,
        "nutrients_per_100g": {"energy_kcal": 355.0, "protein_g": 85.0, "fat_g": 1.5,
            "carbs_g": 3.0, "sugars_g": 3.0, "fiber_g": 0.0, "sodium_mg": 150.0,
            "potassium_mg": 300.0, "phosphorus_mg": 700.0, "calcium_mg": 1400.0,
            "water_g": 5.0},
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": None,
                       "protein_type": "dairy_casein", "stabilizer_class": None,
                       "lactose_g": 1.0, "allergens": ["milk"], "cost_per_kg_usd": 20.0},
    },

    # ── Non-dairy bases & fats ────────────────────────────────────────────────
    {
        "id": "almond_milk_unsweetened", "name": "Almond milk, unsweetened", "role": "base",
        "fdc_id": 2257045,
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": "vegetable",
                       "protein_type": None, "stabilizer_class": None,
                       "lactose_g": 0.0, "allergens": ["tree_nut"], "cost_per_kg_usd": 2.0},
    },
    {
        "id": "coconut_cream", "name": "Coconut cream", "role": "base",
        "fdc_id": None,
        "nutrients_per_100g": {"energy_kcal": 330.0, "protein_g": 3.6, "fat_g": 34.7,
            "carbs_g": 6.6, "sugars_g": 2.8, "fiber_g": 2.2, "sodium_mg": 15.0,
            "potassium_mg": 325.0, "phosphorus_mg": 100.0, "calcium_mg": 11.0,
            "water_g": 54.0},
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": "coconut",
                       "protein_type": None, "stabilizer_class": None,
                       "lactose_g": 0.0, "allergens": [], "cost_per_kg_usd": 4.0},
    },
    {
        "id": "soy_protein_isolate", "name": "Soy protein isolate (90%)", "role": "protein",
        "fdc_id": None,
        "nutrients_per_100g": {"energy_kcal": 335.0, "protein_g": 88.0, "fat_g": 3.0,
            "carbs_g": 0.0, "sugars_g": 0.0, "fiber_g": 0.0, "sodium_mg": 1000.0,
            "potassium_mg": 100.0, "phosphorus_mg": 700.0, "calcium_mg": 180.0,
            "water_g": 5.0},
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": None,
                       "protein_type": "soy", "stabilizer_class": None,
                       "lactose_g": 0.0, "allergens": ["soy"], "cost_per_kg_usd": 9.0},
    },
    {
        "id": "coconut_oil", "name": "Coconut oil, refined", "role": "fat",
        "fdc_id": None,
        "nutrients_per_100g": {"energy_kcal": 892.0, "protein_g": 0.0, "fat_g": 99.1,
            "carbs_g": 0.0, "sugars_g": 0.0, "fiber_g": 0.0, "sodium_mg": 0.0,
            "potassium_mg": 0.0, "phosphorus_mg": 0.0, "calcium_mg": 0.0, "water_g": 0.1},
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": "coconut",
                       "protein_type": None, "stabilizer_class": None,
                       "lactose_g": 0.0, "allergens": [], "cost_per_kg_usd": 3.5},
    },
    {
        "id": "mct_oil", "name": "MCT oil (C8/C10)", "role": "fat",
        "fdc_id": None,
        "nutrients_per_100g": {"energy_kcal": 830.0, "protein_g": 0.0, "fat_g": 100.0,
            "carbs_g": 0.0, "sugars_g": 0.0, "fiber_g": 0.0, "sodium_mg": 0.0,
            "potassium_mg": 0.0, "phosphorus_mg": 0.0, "calcium_mg": 0.0, "water_g": 0.0},
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": "mct",
                       "protein_type": None, "stabilizer_class": None,
                       "lactose_g": 0.0, "allergens": [], "cost_per_kg_usd": 12.0},
    },

    # ── Sugars (curated) ──────────────────────────────────────────────────────
    {
        "id": "sucrose", "name": "Sucrose (table sugar)", "role": "sweetener",
        "fdc_id": None,
        "nutrients_per_100g": {"energy_kcal": 387.0, "protein_g": 0.0, "fat_g": 0.0,
            "carbs_g": 100.0, "sugars_g": 100.0, "fiber_g": 0.0, "sodium_mg": 0.0,
            "potassium_mg": 2.0, "phosphorus_mg": 0.0, "calcium_mg": 1.0, "water_g": 0.0},
        "functional": {"pac": 100.0, "pod": 100.0, "fat_type": None,
                       "protein_type": None, "stabilizer_class": None,
                       "lactose_g": 0.0, "allergens": [], "cost_per_kg_usd": 0.8},
    },
    {
        "id": "dextrose_monohydrate", "name": "Dextrose (glucose) monohydrate", "role": "sweetener",
        "fdc_id": None,
        # Monohydrate: 9 g water of crystallisation per 100 g, so 91 g is
        # anhydrous dextrose. sugars_g and energy_kcal already reflected that;
        # carbs_g was left at 100, which put 109 g of matter in 100 g.
        "nutrients_per_100g": {"energy_kcal": 368.0, "protein_g": 0.0, "fat_g": 0.0,
            "carbs_g": 91.0, "sugars_g": 91.0, "fiber_g": 0.0, "sodium_mg": 0.0,
            "potassium_mg": 0.0, "phosphorus_mg": 0.0, "calcium_mg": 0.0, "water_g": 9.0},
        "functional": {"pac": 190.0, "pod": 74.0, "fat_type": None,
                       "protein_type": None, "stabilizer_class": None,
                       "lactose_g": 0.0, "allergens": [], "cost_per_kg_usd": 1.2},
    },
    {
        "id": "fructose", "name": "Fructose (crystalline)", "role": "sweetener",
        "fdc_id": None,
        "nutrients_per_100g": {"energy_kcal": 368.0, "protein_g": 0.0, "fat_g": 0.0,
            "carbs_g": 100.0, "sugars_g": 100.0, "fiber_g": 0.0, "sodium_mg": 0.0,
            "potassium_mg": 0.0, "phosphorus_mg": 0.0, "calcium_mg": 0.0, "water_g": 0.0},
        "functional": {"pac": 190.0, "pod": 173.0, "fat_type": None,
                       "protein_type": None, "stabilizer_class": None,
                       "lactose_g": 0.0, "allergens": [], "cost_per_kg_usd": 1.8},
    },
    {
        "id": "glucose_syrup_de42", "name": "Glucose syrup, 42 DE (solids basis)", "role": "sweetener",
        "fdc_id": None,
        "nutrients_per_100g": {"energy_kcal": 380.0, "protein_g": 0.0, "fat_g": 0.0,
            "carbs_g": 95.0, "sugars_g": 40.0, "fiber_g": 0.0, "sodium_mg": 30.0,
            "potassium_mg": 5.0, "phosphorus_mg": 0.0, "calcium_mg": 0.0, "water_g": 5.0},
        "functional": {"pac": 55.0, "pod": 50.0, "fat_type": None,
                       "protein_type": None, "stabilizer_class": None,
                       "lactose_g": 0.0, "allergens": [], "cost_per_kg_usd": 1.3},
    },
    {
        "id": "maltodextrin_de10", "name": "Maltodextrin, 10 DE (bulking)", "role": "sweetener",
        "fdc_id": None,
        "nutrients_per_100g": {"energy_kcal": 380.0, "protein_g": 0.0, "fat_g": 0.0,
            "carbs_g": 95.0, "sugars_g": 6.0, "fiber_g": 0.0, "sodium_mg": 10.0,
            "potassium_mg": 5.0, "phosphorus_mg": 0.0, "calcium_mg": 0.0, "water_g": 5.0},
        "functional": {"pac": 10.0, "pod": 5.0, "fat_type": None,
                       "protein_type": None, "stabilizer_class": None,
                       "lactose_g": 0.0, "allergens": [], "cost_per_kg_usd": 1.4},
    },

    # ── Polyols & high-intensity sweeteners (curated) ─────────────────────────
    {
        "id": "erythritol", "name": "Erythritol", "role": "polyol",
        "fdc_id": None,
        "nutrients_per_100g": {"energy_kcal": 20.0, "protein_g": 0.0, "fat_g": 0.0,
            "carbs_g": 100.0, "sugars_g": 0.0, "fiber_g": 0.0, "sodium_mg": 0.0,
            "potassium_mg": 0.0, "phosphorus_mg": 0.0, "calcium_mg": 0.0, "water_g": 0.0},
        "functional": {"pac": 280.0, "pod": 65.0, "fat_type": None,
                       "protein_type": None, "stabilizer_class": None,
                       "lactose_g": 0.0, "allergens": [], "cost_per_kg_usd": 5.0},
    },
    {
        "id": "allulose", "name": "Allulose (D-psicose)", "role": "polyol",
        "fdc_id": None,
        "nutrients_per_100g": {"energy_kcal": 40.0, "protein_g": 0.0, "fat_g": 0.0,
            "carbs_g": 100.0, "sugars_g": 0.0, "fiber_g": 0.0, "sodium_mg": 0.0,
            "potassium_mg": 0.0, "phosphorus_mg": 0.0, "calcium_mg": 0.0, "water_g": 0.0},
        "functional": {"pac": 190.0, "pod": 70.0, "fat_type": None,
                       "protein_type": None, "stabilizer_class": None,
                       "lactose_g": 0.0, "allergens": [], "cost_per_kg_usd": 9.0},
    },
    {
        "id": "polydextrose", "name": "Polydextrose (bulking fiber)", "role": "bulking_fiber",
        "fdc_id": None,
        "nutrients_per_100g": {"energy_kcal": 100.0, "protein_g": 0.0, "fat_g": 0.0,
            "carbs_g": 90.0, "sugars_g": 0.0, "fiber_g": 90.0, "sodium_mg": 0.0,
            "potassium_mg": 0.0, "phosphorus_mg": 0.0, "calcium_mg": 0.0, "water_g": 4.0},
        "functional": {"pac": 10.0, "pod": 0.0, "fat_type": None,
                       "protein_type": None, "stabilizer_class": "bulking_fiber",
                       "lactose_g": 0.0, "allergens": [], "cost_per_kg_usd": 4.0},
    },
    {
        "id": "sucralose", "name": "Sucralose (high-intensity)", "role": "high_intensity",
        "fdc_id": None,
        "nutrients_per_100g": {"energy_kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0,
            "carbs_g": 0.0, "sugars_g": 0.0, "fiber_g": 0.0, "sodium_mg": 0.0,
            "potassium_mg": 0.0, "phosphorus_mg": 0.0, "calcium_mg": 0.0, "water_g": 0.0},
        "functional": {"pac": 0.0, "pod": 60000.0, "fat_type": None,
                       "protein_type": None, "stabilizer_class": None,
                       "lactose_g": 0.0, "allergens": [], "cost_per_kg_usd": 120.0},
    },

    # ── Eggs (FDC Foundation Foods) ───────────────────────────────────────────
    {
        # FDC 748236 ("Eggs, Grade A, Large, egg yolk") reports 48 nutrients
        # and not one mineral, so it built a yolk with phosphorus 0.0 — against
        # a real value near 400 mg/100 g, on the nutrient the renal ruleset
        # gates. 329596 is a Foundation Food covering the same ingredient with a
        # complete vector, which keeps macros and minerals from one record
        # rather than grafting two together.
        "id": "egg_yolk", "name": "Egg yolk, raw", "role": "egg",
        "fdc_id": 329596,
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": None,
                       "protein_type": "egg", "stabilizer_class": "emulsifier",
                       "lactose_g": 0.0, "allergens": ["egg"], "cost_per_kg_usd": 7.0},
    },
    {
        "id": "egg_whole", "name": "Egg, whole, raw", "role": "egg",
        "fdc_id": 748967,
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": None,
                       "protein_type": "egg", "stabilizer_class": "emulsifier",
                       "lactose_g": 0.0, "allergens": ["egg"], "cost_per_kg_usd": 3.5},
    },

    # ── Stabilizers, emulsifiers, mimetics (curated) ──────────────────────────
    {
        "id": "locust_bean_gum", "name": "Locust bean gum", "role": "stabilizer",
        "fdc_id": None,
        # Carbohydrate by difference: 100 - 10 water - 6 protein - 0.6 fat.
        # Was 88.0, which summed to 104.6 g per 100 g.
        "nutrients_per_100g": {"energy_kcal": 155.0, "protein_g": 6.0, "fat_g": 0.6,
            "carbs_g": 83.4, "sugars_g": 0.0, "fiber_g": 80.0, "sodium_mg": 5.0,
            "potassium_mg": 100.0, "phosphorus_mg": 0.0, "calcium_mg": 0.0, "water_g": 10.0},
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": None,
                       "protein_type": None, "stabilizer_class": "galactomannan",
                       "lactose_g": 0.0, "allergens": [], "cost_per_kg_usd": 18.0},
    },
    {
        "id": "guar_gum", "name": "Guar gum", "role": "stabilizer",
        "fdc_id": None,
        # Carbohydrate by difference: 100 - 10 water - 5 protein - 0.5 fat.
        # Was 88.0, which summed to 103.5 g per 100 g.
        "nutrients_per_100g": {"energy_kcal": 155.0, "protein_g": 5.0, "fat_g": 0.5,
            "carbs_g": 84.5, "sugars_g": 0.0, "fiber_g": 80.0, "sodium_mg": 10.0,
            "potassium_mg": 100.0, "phosphorus_mg": 0.0, "calcium_mg": 0.0, "water_g": 10.0},
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": None,
                       "protein_type": None, "stabilizer_class": "galactomannan",
                       "lactose_g": 0.0, "allergens": [], "cost_per_kg_usd": 10.0},
    },
    {
        "id": "carrageenan_lambda", "name": "Carrageenan (lambda)", "role": "stabilizer",
        "fdc_id": None,
        "nutrients_per_100g": {"energy_kcal": 80.0, "protein_g": 0.0, "fat_g": 0.0,
            "carbs_g": 20.0, "sugars_g": 0.0, "fiber_g": 20.0, "sodium_mg": 500.0,
            "potassium_mg": 200.0, "phosphorus_mg": 0.0, "calcium_mg": 0.0, "water_g": 12.0},
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": None,
                       "protein_type": None, "stabilizer_class": "carrageenan",
                       "lactose_g": 0.0, "allergens": [], "cost_per_kg_usd": 25.0},
    },
    {
        "id": "mono_diglycerides", "name": "Mono- and diglycerides", "role": "emulsifier",
        "fdc_id": None,
        "nutrients_per_100g": {"energy_kcal": 860.0, "protein_g": 0.0, "fat_g": 96.0,
            "carbs_g": 0.0, "sugars_g": 0.0, "fiber_g": 0.0, "sodium_mg": 0.0,
            "potassium_mg": 0.0, "phosphorus_mg": 0.0, "calcium_mg": 0.0, "water_g": 0.0},
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": "vegetable",
                       "protein_type": None, "stabilizer_class": "emulsifier",
                       "lactose_g": 0.0, "allergens": [], "cost_per_kg_usd": 6.0},
    },
    {
        "id": "inulin", "name": "Inulin (chicory fiber / fat mimetic)", "role": "mimetic",
        "fdc_id": None,
        "nutrients_per_100g": {"energy_kcal": 150.0, "protein_g": 0.0, "fat_g": 0.0,
            "carbs_g": 90.0, "sugars_g": 8.0, "fiber_g": 90.0, "sodium_mg": 0.0,
            "potassium_mg": 100.0, "phosphorus_mg": 0.0, "calcium_mg": 0.0, "water_g": 5.0},
        "functional": {"pac": 5.0, "pod": 10.0, "fat_type": None,
                       "protein_type": None, "stabilizer_class": "bulking_fiber",
                       "lactose_g": 0.0, "allergens": [], "cost_per_kg_usd": 6.0},
    },

    # ── Flavor / other (curated) ──────────────────────────────────────────────
    {
        "id": "cocoa_powder", "name": "Cocoa powder, natural, unsweetened", "role": "flavor",
        "fdc_id": None,
        "nutrients_per_100g": {"energy_kcal": 228.0, "protein_g": 19.6, "fat_g": 13.7,
            "carbs_g": 57.9, "sugars_g": 1.8, "fiber_g": 37.0, "sodium_mg": 21.0,
            "potassium_mg": 1524.0, "phosphorus_mg": 734.0, "calcium_mg": 128.0,
            "water_g": 3.0},
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": "vegetable",
                       "protein_type": None, "stabilizer_class": None,
                       "lactose_g": 0.0, "allergens": [], "cost_per_kg_usd": 8.0},
    },
    {
        "id": "vanilla_extract", "name": "Vanilla extract", "role": "flavor",
        "fdc_id": None,
        "nutrients_per_100g": {"energy_kcal": 288.0, "protein_g": 0.1, "fat_g": 0.1,
            "carbs_g": 12.7, "sugars_g": 12.7, "fiber_g": 0.0, "sodium_mg": 9.0,
            "potassium_mg": 148.0, "phosphorus_mg": 6.0, "calcium_mg": 11.0, "water_g": 52.6},
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": None,
                       "protein_type": None, "stabilizer_class": None,
                       "lactose_g": 0.0, "allergens": [], "cost_per_kg_usd": 40.0},
    },
    {
        "id": "salt", "name": "Salt (sodium chloride)", "role": "flavor",
        "fdc_id": None,
        "nutrients_per_100g": {"energy_kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0,
            "carbs_g": 0.0, "sugars_g": 0.0, "fiber_g": 0.0, "sodium_mg": 38758.0,
            "potassium_mg": 8.0, "phosphorus_mg": 0.0, "calcium_mg": 24.0, "water_g": 0.2},
        "functional": {"pac": 0.0, "pod": 0.0, "fat_type": None,
                       "protein_type": None, "stabilizer_class": None,
                       "lactose_g": 0.0, "allergens": [], "cost_per_kg_usd": 0.5},
    },
]
# fmt: on
