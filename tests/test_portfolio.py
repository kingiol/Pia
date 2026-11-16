import base64
import io
import unittest
import zipfile

from pia_runtime.portfolio import parse_portfolio


class PortfolioImportTest(unittest.TestCase):
    def test_base64_xlsx_import(self):
        workbook = io.BytesIO()
        with zipfile.ZipFile(workbook, "w") as archive:
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                """<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
                <sheetData>
                  <row><c><v>symbol</v></c><c><v>quantity</v></c><c><v>avg_cost</v></c><c><v>market_value</v></c></row>
                  <row><c><v>600000.SH</v></c><c><v>10</v></c><c><v>10.5</v></c><c><v>105</v></c></row>
                </sheetData>
                </worksheet>""",
            )
        payload = {
            "encoding": "base64",
            "data": base64.b64encode(workbook.getvalue()).decode("ascii"),
        }

        result = parse_portfolio("xlsx", payload)

        self.assertEqual(result["positions"][0]["symbol"], "600000.SH")
        self.assertEqual(result["total_value"], 105.0)


if __name__ == "__main__":
    unittest.main()
