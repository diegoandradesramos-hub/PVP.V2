
import io, re, yaml, datetime as dt
from dataclasses import dataclass
from typing import List, Dict, Any
import pdfplumber

try:
    from PIL import Image
    import pytesseract
    import numpy as np
    import cv2
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

def load_rules(path="data/catalog_rules.yml"):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def norm_space(s: str) -> str:
    import re
    return re.sub(r"\s+", " ", s or "").strip()

def guess_supplier(text: str, rules) -> str:
    t = text.lower()
    for sup, aliases in rules.get("supplier_alias", {}).items():
        for a in aliases:
            if a in t:
                return sup
    return "desconocido"

def product_meta(desc: str, rules) -> Dict[str, Any]:
    d = (desc or "").lower()
    for rule in rules.get("product_rules", []):
        if any(w in d for w in rule.get("match", [])):
            return {
                "category": rule.get("category",""),
                "iva_rate": float(rule.get("iva_rate", 0.10)),
                "unit": rule.get("unit","ud")
            }
    return {"category":"", "iva_rate":0.10, "unit":"ud"}

def ocr_bytes(b: bytes) -> str:
    if not OCR_AVAILABLE:
        return ""
    img = Image.open(io.BytesIO(b)).convert("RGB")
    arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
    arr = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]
    txt = pytesseract.image_to_string(arr, lang="spa+eng")
    return txt

@dataclass
class LineOut:
    date: str
    supplier: str
    ingredient: str
    qty: float
    unit: str
    total_cost_gross: float
    iva_rate: float
    invoice_no: str
    notes: str

# --------- Regex por proveedor ---------
EUROPA_LINE = re.compile(
    r"^\s*(?P<code>[A-Z0-9]{3,})\s+(?P<desc>.+?)\s+(?P<cant>\d+)\s+(?P<precio>\d{1,3}[.,]\d{2})\s+(?P<importe>\d{1,3}[.,]\d{2})\s+(?P<iva>\d{1,2})"
)

DECA_LINE = re.compile(
    r"^\s*(?P<art>\d{3,})\s+(?P<desc>.+?)\s+(?P<cajas>\d{1,3}(?:[.,]\d+)?)\s+(?P<kilos>\d{1,5}[.,]\d{1,3})\s+(?P<eurkg>\d{1,3}[.,]\d{2})\s+(?P<iva>\d{1,2})\s+(?P<importe>\d{1,6}[.,]\d{2})"
)

PERYMUZ_LINE = re.compile(
    r"^\s*(?P<code>[A-Z0-9]{3,})\s+(?P<desc>.+?)\s+(?P<cajas>-?\d{1,3})\s+(?P<precio>\d{1,3}[.,]\d{2})\s+(?P<importe>-?\d{1,6}[.,]\d{2})\s+(?P<iva>\d{1,2}[.,]\d{2}|\d{1,2})"
)

COCA_LINE = re.compile(
    r"^\s*(?P<ean>\d{8,14})\s+(?P<code>\d{2,})\s+(?P<desc>.+?)\s+(?P<cant>\d{1,4})\s+(?P<precio>\d{1,3}[.,]\d{2}).*?(?P<iva>21|10)\s*$"
)

LLINARES_LINE = re.compile(
    r"^\s*(?P<code>\d{6,})\s+(?P<desc>.+?)\s+(?P<cajas>\d{1,3})\s+(?P<ud>\d{1,3})\s+(?P<kilos>\d{1,3}[.,]\d{2})\s+(?P<precio>\d{1,3}[.,]\d{3}|\d{1,3}[.,]\d{2})\s+(?P<iva>\d{1,2})\s+(?P<importe>-?\d{1,6}[.,]\d{2})"
)

def parse_date(text: str) -> str:
    m = re.search(r"(\d{2})/(\d{2})/(\d{2,4})", text)
    if m:
        d, mth, y = m.groups()
        y = y if len(y)==4 else ("20"+y)
        try:
            return f"{y}-{mth}-{d}"
        except:
            pass
    return dt.date.today().isoformat()

def parse_europastry(text: str, rules) -> List[Dict[str, Any]]:
    rows = []
    invoice_no = (re.search(r"FACTURA\s+N[º°.]?\s*(\w+)", text, re.I) or re.search(r"NUM\.\s*(\w+)", text, re.I))
    invoice_no = invoice_no.group(1) if invoice_no else ""
    iso = parse_date(text)
    for ln in text.splitlines():
        m = EUROPA_LINE.search(ln)
        if not m: 
            continue
        desc = norm_space(m.group("desc"))
        cajas = float(m.group("cant"))
        importe = float(m.group("importe").replace(",", "."))
        meta = product_meta(desc, rules)
        ubox = re.search(r"\((\d+)\s*u\)", desc.lower())
        qty = cajas * int(ubox.group(1)) if ubox else cajas
        unit = "ud" if ubox else meta["unit"]
        rows.append(LineOut(iso,"europastry",desc,float(qty),unit,importe,float(meta["iva_rate"]),invoice_no,f"cajas:{cajas}").__dict__)
    return rows

def parse_deca(text: str, rules) -> List[Dict[str, Any]]:
    rows = []
    iso = parse_date(text)
    for ln in text.splitlines():
        m = DECA_LINE.search(ln)
        if not m: 
            continue
        desc = norm_space(m.group("desc"))
        kilos = float(m.group("kilos").replace(",", "."))
        importe = float(m.group("importe").replace(",", "."))
        iva = float(m.group("iva"))/100.0 if int(m.group("iva"))>1 else float(product_meta(desc, rules)["iva_rate"])
        rows.append(LineOut(iso,"deca",desc,kilos,"kg",importe,iva,"",f"cajas:{m.group('cajas')}").__dict__)
    return rows

def parse_perymuz(text: str, rules) -> List[Dict[str, Any]]:
    rows = []
    iso = parse_date(text)
    inv = re.search(r"(?i)FACTURA\s+([A-Z0-9]+)", text)
    invoice_no = inv.group(1) if inv else ""
    for ln in text.splitlines():
        if "DESCUENTO" in ln.upper() or "Albaran" in ln or "ALBARAN" in ln:
            continue
        m = PERYMUZ_LINE.search(ln)
        if not m: 
            continue
        desc = norm_space(m.group("desc"))
        cajas = float(m.group("cajas"))
        importe = float(m.group("importe").replace(",", "."))
        iva_raw = m.group("iva").replace(",", ".")
        iva = float(iva_raw)/100.0 if float(iva_raw)>1 else float(iva_raw)
        if iva == 0: iva = product_meta(desc, rules)["iva_rate"]
        # Si aparece "C24" en la desc => caja de 24 → convertir a uds reales
        umatch = re.search(r"C(\d+)", desc.upper())
        qty = cajas * (int(umatch.group(1)) if umatch else 1)
        unit = "ud"
        rows.append(LineOut(iso,"perymuz",desc,float(qty),unit,importe,iva,invoice_no,f"cajas:{cajas}").__dict__)
    return rows

def parse_cocacola(text: str, rules) -> List[Dict[str, Any]]:
    rows = []
    iso = parse_date(text)
    for ln in text.splitlines():
        m = COCA_LINE.search(ln)
        if not m:
            continue
        desc = norm_space(m.group("desc"))
        cant = float(m.group("cant"))
        precio = float(m.group("precio").replace(",", "."))
        iva = float(m.group("iva"))/100.0
        importe = cant * precio
        # Detecta formatos (C24) → unidades reales
        umatch = re.search(r"C(\d+)", desc.upper())
        qty = cant * (int(umatch.group(1)) if umatch else 1)
        rows.append(LineOut(iso,"cocacola",desc,float(qty),"ud",round(importe,2),iva,"","").__dict__)
    return rows

def parse_llinares(text: str, rules) -> List[Dict[str, Any]]:
    rows = []
    iso = parse_date(text)
    for ln in text.splitlines():
        m = LLINARES_LINE.search(ln)
        if not m:
            continue
        desc = norm_space(m.group("desc"))
        kilos = float(m.group("kilos").replace(",", "."))
        importe = float(m.group("importe").replace(",", "."))
        iva = float(m.group("iva"))/100.0
        rows.append(LineOut(iso,"llinares",desc,kilos,"kg",importe,iva,"","cajas:"+m.group("cajas")).__dict__)
    return rows

def parse_generic(text: str, rules) -> List[Dict[str, Any]]:
    rows = []
    iso = parse_date(text)
    GENERIC = re.compile(r"(?P<desc>[A-Za-z0-9/()., -]{8,})\s+(?P<importe>-?\d{1,6}[.,]\d{2})\s+(?P<iva>4|10|21)")
    for ln in text.splitlines():
        m = GENERIC.search(ln)
        if m:
            desc = norm_space(m.group("desc"))
            iva = float(m.group("iva"))/100.0
            rows.append(LineOut(iso,"desconocido",desc,1.0,"ud",float(m.group("importe").replace(",", ".")),iva,"","auto-generic").__dict__)
    return rows

def parse_invoice_bytes(file_bytes: bytes, filename: str, rules_path="data/catalog_rules.yml") -> List[Dict[str, Any]]:
    rules = load_rules(rules_path)
    text_all = ""

    if filename.lower().endswith(".pdf"):
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page in pdf.pages:
                    text_all += (page.extract_text() or "") + "\n"
        except Exception:
            text_all = ""
    if not text_all:
        text_all = ocr_bytes(file_bytes)

    supplier = guess_supplier(text_all, rules)

    if supplier == "europastry":
        rows = parse_europastry(text_all, rules)
    elif supplier == "deca":
        rows = parse_deca(text_all, rules)
    elif supplier == "perymuz":
        rows = parse_perymuz(text_all, rules)
    elif supplier == "cocacola":
        rows = parse_cocacola(text_all, rules)
    elif supplier == "llinares":
        rows = parse_llinares(text_all, rules)
    else:
        rows = parse_generic(text_all, rules)

    return rows
