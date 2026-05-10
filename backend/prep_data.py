import pandas as pd
import json

df = pd.read_csv("data/food.csv")
df = df[["fdc_id", "description"]].dropna().head(1000)
foods = df.to_dict(orient="records")

with open("usda_foods.json", "w") as f:
    json.dump(foods, f, indent=2)

print(f"Exported {len(foods)} foods to usda_foods.json")
