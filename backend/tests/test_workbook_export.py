"""Offline XLSX structure tests. Runtime integration is opt-in and has no AI cost."""
import json
import os
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

import pytest

from app.core.config import Settings
from app.knowledge.publication import document
from app.knowledge.workbook_export import add_links, export_workbook
from app.knowledge.synthesis import award_result
from test_publication import sample_payload
from test_report_synthesis import proposal, sources, COMPANIES


def test_native_links_include_page_destinations_and_internal_references():
    stream = BytesIO()
    namespace = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    with ZipFile(stream, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('xl/worksheets/sheet1.xml', f'<worksheet xmlns="{namespace}"><sheetData/><pageMargins/></worksheet>')
    output = add_links(stream.getvalue(), [
        {'sheet': 1, 'cell': 'D6', 'location': "'Sources'!A6"},
        {'sheet': 1, 'cell': 'E6', 'url': 'https://example.com/report.pdf#page=12'},
        {'sheet': 1, 'cell': 'E7', 'url': 'javascript:bad()'},
    ])
    with ZipFile(BytesIO(output)) as archive:
        root = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        assert [e.tag.split('}')[-1] for e in root] == ['sheetData', 'hyperlinks', 'pageMargins']
        links = root.find(f'{{{namespace}}}hyperlinks')
        assert len(links) == 2
        assert links[0].get('location') == "'Sources'!A6"
        rels = ET.fromstring(archive.read('xl/worksheets/_rels/sheet1.xml.rels'))
        assert len(rels) == 1 and rels[0].get('Target').endswith('#page=12')


@pytest.mark.skipif(not os.environ.get('WORKBOOK_TEST_NODE'), reason='Set bundled workbook runtime paths for native XLSX integration')
def test_workbook_formulas_links_and_input_changes(tmp_path):
    node = Path(os.environ['WORKBOOK_TEST_NODE'])
    modules = Path(os.environ['WORKBOOK_TEST_MODULES'])
    payload = sample_payload()
    payload['sections'].append({'id': 'derive:0', 'kind': 'derive', 'result': {'awards': [award_result(proposal(), sources(), COMPANIES)]}})
    settings = Settings(workbook_node=node, workbook_modules=modules)
    output = export_workbook(payload, settings)
    path = tmp_path / 'fixture.xlsx'
    path.write_bytes(output)
    with ZipFile(BytesIO(output)) as archive:
        ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        assert not any(ET.fromstring(archive.read(n)).findall('.//m:c[@t="e"]', ns) for n in archive.namelist() if n.startswith('xl/worksheets/sheet') and n.endswith('.xml'))
        names=[s.get('name') for s in ET.fromstring(archive.read('xl/workbook.xml')).findall('m:sheets/m:sheet',ns)]
        assert names[0] == 'Cover'
        assert b'#page=12' in archive.read(f'xl/worksheets/_rels/sheet{names.index("Sources")+1}.xml.rels')
        assert any(n.startswith('xl/media/') for n in archive.namelist())
        assert ET.fromstring(archive.read('xl/worksheets/sheet1.xml')).find('m:drawing',ns) is not None
        assert any(link.get('location') == "'Comparisons'!A1" for link in ET.fromstring(archive.read('xl/worksheets/sheet1.xml')).findall('m:hyperlinks/m:hyperlink',ns))
    shutil.copyfile(Path(__file__).with_name('verify_workbook.mjs'), tmp_path / 'verify.mjs')
    (tmp_path / 'node_modules').symlink_to(modules, target_is_directory=True)
    result = subprocess.run([str(node), str(tmp_path / 'verify.mjs'), str(path)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(not os.environ.get('WORKBOOK_TEST_NODE'), reason='Bundled workbook runtime required')
def test_analytical_workbook_steps_recalculate(tmp_path):
    from test_analytical import result as analytical_result
    node, modules = Path(os.environ['WORKBOOK_TEST_NODE']), Path(os.environ['WORKBOOK_TEST_MODULES'])
    payload = sample_payload()
    data=analytical_result()
    source=data['metrics'][0]['rows'][0]['inputs'][0]['source']
    data['promises']=[dict(company_id='a',company='Fixture A',commitment='Increase representation',deadline='2030',assessment='A stated commitment.',citations=[source])]
    payload['sections'] = [dict(id='analyse',kind='analyse',title='Leadership',result=data),
        dict(id='collect',kind='collect',result=dict(facts=[dict(id='fact',company_id='a',metric='Employees',value='1,200',unit='persons',year=2025,kind='actual',population='Employees',source=source)]))]
    path=tmp_path/'analytical.xlsx'
    path.write_bytes(export_workbook(payload,Settings(workbook_node=node,workbook_modules=modules)))
    with ZipFile(path) as archive:
        ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        sheet_names=[s.get('name') for s in ET.fromstring(archive.read('xl/workbook.xml')).findall('m:sheets/m:sheet',ns)]
        assert 'Reported data' in sheet_names and 'Promises' in sheet_names
        for name in ('Reported data','Promises'):
            index=sheet_names.index(name)+1
            assert b'#page=12' in archive.read(f'xl/worksheets/_rels/sheet{index}.xml.rels')
    shutil.copyfile(Path(__file__).with_name('verify_analytical_workbook.mjs'),tmp_path/'verify.mjs')
    (tmp_path/'node_modules').symlink_to(modules,target_is_directory=True)
    result=subprocess.run([str(node),str(tmp_path/'verify.mjs'),str(path)],capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.skipif(not os.environ.get('WORKBOOK_TEST_NODE'), reason='Bundled workbook runtime required')
def test_result_unit_conversion_recalculates_in_workbook(tmp_path):
    from app.knowledge.analytical import calculate
    from test_analytical import metric, facts
    data = facts()
    data['a:leaders'].update(value='2',unit='EUR million')
    data['a:workforce'].update(value='1000000',unit='customers')
    proposal = metric(rows=[dict(company_id='a',inputs=[dict(id='spend',fact_id='a:leaders',normalised_unit='EUR million'),
        dict(id='customers',fact_id='a:workforce',normalised_unit='customers')])],
        steps=[dict(id='result',operation='divide',operands=['spend','customers'])],result_unit='EUR/customer')
    answer = calculate(proposal,data,{'a':'Fixture A'})
    payload = sample_payload()
    payload['sections'] = [dict(id='analyse',kind='analyse',result=dict(metrics=[answer],analytical_findings=[],badges=[],claims=[]))]
    settings = Settings(workbook_node=Path(os.environ['WORKBOOK_TEST_NODE']),workbook_modules=Path(os.environ['WORKBOOK_TEST_MODULES']))
    path = tmp_path/'scaled.xlsx'
    path.write_bytes(export_workbook(payload,settings))
    shutil.copyfile(Path(__file__).with_name('verify_scaled_workbook.mjs'),tmp_path/'verify.mjs')
    (tmp_path/'node_modules').symlink_to(settings.workbook_modules,target_is_directory=True)
    result = subprocess.run([str(settings.workbook_node),str(tmp_path/'verify.mjs'),str(path)],capture_output=True,text=True,timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
