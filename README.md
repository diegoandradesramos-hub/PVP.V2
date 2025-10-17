# PVP La Terraza V2

Streamlit app para calcular PVP a partir de compras y recetas. Incluye lectura automática de facturas (PDF/foto) de **Europastry, DECA 1285, Perymuz, Coca‑Cola EP Iberia y P. Llinares**.

## Ejecutar
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Flujo
1. **Sube facturas** (PDF o foto). La app separa líneas por producto.
2. Revisa/edita **Ingredientes y merma** (`data/ingredients_yield.csv`).
3. Define **Recetas** (`data/recipes.csv`): producto ↔ ingredientes.
4. Ajusta **Márgenes** por sección (`data/category_margins.csv`).
5. Consulta **PVP sugerido** (con y sin IVA).

## Archivos de datos
- `data/purchases.csv` — se va rellenando al subir facturas.
- `data/ingredients_yield.csv` — rendimiento usable por ingrediente (1 = 100%).  
- `data/recipes.csv` — receta de cada producto de carta.
- `data/category_margins.csv` — margen objetivo por sección.

## Proveedores soportados (inicial)
- Europastry (panes, pizzas)
- DECA 1285 (congelados)
- Perymuz XXI (bebidas/snacks/salsas)
- Coca‑Cola European Partners Iberia (refrescos/agua)
- P. Llinares (congelados)
- + Fallback genérico

> Nota: los parsers usan heurísticas y pueden requerir ajustes ligeros para nuevos formatos.
