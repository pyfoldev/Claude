#!/usr/bin/env python3
"""Создание и правка документов: docx, xlsx, pptx, pdf. Вызов: docs.py create <fmt> <out>  (контент на stdin)  |  docs.py edit <path>  (JSON-массив операций на stdin)."""
import sys, json, re, os

def die(msg):
    print(msg, file=sys.stderr); sys.exit(2)

INLINE = re.compile(r'(\*\*[^*]+\*\*|\*[^*\n]+\*|`[^`\n]+`)')
def add_runs(par, text):
    from docx.shared import Pt
    for part in INLINE.split(text):
        if not part: continue
        if part.startswith('**') and part.endswith('**') and len(part) > 4: r = par.add_run(part[2:-2]); r.bold = True
        elif part.startswith('`') and part.endswith('`') and len(part) > 2: r = par.add_run(part[1:-1]); r.font.name = 'Consolas'; r.font.size = Pt(10)
        elif part.startswith('*') and part.endswith('*') and len(part) > 2: r = par.add_run(part[1:-1]); r.italic = True
        else: par.add_run(part)

def parse_table(lines):
    rows = []
    for l in lines:
        cells = [c.strip() for c in l.strip().strip('|').split('|')]
        if all(re.fullmatch(r':?-{2,}:?', c) for c in cells if c): continue
        rows.append(cells)
    return rows

def md_to_docx(doc, md, after=None):
    """Добавляет markdown в документ. after — параграф, после которого вставлять (иначе в конец)."""
    from docx.shared import Pt
    from docx.enum.text import WD_BREAK
    new = []
    lines = md.replace('\r', '').split('\n'); i = 0
    def mk(style=None):
        p = doc.add_paragraph(style=style); new.append(p); return p
    while i < len(lines):
        l = lines[i]
        if l.strip().startswith('```'):
            i += 1; code = []
            while i < len(lines) and not lines[i].strip().startswith('```'): code.append(lines[i]); i += 1
            p = mk(); r = p.add_run('\n'.join(code)); r.font.name = 'Consolas'; r.font.size = Pt(9.5)
        elif l.strip().startswith('|') and i + 1 < len(lines) and lines[i + 1].strip().startswith('|'):
            blk = []
            while i < len(lines) and lines[i].strip().startswith('|'): blk.append(lines[i]); i += 1
            rows = parse_table(blk); i -= 1
            if rows:
                t = doc.add_table(rows=len(rows), cols=max(len(r) for r in rows)); t.style = 'Table Grid'
                for ri, row in enumerate(rows):
                    for ci, c in enumerate(row):
                        cell = t.cell(ri, ci); cell.text = ''; add_runs(cell.paragraphs[0], c)
                        if ri == 0:
                            for r in cell.paragraphs[0].runs: r.bold = True
                new.append(t)
        elif re.match(r'^#{1,6}\s', l):
            lvl = len(l) - len(l.lstrip('#')); p = doc.add_heading('', level=min(lvl, 4)); add_runs(p, l.lstrip('#').strip()); new.append(p)
        elif re.match(r'^\s*[-*•]\s+', l):
            p = mk('List Bullet'); add_runs(p, re.sub(r'^\s*[-*•]\s+', '', l))
        elif re.match(r'^\s*\d+[.)]\s+', l):
            p = mk('List Number'); add_runs(p, re.sub(r'^\s*\d+[.)]\s+', '', l))
        elif l.strip() in ('---', '***', '\f'):
            p = mk(); p.add_run().add_break(WD_BREAK.PAGE)
        elif l.strip() == '':
            pass
        else:
            p = mk(); add_runs(p, l)
        i += 1
    if after is not None:   # переносим новые элементы после якоря
        anchor = after._p if hasattr(after, '_p') else after._tbl
        for el in new:
            node = el._p if hasattr(el, '_p') else el._tbl
            anchor.addnext(node); anchor = node
    return new

def create_docx(md, out):
    from docx import Document
    d = Document(); md_to_docx(d, md); d.save(out)

def create_xlsx(content, out):
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter
    wb = openpyxl.Workbook(); wb.remove(wb.active)
    try: data = json.loads(content)
    except Exception:
        import csv, io
        sample = content[:2000]; delim = ';' if sample.count(';') > sample.count(',') else ('\t' if sample.count('\t') > sample.count(',') else ',')
        data = {'sheets': [{'name': 'Лист1', 'rows': list(csv.reader(io.StringIO(content), delimiter=delim))}]}
    sheets = data['sheets'] if isinstance(data, dict) and 'sheets' in data else [{'name': 'Лист1', 'rows': data}] if isinstance(data, list) else []
    if not sheets: die('Ожидается JSON {"sheets":[{"name":..,"rows":[[..]]}]} или CSV')
    for sh in sheets:
        ws = wb.create_sheet(str(sh.get('name', 'Лист'))[:31])
        for r in sh.get('rows', []):
            row = []
            for v in r:
                if isinstance(v, str):
                    s = v.strip()
                    if re.fullmatch(r'-?\d+', s) and len(s) < 16 and not s.startswith('0') or s == '0': v = int(s)
                    elif re.fullmatch(r'-?\d+[.,]\d+', s): v = float(s.replace(',', '.'))
                row.append(v)
            ws.append(row)
        if sh.get('header', True) and ws.max_row >= 1:
            for c in ws[1]: c.font = Font(bold=True); c.fill = PatternFill('solid', fgColor='E8EAF0'); c.alignment = Alignment(vertical='center')
            ws.freeze_panes = 'A2'
        for ci in range(1, ws.max_column + 1):
            w = max((len(str(ws.cell(r, ci).value)) for r in range(1, min(ws.max_row, 200) + 1) if ws.cell(r, ci).value is not None), default=8)
            ws.column_dimensions[get_column_letter(ci)].width = min(max(10, w + 2), 60)
    wb.save(out)

def create_pptx(md, out):
    from pptx import Presentation
    from pptx.util import Inches, Pt
    pr = Presentation(); pr.slide_width = Inches(13.333); pr.slide_height = Inches(7.5)
    slides = [s for s in re.split(r'\n\s*---+\s*\n', '\n' + md.replace('\r', '') + '\n') if s.strip()]
    for k, s in enumerate(slides):
        lines = [l for l in s.strip().split('\n')]
        title = ''; body = []; notes = []
        for l in lines:
            if re.match(r'^#{1,2}\s', l) and not title: title = l.lstrip('#').strip()
            elif re.match(r'^notes?:', l, re.I): notes.append(re.sub(r'^notes?:\s*', '', l, flags=re.I))
            elif l.strip(): body.append(l)
        if k == 0 and len(body) <= 1:
            sl = pr.slides.add_slide(pr.slide_layouts[0]); sl.shapes.title.text = title or (body[0] if body else 'Презентация')
            if len(sl.placeholders) > 1: sl.placeholders[1].text = body[0] if (title and body) else ''
        else:
            sl = pr.slides.add_slide(pr.slide_layouts[1]); sl.shapes.title.text = title or f'Слайд {k + 1}'
            tf = sl.placeholders[1].text_frame; tf.clear(); first = True
            for l in body:
                lvl = (len(l) - len(l.lstrip())) // 2; txt = re.sub(r'^\s*[-*•]\s+|^\s*\d+[.)]\s+', '', l).replace('**', '')
                p = tf.paragraphs[0] if first else tf.add_paragraph(); first = False
                p.text = txt; p.level = min(lvl, 3)
                for r in p.runs: r.font.size = Pt(24 - 2 * min(lvl, 3))
        if notes: sl.notes_slide.notes_text_frame.text = '\n'.join(notes)
    pr.save(out)

def create_pdf(md, out):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Preformatted, PageBreak, ListFlowable, ListItem
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    reg = next((p for p in ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/dejavu/DejaVuSans.ttf'] if os.path.exists(p)), None)
    bold = reg.replace('DejaVuSans.ttf', 'DejaVuSans-Bold.ttf') if reg else None
    mono = reg.replace('DejaVuSans.ttf', 'DejaVuSansMono.ttf') if reg else None
    if reg:
        pdfmetrics.registerFont(TTFont('DV', reg)); pdfmetrics.registerFont(TTFont('DV-B', bold if os.path.exists(bold) else reg)); pdfmetrics.registerFont(TTFont('DV-M', mono if os.path.exists(mono) else reg))
        from reportlab.pdfbase.pdfmetrics import registerFontFamily
        registerFontFamily('DV', normal='DV', bold='DV-B', italic='DV', boldItalic='DV-B')
        base, bf, mf = 'DV', 'DV-B', 'DV-M'
    else: base, bf, mf = 'Helvetica', 'Helvetica-Bold', 'Courier'
    ss = getSampleStyleSheet()
    body = ParagraphStyle('b', parent=ss['BodyText'], fontName=base, fontSize=10.5, leading=15, spaceAfter=5)
    H = {n: ParagraphStyle(f'h{n}', parent=body, fontName=bf, fontSize=s, leading=s + 5, spaceBefore=10, spaceAfter=6) for n, s in {1: 20, 2: 16, 3: 13, 4: 11.5}.items()}
    code = ParagraphStyle('c', parent=body, fontName=mf, fontSize=8.8, leading=11.5, backColor=colors.HexColor('#F2F3F5'), borderPadding=6, spaceAfter=8)
    def inline(t):
        t = t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        t = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', t); t = re.sub(r'(?<![\w*])\*([^*\n]+)\*(?![\w*])', r'<i>\1</i>', t)
        return re.sub(r'`([^`]+)`', rf'<font name="{mf}">\1</font>', t)
    flow = []; lines = md.replace('\r', '').split('\n'); i = 0; items = []
    def flush():
        nonlocal items
        if items: flow.append(ListFlowable([ListItem(Paragraph(inline(x), body)) for x in items], bulletType='bullet', start='•', leftIndent=14)); items = []
    while i < len(lines):
        l = lines[i]
        if l.strip().startswith('```'):
            flush(); i += 1; c = []
            while i < len(lines) and not lines[i].strip().startswith('```'): c.append(lines[i]); i += 1
            flow.append(Preformatted('\n'.join(c), code))
        elif l.strip().startswith('|'):
            flush(); blk = []
            while i < len(lines) and lines[i].strip().startswith('|'): blk.append(lines[i]); i += 1
            i -= 1; rows = parse_table(blk)
            if rows:
                n = max(len(r) for r in rows); data = [[Paragraph(inline(c), body) for c in r + [''] * (n - len(r))] for r in rows]
                t = Table(data, repeatRows=1); t.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#B8BCC6')), ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E8EAF0')), ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
                flow += [t, Spacer(1, 6)]
        elif re.match(r'^#{1,6}\s', l):
            flush(); lvl = min(len(l) - len(l.lstrip('#')), 4); flow.append(Paragraph(inline(l.lstrip('#').strip()), H[lvl]))
        elif re.match(r'^\s*([-*•]|\d+[.)])\s+', l): items.append(re.sub(r'^\s*([-*•]|\d+[.)])\s+', '', l))
        elif l.strip() in ('---', '\f'): flush(); flow.append(PageBreak())
        elif l.strip() == '': flush()
        else: flush(); flow.append(Paragraph(inline(l), body))
        i += 1
    flush()
    SimpleDocTemplate(out, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm).build(flow or [Paragraph(' ', body)])

# ---------------- правка ----------------
def edit_docx(path, ops):
    from docx import Document
    d = Document(path); log = []
    def all_pars():
        for p in d.paragraphs: yield p
        for t in d.tables:
            for row in t.rows:
                for c in row.cells:
                    for p in c.paragraphs: yield p
    for op in ops:
        k = op.get('op')
        if k == 'replace':
            n = 0
            for p in all_pars():
                if op['old'] in p.text:
                    done = False
                    for r in p.runs:
                        if op['old'] in r.text: r.text = r.text.replace(op['old'], op['new']); done = True
                    if not done:    # совпадение пересекает несколько фрагментов — склеиваем текст
                        full = p.text.replace(op['old'], op['new'])
                        for r in p.runs[1:]: r.text = ''
                        if p.runs: p.runs[0].text = full
                    n += 1
            log.append(f"replace «{op['old'][:30]}»: {n} абзац(ев)")
        elif k == 'append':
            md_to_docx(d, op.get('md', op.get('text', ''))); log.append('append ok')
        elif k == 'insert_after':
            anchor = next((p for p in d.paragraphs if op['anchor'] in p.text), None)
            if anchor is None: log.append(f"insert_after: не найден «{op['anchor'][:30]}»")
            else: md_to_docx(d, op.get('md', ''), after=anchor); log.append('insert_after ok')
        elif k == 'delete_paragraph':
            n = 0
            for p in list(d.paragraphs):
                if op['contains'] in p.text: p._p.getparent().remove(p._p); n += 1
            log.append(f'delete_paragraph: {n}')
        elif k == 'set_cell':
            t = d.tables[op.get('table', 0)]; t.cell(op['row'], op['col']).text = str(op['text']); log.append('set_cell ok')
        else: log.append(f'неизвестная операция {k}')
    d.save(path); return log

def edit_xlsx(path, ops):
    import openpyxl
    wb = openpyxl.load_workbook(path); log = []
    def sh(op): return wb[op['sheet']] if op.get('sheet') in wb.sheetnames else wb.active
    for op in ops:
        k = op.get('op')
        if k == 'set': sh(op)[op['cell']] = op['value']; log.append(f"{op['cell']} = {op['value']}")
        elif k == 'append_row': sh(op).append(op['values']); log.append('строка добавлена')
        elif k == 'set_range':
            ws = sh(op); c0 = ws[op.get('start', 'A1')]
            for ri, row in enumerate(op['rows']):
                for ci, v in enumerate(row): ws.cell(c0.row + ri, c0.column + ci, v)
            log.append('диапазон записан')
        elif k == 'add_sheet':
            ws = wb.create_sheet(op['name'][:31])
            for r in op.get('rows', []): ws.append(r)
            log.append(f"лист {op['name']} добавлен")
        elif k == 'delete_sheet':
            if op['name'] in wb.sheetnames: del wb[op['name']]; log.append('лист удалён')
        elif k == 'replace':
            n = 0
            for ws in wb.worksheets:
                for row in ws.iter_rows():
                    for c in row:
                        if isinstance(c.value, str) and op['old'] in c.value: c.value = c.value.replace(op['old'], op['new']); n += 1
            log.append(f"replace: {n} ячеек")
        else: log.append(f'неизвестная операция {k}')
    wb.save(path); return log

def edit_pptx(path, ops):
    from pptx import Presentation
    from pptx.util import Pt
    pr = Presentation(path); log = []
    for op in ops:
        k = op.get('op')
        if k == 'replace':
            n = 0
            for s in pr.slides:
                for sh in s.shapes:
                    if sh.has_text_frame:
                        for p in sh.text_frame.paragraphs:
                            for r in p.runs:
                                if op['old'] in r.text: r.text = r.text.replace(op['old'], op['new']); n += 1
            log.append(f"replace: {n}")
        elif k == 'add_slide':
            sl = pr.slides.add_slide(pr.slide_layouts[1]); sl.shapes.title.text = op.get('title', '')
            tf = sl.placeholders[1].text_frame; tf.clear()
            for j, b in enumerate(op.get('bullets', [])):
                p = tf.paragraphs[0] if j == 0 else tf.add_paragraph(); p.text = str(b)
            if op.get('notes'): sl.notes_slide.notes_text_frame.text = op['notes']
            log.append('слайд добавлен')
        elif k == 'delete_slide':
            ids = pr.slides._sldIdLst; i = int(op['index']) - 1
            if 0 <= i < len(ids): pr.part.drop_rel(ids[i].rId); del ids[i]; log.append('слайд удалён')
        elif k == 'set_text':
            s = pr.slides[int(op['slide']) - 1]; shp = [x for x in s.shapes if x.has_text_frame]
            t = shp[int(op.get('shape', 0))]; t.text_frame.text = op['text']; log.append('текст заменён')
        else: log.append(f'неизвестная операция {k}')
    pr.save(path); return log

def main():
    a = sys.argv[1:]
    if len(a) >= 3 and a[0] == 'create':
        fmt, out = a[1], a[2]; data = sys.stdin.read()
        {'docx': create_docx, 'xlsx': create_xlsx, 'pptx': create_pptx, 'pdf': create_pdf}.get(fmt, lambda *_: die(f'формат {fmt} не поддерживается'))(data, out)
        print('ok')
    elif len(a) >= 2 and a[0] == 'edit':
        path = a[1]; ops = json.loads(sys.stdin.read()); ext = os.path.splitext(path)[1].lower()
        fn = {'.docx': edit_docx, '.xlsx': edit_xlsx, '.xlsm': edit_xlsx, '.pptx': edit_pptx}.get(ext)
        if not fn: die(f'правка {ext} не поддерживается (docx, xlsx, pptx; для остальных — пересоздай файл)')
        print('; '.join(fn(path, ops)))
    else: die('usage: docs.py create <fmt> <out> | edit <path>')
main()
