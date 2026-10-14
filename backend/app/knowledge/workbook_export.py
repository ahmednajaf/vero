"""Isolated local workbook renderer. No hosted calls; bounded export execution."""
import json
from base64 import b64encode
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
import xml.etree.ElementTree as ET

from app.core.config import Settings
from app.knowledge.publication import document
from app.knowledge.report_design import asset


def workbook_data(payload: dict[str, Any]) -> dict[str, Any]:
    """Publication plus presentation metadata; no changes to analytical content."""
    data = document(payload)
    data["edition"] = {"companies": payload["definition"]["companies"], "created_at": payload.get("created_at", "")}
    data["brand"] = {}
    for name, filename in {"logo": "brand/vero-wordmark.png", "clarity": "awards/clarity.png", "people": "awards/people.png", "innovation": "awards/innovation.png"}.items():
        path = asset(filename)
        if path.is_file():
            data["brand"][name] = "data:image/png;base64," + b64encode(path.read_bytes()).decode()
    return data


def add_links(content: bytes, links: list[dict[str, Any]]) -> bytes:
    """Add native OOXML links: this renderer cannot evaluate HYPERLINK formulas.

    Workbook authoring/calculation remains in Artifact Tool. This narrowly scoped
    compatibility step adds the unsupported native hyperlink feature, not formulas.
    """
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    relation = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    package = "http://schemas.openxmlformats.org/package/2006/relationships"
    from urllib.parse import urlparse
    with ZipFile(BytesIO(content)) as original:
        files = {name: original.read(name) for name in original.namelist()}
    for number in {link["sheet"] for link in links}:
        path = f"xl/worksheets/sheet{number}.xml"
        relpath = f"xl/worksheets/_rels/sheet{number}.xml.rels"
        root = ET.fromstring(files[path])
        rels = ET.fromstring(files[relpath]) if relpath in files else ET.Element(f"{{{package}}}Relationships")
        group = ET.Element(f"{{{main}}}hyperlinks")
        # SpreadsheetML child order matters in Excel even when other readers forgive it.
        tail = {"printOptions", "pageMargins", "pageSetup", "headerFooter", "rowBreaks", "colBreaks", "customProperties", "cellWatches", "ignoredErrors", "smartTags", "drawing", "legacyDrawing", "legacyDrawingHF", "picture", "oleObjects", "controls", "webPublishItems", "tableParts", "extLst"}
        position = next((i for i, child in enumerate(root) if child.tag.split("}")[-1] in tail), len(root))
        root.insert(position, group)
        existing = {r.get("Id") for r in rels}
        for i, link in enumerate(link for link in links if link["sheet"] == number):
            if "location" in link:
                ET.SubElement(group, f"{{{main}}}hyperlink", {"ref": link["cell"], "location": link["location"]})
                continue
            if urlparse(link["url"]).scheme not in {"http", "https"}:
                continue
            identifier = f"veroSource{i}"
            while identifier in existing:
                identifier += "x"
            existing.add(identifier)
            ET.SubElement(group, f"{{{main}}}hyperlink", {"ref": link["cell"], f"{{{relation}}}id": identifier})
            ET.SubElement(rels, f"{{{package}}}Relationship", {"Id": identifier, "Type": relation + "/hyperlink", "Target": link["url"], "TargetMode": "External"})
        files[path] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        files[relpath] = ET.tostring(rels, encoding="utf-8", xml_declaration=True)
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return output.getvalue()


def export_workbook(payload: dict[str, Any], settings: Settings) -> bytes:
    node, modules = settings.workbook_node, settings.workbook_modules
    if not node or not modules or not modules.is_dir():
        raise RuntimeError("workbook_renderer_not_configured")
    data = workbook_data(payload)
    with tempfile.TemporaryDirectory(prefix="vero-workbook-") as folder:
        root = Path(folder)
        shutil.copyfile(Path(__file__).with_name("workbook.mjs"), root / "workbook.mjs")
        (root / "node_modules").symlink_to(modules, target_is_directory=True)
        (root / "input.json").write_text(json.dumps(data))
        try:
            subprocess.run([str(node), str(root / "workbook.mjs"), str(root / "input.json"), str(root / "output.xlsx")],
                           check=True, capture_output=True, timeout=120, cwd=root)
        except (OSError, subprocess.SubprocessError):
            raise RuntimeError("workbook_export_failed") from None
        return add_links((root / "output.xlsx").read_bytes(), json.loads((root / "output.xlsx.links.json").read_text()))
