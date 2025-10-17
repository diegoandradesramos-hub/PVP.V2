
import streamlit as st
import pandas as pd
import numpy as np
from invoice_parser import parse_invoice_bytes
import os

st.set_page_config(page_title="PVP La Terraza V2", layout="wide")
st.title("PVP La Terraza V2")

DATA_DIR = "data"
PURCHASES = os.path.join(DATA_DIR, "purchases.csv")
YIELDS = os.path.join(DATA_DIR, "ingredients_yield.csv")
RECIPES = os.path.join(DATA_DIR, "recipes.csv")
MARGINS = os.path.join(DATA_DIR, "category_margins.csv")

@st.cache_data
def load_df(path, cols=None):
    try:
        df = pd.read_csv(path)
        if cols:
            for c in cols:
                if c not in df.columns:
                    df[c] = np.nan
        return df
    except FileNotFoundError:
        return pd.DataFrame(columns=cols or [])

def save_df(df, path):
    df.to_csv(path, index=False)

st.sidebar.header("Márgenes por sección")
margins = load_df(MARGINS, ["category","target_margin"])
st.sidebar.dataframe(margins, use_container_width=True)

# 1) Upload invoices
st.subheader("1) Subir facturas (PDF / foto)")
uploads = st.file_uploader("Arrastra PDFs/JPG/PNG (móvil ok). La app separa líneas por producto.", type=["pdf","jpg","jpeg","png"], accept_multiple_files=True)

parsed_rows = []
if uploads:
    for f in uploads:
        try:
            rows = parse_invoice_bytes(f.read(), f.name)
            parsed_rows.extend(rows)
        except Exception as e:
            st.error(f"Error leyendo {f.name}: {e}")

    if parsed_rows:
        df_new = pd.DataFrame(parsed_rows)
        st.success(f"Detectadas {len(df_new)} líneas")
        st.dataframe(df_new, use_container_width=True)
        if st.button("Añadir a Compras"):
            existing = load_df(PURCHASES, ["date","supplier","ingredient","qty","unit","total_cost_gross","iva_rate","invoice_no","notes"])
            out = pd.concat([existing, df_new], ignore_index=True)
            save_df(out, PURCHASES)
            st.success(f"Guardadas {len(df_new)} líneas en {PURCHASES}")

# 2) Ingredientes y merma
st.subheader("2) Ingredientes y merma (rendimiento usable)")
yields = load_df(YIELDS, ["ingredient","unit","usable_yield","notes"])
st.dataframe(yields, use_container_width=True)

# 3) Compras
st.subheader("3) Compras registradas")
purchases = load_df(PURCHASES, ["date","supplier","ingredient","qty","unit","total_cost_gross","iva_rate","invoice_no","notes"])
st.dataframe(purchases.tail(200), use_container_width=True)

# Cálculo: coste neto por ingrediente (último precio)
def compute_ingredient_costs(purchases: pd.DataFrame) -> pd.DataFrame:
    if purchases.empty:
        return pd.DataFrame(columns=["ingredient","unit","unit_cost_net"])
    df = purchases.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["cost_net"] = df["total_cost_gross"] / (1 + df["iva_rate"].fillna(0))
    df["unit_cost_net"] = df["cost_net"] / df["qty"].replace(0, np.nan)
    df = df.dropna(subset=["unit_cost_net"])
    # último precio por ingrediente
    df = df.sort_values("date").groupby("ingredient").tail(1)
    return df[["ingredient","unit","unit_cost_net"]].reset_index(drop=True)

ing_costs = compute_ingredient_costs(purchases)
st.subheader("4) Coste neto por ingrediente (último precio)")
st.dataframe(ing_costs, use_container_width=True)

# 5) Recetas
st.subheader("5) Recetas")
recipes = load_df(RECIPES, ["product","category","iva_rate","ingredient","qty","unit"])
st.dataframe(recipes, use_container_width=True)

# unir costes + mermas
def compute_recipe_cost(recipes, ing_costs, yields):
    if recipes.empty:
        return pd.DataFrame(columns=["product","category","iva_rate","cost_net","target_margin","pvp_sin_iva","pvp_con_iva"])
    y = yields.copy()
    y["usable_yield"] = y["usable_yield"].fillna(1.0).replace(0,1.0)
    costs = ing_costs.copy().rename(columns={"unit":"ing_unit"})
    r = recipes.merge(costs, how="left", left_on="ingredient", right_on="ingredient")
    r = r.merge(y[["ingredient","usable_yield"]], how="left", on="ingredient")
    r["usable_yield"] = r["usable_yield"].fillna(1.0)
    r["adj_qty"] = r["qty"] / r["usable_yield"]
    r["line_cost"] = r["adj_qty"] * r["unit_cost_net"]
    # total por producto
    by_prod = r.groupby(["product","category","iva_rate"], as_index=False)["line_cost"].sum()
    by_prod = by_prod.rename(columns={"line_cost":"cost_net"})
    # aplicar margen por categoría
    by_prod = by_prod.merge(margins, how="left", left_on="category", right_on="category")
    by_prod["target_margin"] = by_prod["target_margin"].fillna(0.65)
    by_prod["pvp_sin_iva"] = by_prod["cost_net"] / (1 - by_prod["target_margin"])
    by_prod["pvp_con_iva"] = by_prod["pvp_sin_iva"] * (1 + by_prod["iva_rate"].fillna(0.10))
    return by_prod

pvp = compute_recipe_cost(recipes, ing_costs, yields)
st.subheader("6) PVP sugerido")
st.dataframe(pvp, use_container_width=True)

st.caption("Tip: modifica márgenes en el panel lateral, añade compras y recetas y se recalcula al vuelo.")
