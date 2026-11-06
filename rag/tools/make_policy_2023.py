"""Writes rag/data/raw/remote_work_policy_2023.pdf: an OLDER version of the sample policy (fictional, like the 2026 one).
It exists only as a test case for 'outdated version' questions: the same company, the same sections, but several facts differ.
Needs reportlab (`pip install reportlab`); the PDF is committed, so this script is only needed to change the text."""
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parents[1] / "data" / "raw" / "remote_work_policy_2023.pdf"
EFFECTIVE = "Effective 2023-03-01"

PAGES = [
    [("Remote Work Policy", None),
     ("1. Purpose", "This policy explains who may work remotely, how remote days are approved and which security rules apply to company laptops outside the office. It applies to all permanent employees of Northwind Logistics."),
     ("2. Eligibility", "Employees who have completed the probation period may work remotely up to three days per week. Warehouse and dispatch roles are not eligible, because their work requires physical presence on site. Team leads may approve exceptions for a limited period.")],
    [("3. Approval", "Remote days are requested in the HR portal at least two working days in advance. The team lead approves or declines the request within two working days. Recurring remote days are approved once per quarter."),
     ("4. Equipment", "The company provides a laptop and a headset. Employees may claim up to 25 EUR per year for a keyboard or a mouse through the expense policy. Personal computers may be used for company work after approval by the IT service desk."),
     ("5. Information security", "Company laptops must use full disk encryption. The corporate VPN is required when connected to any network outside the office; public Wi-Fi may be used only through the VPN. Lost or stolen devices are reported to the IT service desk within 24 hours.")],
    [("6. Working hours", "Core hours are from 11:00 to 15:00 Kyiv time. Employees must be reachable in the team chat during core hours and attend scheduled meetings with the camera on when requested by the organiser."),
     ("7. Review", "The policy is reviewed once every two years by HR. Questions about this policy go to hr@northwind.example.")],
]


def main():
    c = canvas.Canvas(str(OUT), pagesize=A4)
    c.setTitle("Remote Work Policy")
    w, h = A4
    left, right = 56, w - 56
    for n, page in enumerate(PAGES, start=1):
        c.setFont("Helvetica", 8)
        c.drawString(left, h - 21 - 8, "Northwind Logistics — Internal")
        c.drawRightString(right, h - 21 - 8, EFFECTIVE)
        y = h - (53 if n == 1 else 58)
        for head, body in page:
            if body is None:                                   # the document title
                c.setFont("Helvetica-Bold", 16)
                c.drawString(left, y - 16, head)
                y -= 35
                continue
            c.setFont("Helvetica-Bold", 11)
            c.drawString(left, y - 11, head)
            y -= 17
            c.setFont("Helvetica", 10)
            for line in simpleSplit(body, "Helvetica", 10, right - left):
                c.drawString(left, y - 10, line)
                y -= 13
            y -= 9
        c.setFont("Helvetica", 8)
        c.drawCentredString(w / 2, 31, f"Page {n} of {len(PAGES)}")
        c.showPage()
    c.save()
    print("written", OUT)


if __name__ == "__main__":
    main()
