"""Builds SYNTHETIC test documents. They are NOT RMB content and must never be loaded into a demo knowledge base."""
import json
import os

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

HERE = os.path.join(os.path.dirname(__file__), "fixtures")

LAW = [
    ("Article 1: Purpose", "This synthetic law exists only to test the chatbot software. It contains no real RMB rules."),
    ("Article 2: Types of licenses", "Exploration license, mining license and quarry license are the types of license granted under this synthetic law. An exploration license authorises prospecting for minerals within a defined area. A mining license authorises the extraction of minerals. A quarry license authorises the extraction of construction materials."),
    ("Article 3: Application requirements", "An applicant for a license submits a written application to the licensing authority together with proof of identity, a description of the area and a work programme."),
    ("Article 4: Cooperatives", "Artisanal and small-scale miners may organise themselves in a cooperative. A cooperative registers with the authority before it begins operations."),
    ("Article 5: Safety training", "Every license holder shall provide safety training to workers and shall keep records of the training that was given."),
    ("Article 6: Royalty", "A royalty is payable on minerals that are sold. The rate of the royalty is set by a separate order."),
    ("Article 7: Duration", "An exploration license is valid for the period stated in the license."),
    ("Article 8: Langue", "Les licences sont accordées par l'autorité pour les activités qui sont prévues dans la loi et les demandes sont déposées par les personnes qui ont les documents."),
]
PROSPECTUS = [
    "SYNTHETIC TEST PROSPECTUS. Priority minerals in this fictional document are tin, tungsten and gold. Investors can request geological information about the fictional basin from the investment promotion team.",
    "Value addition is encouraged. Processing of minerals inside the country creates jobs and increases export value for the fictional sector described in this test document.",
]


def make():
    os.makedirs(HERE, exist_ok=True)
    c = canvas.Canvas(os.path.join(HERE, "test-law.pdf"), pagesize=A4)
    y = 800
    c.setFont("Helvetica", 10)
    c.drawString(40, y, "SYNTHETIC TEST FIXTURE: NOT RMB CONTENT"); y -= 28
    for i, (head, body) in enumerate(LAW):
        c.drawString(40, y, head)
        y -= 16
        words, line = body.split(), ""
        for w in words:
            if len(line) + len(w) > 95:
                c.drawString(40, y, line); y -= 14; line = ""
            line += w + " "
        c.drawString(40, y, line); y -= 26
        if y < 80:
            c.showPage(); c.setFont("Helvetica", 10); y = 800
    c.save()
    c = canvas.Canvas(os.path.join(HERE, "test-prospectus.pdf"), pagesize=A4)
    for t in PROSPECTUS:
        c.setFont("Helvetica", 10)
        y = 800
        line = ""
        for w in t.split():
            if len(line) + len(w) > 95:
                c.drawString(40, y, line); y -= 14; line = ""
            line += w + " "
        c.drawString(40, y, line)
        c.showPage()
    c.save()
    json.dump({"sources": [
        {"id": "test-law", "title": "SYNTHETIC TEST LAW (not RMB content)", "category": "regulatory", "kind": "pdf_articles", "url": "https://example.invalid/test-law", "owner": "Test fixture", "version": "test", "status": "unverified"},
        {"id": "test-prospectus", "title": "SYNTHETIC TEST PROSPECTUS (not RMB content)", "category": "promotion", "kind": "pdf_pages", "url": "https://example.invalid/test-prospectus", "owner": "Test fixture", "version": "test", "status": "unverified"},
    ]}, open(os.path.join(HERE, "sources_test.json"), "w"), indent=2)


if __name__ == "__main__":
    make()
    print("fixtures written")
