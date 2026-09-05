"""Read-only OOXML checks, independent of the exporter/importer. Python standard library."""
import argparse
import json
import re
import zipfile
import xml.etree.ElementTree as ET

parser = argparse.ArgumentParser()
parser.add_argument('xlsx')
parser.add_argument('--expected-shots', type=int, required=True)
parser.add_argument('--expected-seconds', type=int, required=True)
args = parser.parse_args()
ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
with zipfile.ZipFile(args.xlsx) as archive:
    shared = ET.fromstring(archive.read('xl/sharedStrings.xml')) if 'xl/sharedStrings.xml' in archive.namelist() else None
    strings = [''.join(node.itertext()) for node in shared] if shared is not None else []
    sheets = [ET.fromstring(archive.read(f'xl/worksheets/sheet{i}.xml')) for i in (1, 2)]

    def value(cell):
        v = cell.find('s:v', ns)
        if cell.get('t') == 's':
            return strings[int(v.text)]
        if cell.get('t') == 'inlineStr':
            return ''.join(cell.find('s:is', ns).itertext())
        return v.text or '' if v is not None else ''

    heights, widths, chars, newlines = [], [], [], []
    for sheet in sheets:
        assert not sheet.findall('.//s:autoFilter', ns), 'Continuation rows must stay grouped.'
        for row in sheet.findall('s:sheetData/s:row', ns):
            height = float(row.get('ht', '15'))
            heights.append(height)
            assert 0 < height <= 409.001
            assert row.get('hidden', '0') != '1'
        for column in sheet.findall('s:cols/s:col', ns):
            width = float(column.get('width', '0'))
            widths.append(width)
            assert 0 < width <= 255
        for cell in sheet.findall('.//s:c', ns):
            if cell.get('t') in ('str', 's', 'inlineStr'):
                text = value(cell)
                # Excel's capacity is conservatively checked in UTF-16 code units.
                chars.append(len(text.encode('utf-16-le')) // 2)
                newlines.append(text.count('\n'))
                assert chars[-1] <= 32767 and newlines[-1] <= 253
                assert cell.find('s:f', ns) is None, 'Authored text became a formula.'

    main = sheets[0]
    cells = main.findall('.//s:c', ns)
    header_row = next(int(re.search(r'\d+', c.get('r')).group()) for c in cells if c.get('r').startswith('D') and value(c) == '镜头时长')
    duration_cells = [c for c in cells if re.fullmatch(r'D\d+', c.get('r')) and int(c.get('r')[1:]) > header_row and c.get('t') == 'n']
    durations = [int(value(c)) for c in duration_cells]
    assert all(x > 0 for x in durations)
    assert len(durations) == args.expected_shots
    assert sum(durations) == args.expected_seconds
    formulas = {c.find('s:f', ns).text: value(c) for c in cells if c.find('s:f', ns) is not None}
    assert any(re.fullmatch(r'SUM\(D\d+:D\d+\)', f) and int(v) == args.expected_seconds for f, v in formulas.items())
    assert any(re.fullmatch(r'COUNT\(D\d+:D\d+\)', f) and int(v) == args.expected_shots for f, v in formulas.items())
    assert not any('工作续记' in value(c) for sheet in sheets for c in sheet.findall('.//s:c', ns))
    print(json.dumps({
        'shots': len(durations), 'estimated_seconds': sum(durations),
        'max_row_height_pt': max(heights), 'max_column_width': max(widths),
        'max_cell_utf16_units': max(chars), 'max_cell_newlines': max(newlines),
        'freeze_panes_saved': [bool(sheet.findall('.//s:pane', ns)) for sheet in sheets],
    }, ensure_ascii=False))
