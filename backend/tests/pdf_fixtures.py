"""Six deterministic synthetic fixture files, containing no real-company metrics."""

from pathlib import Path

from PIL import Image, ImageDraw
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Table, TableStyle


def build_fixtures(directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    files = {
        name: directory / f"{name}.pdf"
        for name in ("text", "multi_column", "tables", "empty", "scanned", "malformed")
    }
    text = Canvas(str(files["text"]), pagesize=(612, 792), invariant=True)
    for number in (1, 2):
        text.setFont("Helvetica-Bold", 20)
        text.drawString(50, 730, f"Fictional section {number}")
        text.bookmarkPage(f"section-{number}")
        text.addOutlineEntry(f"Fictional section {number}", f"section-{number}")
        text.setFont("Helvetica", 11)
        for line in range(20):
            text.drawString(
                50,
                680 - line * 18,
                f"PAGE_{number} line {line:02d}: Original wording remains tied to this page.",
            )
        text.drawString(300, 30, str(number))
        text.showPage()
    text.save()

    columns = Canvas(str(files["multi_column"]), pagesize=(612, 792), invariant=True)
    columns.setFont("Helvetica-Bold", 20)
    columns.drawString(50, 735, "A spanning heading across both columns")
    columns.setFont("Helvetica", 10)
    # Deliberately write in alternating stream order: geometric reading order
    # should finish the left column before starting the right, not interleave.
    for index in range(12):
        columns.drawString(
            50, 680 - index * 20, f"LEFT_{index:02d} first column sentence."
        )
        columns.drawString(
            330, 680 - index * 20, f"RIGHT_{index:02d} second column sentence."
        )
    columns.drawString(260, 50, "Footer retained")
    columns.save()

    tables = Canvas(str(files["tables"]), pagesize=(612, 792), invariant=True)
    tables.setFont("Helvetica-Bold", 18)
    tables.drawString(50, 730, "Fictional tabular data: ruled")
    cells = [
        ["Category", "2025", "2024", "Unit"],
        ["Example A", "123.4", "100.0", "test"],
        ["Example B", "7", "", "test"],
        ["Example C", "90", "80", "test"],
        ["Example D", "45", "30", "test"],
    ]
    grid = Table(cells, colWidths=[170, 80, 80, 80], rowHeights=30)
    grid.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    grid.wrapOn(tables, 500, 500)
    grid.drawOn(tables, 50, 510)
    tables.showPage()
    tables.setFont("Helvetica-Bold", 18)
    tables.drawString(50, 730, "Fictional tabular data: borderless")
    tables.setFont("Helvetica", 11)
    for index, row in enumerate(cells):
        for x, value in zip((50, 260, 360, 460), row, strict=True):
            tables.drawString(x, 670 - index * 30, value)
    tables.showPage()
    tables.setFont("Helvetica-Bold", 18)
    tables.drawString(50, 730, "Independent side-by-side tables")
    tables.setFont("Helvetica", 10)
    for x, side in ((50, "LEFT"), (330, "RIGHT")):
        for index, row in enumerate(
            [
                ["Category", "2025", "2024"],
                [f"{side} A", "123", "100"],
                [f"{side} B", "45", "40"],
                [f"{side} C", "67", "60"],
            ]
        ):
            y = 670 - index * 30
            for column, value in enumerate(row):
                tables.drawString(x + (0, 140, 195)[column], y, value)
            # Real reports often draw one horizontal rule as touching cell
            # strokes. These must join without bridging the page-column gutter.
            for left, right in ((0, 140), (140, 195), (195, 235)):
                tables.line(x + left, y - 6, x + right, y - 6)
    tables.save()

    empty = Canvas(str(files["empty"]), pagesize=(612, 792), invariant=True)
    empty.showPage()
    empty.save()
    image = Image.new("RGB", (800, 500), "white")
    ImageDraw.Draw(image).text(
        (80, 100),
        "SCANNED FIXTURE - IMAGE ONLY - NO TEXT LAYER",
        fill="black",
        font_size=24,
    )
    scanned = Canvas(str(files["scanned"]), pagesize=(612, 792), invariant=True)
    scanned.drawImage(ImageReader(image), 40, 300, width=530, height=331)
    scanned.save()
    files["malformed"].write_bytes(b"%PDF-1.7\nNot a valid PDF object structure.\n")
    return files


if __name__ == "__main__":
    import sys

    for name, path in build_fixtures(Path(sys.argv[1])).items():
        print(f"{name}: {path}")
