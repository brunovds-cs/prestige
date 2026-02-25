"""Generate dummy insurance claim PDFs for pipeline testing."""

from pathlib import Path

from fpdf import FPDF

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "inbound_claims"


def generate_standard_01() -> None:
    """Clean tabular layout with clearly labeled fields."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=16)
    pdf.cell(0, 12, "Insurance Claim Form", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(6)

    pdf.set_font("Helvetica", size=11)

    # Table header
    headers = ["Field", "Value"]
    col_w = [60, 120]
    pdf.set_fill_color(220, 220, 220)
    for header, w in zip(headers, col_w):
        pdf.cell(w, 10, header, border=1, fill=True)
    pdf.ln()

    # Table rows
    rows = [
        ("Policyholder Name", "Maria Santos"),
        ("Policy Number", "POL-2024-78432"),
        ("Claim Amount", "$12,500.00"),
        ("Incident Date", "2025-11-03"),
    ]
    for label, value in rows:
        pdf.cell(col_w[0], 10, label, border=1)
        pdf.cell(col_w[1], 10, value, border=1)
        pdf.ln()

    pdf.ln(8)
    pdf.set_font("Helvetica", size=10)
    pdf.multi_cell(
        0,
        6,
        "Description: Water damage to commercial property at 450 Industrial Blvd "
        "following burst pipe on November 3, 2025. Damage includes flooring, drywall, "
        "and electrical systems in the east wing.",
    )

    pdf.output(str(OUTPUT_DIR / "claim_standard_01.pdf"))


def generate_standard_02() -> None:
    """Different layout — labeled lines instead of table, same fields."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", size=14)
    pdf.cell(0, 10, "ACME Insurance - Claim Submission", new_x="LMARGIN", new_y="NEXT")
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(6)

    fields = [
        ("Policyholder:", "John Rivera"),
        ("Policy #:", "POL-2025-00193"),
        ("Total Claimed:", "$8,750.50"),
        ("Date of Incident:", "2026-01-15"),
    ]

    for label, value in fields:
        pdf.set_font("Helvetica", "B", size=11)
        pdf.cell(50, 8, label)
        pdf.set_font("Helvetica", size=11)
        pdf.cell(0, 8, value, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)
    pdf.set_font("Helvetica", size=10)
    pdf.multi_cell(
        0,
        6,
        "Claim details: Roof damage from hailstorm on January 15, 2026. "
        "Multiple sections of the warehouse roof were compromised, leading to "
        "interior water intrusion. Temporary tarping was applied on-site.",
    )

    pdf.output(str(OUTPUT_DIR / "claim_standard_02.pdf"))


def generate_messy_03() -> None:
    """Unstructured running text with data buried in paragraphs."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Courier", size=11)
    pdf.cell(0, 10, "CLAIM NOTICE", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)

    pdf.set_font("Times", size=10)
    text = (
        "To whom it may concern,\n\n"
        "I am writing to report an incident that occurred at our facility. "
        "My name is Patricia Almeida and I hold policy number POL-2023-55671 "
        "with your company. On the date of 2025-08-22, a fire broke out in "
        "the storage area of our building located at 88 Commerce Street.\n\n"
        "The fire department responded and the blaze was contained, however "
        "significant damage was sustained. We have obtained estimates from "
        "two contractors and the total cost of repairs is expected to be "
        "around $23,100.00 dollars. This includes structural repairs, "
        "replacement of inventory, and smoke damage remediation.\n\n"
        "I would appreciate a prompt review of this claim. Please contact "
        "me at (555) 012-3456 or patricia.almeida@email.com if you require "
        "additional documentation.\n\n"
        "Sincerely,\n"
        "Patricia Almeida\n"
        "Policy: POL-2023-55671\n"
        "Claim amt: $23,100"
    )
    pdf.multi_cell(0, 5, text)

    pdf.output(str(OUTPUT_DIR / "claim_messy_03.pdf"))


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generate_standard_01()
    generate_standard_02()
    generate_messy_03()
    print(f"Generated 3 claim PDFs in {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
