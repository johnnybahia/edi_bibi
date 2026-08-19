#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EDI BIBI - Gerador automático a partir de PDFs
----------------------------------------------
Uso:
  - Coloque este arquivo (edi_bibi.py) na pasta "EDI BIBI"
  - Coloque PDFs nessa mesma pasta
  - Execute:  python edi_bibi.py
"""
from __future__ import annotations
import re
import sys
import shutil
from pathlib import Path
from typing import List, Dict, Optional

# ========================= CONFIG =========================
VALOR_B_15D = "060000000000000"                 # col. 103-117 (15 dígitos)
CAMPO_MISTO_29D = "05645301000196000000000000750"  # col. 199-227 (29 dígitos)

UN_PADRAO = "MT"
TIPO_REGRA = "primeiro_02_restante_01"  # "todos_01" | "todos_02"

# ========================= UTILS ==========================
def so_digitos(s: str) -> str:
    return re.sub(r"\D+", "", s or "")

def ascii_upper(s: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", s or "")
    only = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    only_ascii = only.encode("ascii", "ignore").decode("ascii")
    return only_ascii.upper()

def yyyymmdd_from_br(date_br: str) -> Optional[str]:
    m = re.search(r"(\d{1,2})[\/\.\-](\d{1,2})[\/\.\-](\d{4})", date_br)
    if not m:
        return None
    d, mth, y = m.group(1), m.group(2), m.group(3)
    return f"{y}{int(mth):02d}{int(d):02d}"

def qtd_to_9d_implied3(q: float) -> str:
    v = int(round(q * 1000))
    return str(v).zfill(9)

def float_to_17d_implied2(valor: float) -> str:
    v = int(round(valor * 100))
    return str(v).zfill(17)

def safe_float(num_str: str) -> Optional[float]:
    if not num_str:
        return None
    s = num_str.strip().replace(",", "")
    try:
        return float(s)
    except Exception:
        return None

# ======================== PDF EXTRACT =====================
def extract_text_pdf(path: Path) -> str:
    text = ""
    try:
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            pages = []
            for p in pdf.pages:
                pages.append(p.extract_text(x_tolerance=1, y_tolerance=1) or "")
            text = "\n".join(pages)
    except Exception as e:
        print(f"[WARN] Falha ao extrair com pdfplumber em {path.name}: {e}")

    if text and len(so_digitos(text)) > 20:
        return text

    # OCR fallback opcional
    try:
        import pytesseract
        from PIL import Image
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            pages_txt = []
            for p in pdf.pages:
                im = p.to_image(resolution=300).original
                if isinstance(im, Image.Image):
                    pages_txt.append(pytesseract.image_to_string(im, lang="por"))
            text_ocr = "\n".join(pages_txt)
            if text_ocr:
                print(f"[INFO] OCR usado em {path.name}")
                return text_ocr
    except Exception as e:
        print(f"[WARN] OCR não disponível/erro em {path.name}: {e}")

    return text or ""

def parse_cnpj_comprador(text: str) -> Optional[str]:
    patterns = [
        r"C\.?\s*G\.?\s*C\.?\s*M\.?\s*F\.?.{0,20}?(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})",
        r"CNPJ.{0,20}?(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return so_digitos(m.group(1))[:14]
    m = re.search(r"(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})", text)
    if m:
        return so_digitos(m.group(1))[:14]
    return None

def parse_pedido_oc(text: str) -> Optional[str]:
    if not text:
        return None

    T_LABEL = r"(?:ORDEM\s*DE\s*COMPRA|ORDEM\s*COMPRA|OC\b|PEDIDO\b|N[º°]\s*DO\s*PEDIDO)"
    pat_right = re.compile(T_LABEL + r"[\s:\-]{0,20}([0-9]{6,9})", flags=re.IGNORECASE)
    pat_left  = re.compile(r"([0-9]{6,9})[\s:\-]{0,20}" + T_LABEL, flags=re.IGNORECASE)

    lines = text.splitlines()

    def is_noisy(line: str) -> bool:
        L = line.upper()
        return any(k in L for k in ["FONE", "TELEF", "FAX", "CEP", "CNPJ", "I.E", "IE ", "NCM"])

    for m in pat_right.finditer(text):
        num = m.group(1)
        start = text.rfind("\n", 0, m.start())
        end   = text.find("\n", m.end())
        if start == -1: start = 0
        if end   == -1: end   = len(text)
        line = text[start:end]
        if is_noisy(line):
            continue
        return num

    for m in pat_left.finditer(text):
        num = m.group(1)
        start = text.rfind("\n", 0, m.start())
        end   = text.find("\n", m.end())
        if start == -1: start = 0
        if end   == -1: end   = len(text)
        line = text[start:end]
        if is_noisy(line):
            continue
        return num

    for ln in lines:
        if is_noisy(ln):
            continue
        m = re.search(r"\b(\d{7})\b", ln)
        if m:
            return m.group(1)

    for ln in lines:
        if is_noisy(ln):
            continue
        m = re.search(r"\b(\d{6,9})\b", ln)
        if m:
            return m.group(1)

    return None

def parse_data_emissao(text: str) -> Optional[str]:
    """Extrai data de emissão do cabeçalho (âncora pela label)."""
    m = re.search(r"Data\s+Emiss[aã]o[:\s]+(\d{1,2}/\d{1,2}/\d{4})", text, re.IGNORECASE)
    if m:
        return yyyymmdd_from_br(m.group(1))
    # fallback: primeira data do documento
    m = re.search(r"(\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{4})", text)
    if m:
        return yyyymmdd_from_br(m.group(1))
    return None

# Regex para linha de item da tabela BIBI
# Formato: CODIGO(4-6d)  SEQ(1-2d)DESCRICAO  NCM/Seq  UN  1  MATERIA PRIMA  QTD  PRECO  0.00  DATA  ABERTA  0.000
_ITEM_LINE_RE = re.compile(
    r"^(\d{4,6})\s+"           # grupo 1: código do item
    r"(\d{1,2})"               # grupo 2: sequencial (Dif. Item)
    r"(.+?)"                   # grupo 3: descrição (lazy)
    r"\s+(\d{8}/\d)"           # grupo 4: NCM/Seq
    r"\s+([A-Z]{2})"           # grupo 5: unidade de medida
    r"\s+\d+"                  # agrupamento sequencial
    r"\s+MATERIA\s+PRIMA"
    r"\s+([\d,\.]+)"           # grupo 6: quantidade prevista
    r"\s+([\d\.]+)"            # grupo 7: preço unitário
    r".*?(\d{2}/\d{2}/\d{4})", # grupo 8: data de entrega
    re.IGNORECASE,
)

def parse_itens(text: str) -> List[Dict]:
    """
    Parser orientado à linha completa de item da tabela BIBI.
    Cada item ocupa uma linha com: código, seq+desc, NCM, UN, qtd, preço, data.
    Linhas de continuação de descrição (sem código no início) são ignoradas.
    """
    itens: List[Dict] = []
    for raw_ln in text.splitlines():
        ln = raw_ln.strip()
        if not ln:
            continue
        m = _ITEM_LINE_RE.match(ln)
        if not m:
            continue

        codigo   = m.group(1).zfill(6)
        seq      = m.group(2)
        desc_raw = re.sub(r"\s+", " ", m.group(3)).strip()
        ncm      = m.group(4)
        un       = m.group(5)[:2].upper()
        qtd      = safe_float(m.group(6)) or 0.0
        preco    = safe_float(m.group(7)) or 0.0
        data_fim = yyyymmdd_from_br(m.group(8))

        # Descrição no EDI: SEQ + desc_produto + NCM + UN + 1 MATERIA PRIMA
        desc_edi = ascii_upper(f"{seq}{desc_raw} {ncm} {un} 1 MATERIA PRIMA")[:75]

        if qtd == 0.0:
            print(f"[WARN] Item {codigo} com quantidade zero, ignorado.")
            continue

        itens.append({
            "CODIGO6":   codigo,
            "QTD":       qtd,
            "PRECO":     preco,
            "UN":        un,
            "DESCRICAO": desc_edi,
            "DATA_FIM":  data_fim,
        })
    return itens

# ===================== EDI BUILD =========================
def make_line(doc_base: str, tipo: str, data_ini: str, data_fim: str,
              codigo6: str, qtd_9d: str, un2: str, valor_a: str, valor_b: str,
              misto29: str, descricao: str) -> str:
    buf = [" "] * 343

    def put(a, b, s):
        s = s or ""
        w = b - a + 1
        if len(s) > w:
            s = s[:w]
        buf[a-1:b] = list(s.ljust(w))

    def put_n(a, b, s):
        s = so_digitos(str(s))
        w = b - a + 1
        if len(s) > w:
            s = s[-w:]
        buf[a-1:b] = list(s.zfill(w))

    put(41, 41, "V")
    put(100, 101, "R$")
    put(118, 119, "N0")
    put(335, 343, "000000000")

    put_n(1, 21, doc_base)
    put(25, 26, tipo)
    put(33, 40, data_ini)
    put(42, 49, data_fim)
    put_n(56, 61, codigo6)
    put_n(71, 79, qtd_9d)
    put(80, 81, (un2 or "  ")[:2])
    put_n(83, 99, valor_a)
    put(102, 102, " ")
    put_n(103, 117, valor_b)
    put_n(199, 227, misto29)
    put(260, 334, ascii_upper(descricao)[:75])

    line = "".join(buf)
    assert len(line) == 343, f"linha com {len(line)} colunas (esperado 343)"
    return line

def montar_edi_para_texto(cnpj14: str, oc_raw: str, data_ini: str, itens: List[Dict]) -> str:
    oc_digits = so_digitos(oc_raw or "")
    oc7 = (oc_digits[-7:] if len(oc_digits) >= 7 else oc_digits.zfill(7))
    doc_base = (cnpj14 + oc7)[-21:]

    lines = []
    for idx, it in enumerate(itens, start=1):
        if TIPO_REGRA == "primeiro_02_restante_01":
            tipo = "02" if idx == 1 else "01"
        elif TIPO_REGRA == "todos_02":
            tipo = "02"
        else:
            tipo = "01"

        qtd_9d        = qtd_to_9d_implied3(float(it["QTD"]))
        valor_a       = float_to_17d_implied2(float(it.get("PRECO", 0.0)))
        un2           = (it.get("UN") or UN_PADRAO)[:2]
        desc          = it.get("DESCRICAO") or f"ITEM {it.get('CODIGO6','')}"
        data_fim_item = it.get("DATA_FIM") or data_ini

        line = make_line(
            doc_base=doc_base,
            tipo=tipo,
            data_ini=data_ini,
            data_fim=data_fim_item,
            codigo6=it["CODIGO6"],
            qtd_9d=qtd_9d,
            un2=un2,
            valor_a=valor_a,
            valor_b=VALOR_B_15D,
            misto29=CAMPO_MISTO_29D,
            descricao=desc,
        )
        lines.append(line)
    return "\n".join(lines)

# ========================= PIPELINE ======================
def processar_pdf(pdf_path: Path, out_root: Path) -> Optional[Path]:
    print(f"\n[INFO] Processando: {pdf_path.name}")
    text = extract_text_pdf(pdf_path)
    if not text:
        print(f"[ERRO] Texto não extraído de {pdf_path.name}.")
        return None

    cnpj   = parse_cnpj_comprador(text)
    oc     = parse_pedido_oc(text)
    itens  = parse_itens(text)
    data_ini = parse_data_emissao(text)

    if not cnpj:
        print("[ERRO] CNPJ do comprador não encontrado.")
        return None
    if not oc:
        print("[ERRO] Nº do pedido/OC não encontrado.")
        return None
    if not itens:
        print("[ERRO] Nenhum item localizado no PDF.")
        return None
    if not data_ini:
        print("[WARN] Data de emissão não encontrada, usando 19000101.")
        data_ini = "19000101"

    edi_txt = montar_edi_para_texto(cnpj, oc, data_ini, itens)

    dest_dir = out_root / pdf_path.stem
    dest_dir.mkdir(parents=True, exist_ok=True)

    edi_path = dest_dir / f"{pdf_path.stem}.edi"
    edi_path.write_text(edi_txt, encoding="utf-8")
    print(f"[OK] EDI gerado: {edi_path}")

    dest_pdf = dest_dir / pdf_path.name
    try:
        shutil.move(str(pdf_path), str(dest_pdf))
        print(f"[OK] PDF movido para: {dest_pdf}")
    except Exception as e:
        print(f"[WARN] Não foi possível mover o PDF (copiando): {e}")
        try:
            shutil.copy2(str(pdf_path), str(dest_pdf))
            print(f"[OK] PDF copiado para: {dest_pdf}")
        except Exception as e2:
            print(f"[ERRO] Falha ao copiar o PDF: {e2}")

    return edi_path

def main():
    root = Path(".").resolve()
    print(f"[INFO] Pasta de trabalho: {root}")
    pdfs = [p for p in root.iterdir() if p.suffix.lower() == ".pdf" and p.is_file()]
    if not pdfs:
        print("[INFO] Nenhum PDF encontrado no diretório atual.")
        return

    for pdf in pdfs:
        try:
            processar_pdf(pdf, root)
        except Exception as e:
            print(f"[ERRO] Falha ao processar {pdf.name}: {e}")

if __name__ == "__main__":
    main()