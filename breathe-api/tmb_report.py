"""TMB (Texas Medical Board) CEU compliance PDF report generator using WeasyPrint."""
from datetime import datetime
from collections import defaultdict
from sqlalchemy.orm import Session
from models import User, License, CEU, Credential


def generate_tmb_report_html(user: User, licenses: list, ceus: list, credentials: list) -> str:
    """Generate HTML for the TMB CEU compliance report."""
    now = datetime.now().strftime("%B %d, %Y")
    today_iso = datetime.now().strftime("%Y-%m-%d")

    # --- CEU table rows (numbered) ---
    ceu_rows = ""
    for i, ceu in enumerate(ceus, 1):
        ceu_rows += f"""
        <tr>
            <td style="text-align:center;">{i}</td>
            <td>{ceu.title}</td>
            <td>{ceu.provider}</td>
            <td style="text-align:center;">{ceu.credits:.1f}</td>
            <td style="text-align:center;">{ceu.completion_date.strftime('%m/%d/%Y') if ceu.completion_date else ''}</td>
            <td style="text-align:center;">{ceu.category or '—'}</td>
        </tr>"""

    total_credits = sum(c.credits for c in ceus)

    # --- License info section ---
    primary_license = licenses[0] if licenses else None
    license_number = primary_license.license_number if primary_license else "—"
    license_type = primary_license.license_type if primary_license else "—"
    expiry_date = primary_license.expiry_date.strftime('%m/%d/%Y') if primary_license and primary_license.expiry_date else "—"
    cycle_years = primary_license.cycle_years if primary_license else 2
    required_ceus = primary_license.required_ceus if primary_license else 30

    license_info = ""
    for lic in licenses:
        license_info += f"""
        <tr>
            <td>{lic.state}</td>
            <td>{lic.license_type}</td>
            <td>{lic.license_number}</td>
            <td>{lic.expiry_date.strftime('%m/%d/%Y') if lic.expiry_date else ''}</td>
            <td style="text-align:center;">{lic.cycle_years}</td>
            <td style="text-align:center;">{lic.required_ceus}</td>
        </tr>"""

    # --- Category compliance summary ---
    categories = ["clinical", "safety", "ethics", "leadership"]
    category_credits = defaultdict(float)
    for ceu in ceus:
        cat = ceu.category or "clinical"
        category_credits[cat] += ceu.credits

    category_rows = ""
    for cat in categories:
        earned = category_credits.get(cat, 0.0)
        # Texas doesn't mandate specific category breakdowns, but show for professionalism
        category_rows += f"""
        <tr>
            <td style="text-transform:capitalize;">{cat}</td>
            <td style="text-align:center;">{earned:.1f}</td>
            <td style="text-align:center;">—</td>
            <td style="text-align:center;">{earned:.1f}</td>
        </tr>"""

    # Also include any categories not in the standard list
    other_cats = set(category_credits.keys()) - set(categories)
    for cat in sorted(other_cats):
        earned = category_credits[cat]
        category_rows += f"""
        <tr>
            <td style="text-transform:capitalize;">{cat}</td>
            <td style="text-align:center;">{earned:.1f}</td>
            <td style="text-align:center;">—</td>
            <td style="text-align:center;">{earned:.1f}</td>
        </tr>"""

    # --- Certificate attachment list ---
    certs_with_path = [c for c in ceus if c.certificate_path]
    if certs_with_path:
        cert_list = ""
        for c in certs_with_path:
            filename = c.certificate_path.split("/")[-1] if c.certificate_path else "—"
            date_str = c.completion_date.strftime('%m/%d/%Y') if c.completion_date else '—'
            cert_list += f"""
            <li><strong>{filename}</strong> — {c.title} ({date_str})</li>"""
    else:
        cert_list = "<li>No certificate files on file</li>"

    # --- Credentials list ---
    cred_rows = ""
    for cred in credentials:
        cred_rows += f"""
        <tr>
            <td>{cred.type}</td>
            <td>{cred.issuing_org}</td>
            <td>{cred.expiry_date.strftime('%m/%Y') if cred.expiry_date else ''}</td>
            <td style="text-align:center;">{cred.cycle_years}</td>
        </tr>"""

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        @page {{
            size: letter;
            margin: 1in;
        }}
        body {{
            font-family: 'Helvetica', 'Arial', sans-serif;
            font-size: 11pt;
            color: #333;
            line-height: 1.5;
        }}
        h1 {{
            text-align: center;
            font-size: 16pt;
            color: #1a3c5e;
            margin-bottom: 5px;
        }}
        h2 {{
            font-size: 13pt;
            color: #1a3c5e;
            border-bottom: 2px solid #1a3c5e;
            padding-bottom: 4px;
            margin-top: 25px;
            margin-bottom: 12px;
        }}
        .subtitle {{
            text-align: center;
            font-size: 11pt;
            color: #666;
            margin-bottom: 20px;
        }}
        .report-header {{
            text-align: center;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 3px double #1a3c5e;
        }}
        .report-header .agency {{
            font-size: 14pt;
            font-weight: bold;
            color: #1a3c5e;
            letter-spacing: 1px;
        }}
        .report-header .title {{
            font-size: 13pt;
            margin-top: 5px;
        }}
        .info-box {{
            background: #f5f8fa;
            border: 1px solid #d0dbe6;
            border-radius: 6px;
            padding: 12px 18px;
            margin-bottom: 20px;
        }}
        .info-box table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .info-box td {{
            padding: 3px 10px;
            font-size: 10pt;
        }}
        .info-box td:first-child {{
            font-weight: bold;
            width: 140px;
            color: #555;
        }}
        table.data {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 10px;
        }}
        table.data th {{
            background: #1a3c5e;
            color: white;
            font-size: 9.5pt;
            padding: 6px 8px;
            text-align: left;
        }}
        table.data td {{
            border: 1px solid #ccc;
            padding: 5px 8px;
            font-size: 9.5pt;
        }}
        table.data tr:nth-child(even) {{
            background: #f9fafb;
        }}
        .total-line {{
            font-weight: bold;
            font-size: 11pt;
            margin: 10px 0;
            text-align: right;
        }}
        .summary-box {{
            background: #f5f8fa;
            border: 1px solid #d0dbe6;
            border-radius: 6px;
            padding: 10px 15px;
            margin: 10px 0 20px 0;
        }}
        .summary-box table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .summary-box td {{
            padding: 4px 10px;
            font-size: 10pt;
        }}
        .summary-box td:first-child {{
            font-weight: bold;
            color: #555;
        }}
        .certificates {{
            margin-top: 10px;
            padding-left: 20px;
            font-size: 10pt;
        }}
        .certificates li {{
            margin-bottom: 4px;
        }}
        .cert-note {{
            font-size: 9pt;
            color: #666;
            font-style: italic;
            margin-top: 8px;
        }}
        .attestation {{
            margin-top: 30px;
            padding: 15px 20px;
            background: #f5f8fa;
            border: 1px solid #d0dbe6;
            border-radius: 6px;
        }}
        .attestation p {{
            font-size: 10pt;
            line-height: 1.6;
            margin-bottom: 15px;
        }}
        .signature-line {{
            margin-top: 20px;
            width: 100%;
        }}
        .sig-block {{
            display: inline-block;
            width: 45%;
            margin-top: 10px;
            vertical-align: top;
        }}
        .sig-block.right {{
            margin-left: 8%;
        }}
        .sig-line {{
            border-bottom: 1px solid #333;
            width: 90%;
            margin-bottom: 5px;
            height: 30px;
        }}
        .sig-label {{
            font-size: 9pt;
            color: #666;
        }}
        .sig-info {{
            font-size: 10pt;
            margin-top: 12px;
        }}
        .sig-info-row {{
            margin-bottom: 8px;
        }}
        .sig-info-label {{
            display: inline-block;
            font-weight: bold;
            width: 140px;
            color: #555;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 15px;
            border-top: 1px solid #ccc;
            font-size: 8.5pt;
            color: #888;
            text-align: center;
        }}
    </style>
</head>
<body>

    <div class="report-header">
        <div class="agency">Texas Medical Board</div>
        <div class="title">Continuing Education Compliance Report</div>
    </div>

    <div class="info-box">
        <table>
            <tr><td>Licensee:</td><td>{user.name}</td></tr>
            <tr><td>Email:</td><td>{user.email}</td></tr>
            <tr><td>License Number:</td><td>{license_number}</td></tr>
            <tr><td>License Type:</td><td>{license_type}</td></tr>
            <tr><td>License Expiry:</td><td>{expiry_date}</td></tr>
            <tr><td>Report Date:</td><td>{now}</td></tr>
            <tr><td>Report Period:</td><td>{cycle_years}-year renewal cycle</td></tr>
        </table>
    </div>

    <h2>License Information</h2>
    <table class="data">
        <thead>
            <tr>
                <th>State</th>
                <th>Type</th>
                <th>License #</th>
                <th>Expiry Date</th>
                <th>Cycle (yrs)</th>
                <th>Required CEUs</th>
            </tr>
        </thead>
        <tbody>
            {license_info}
        </tbody>
    </table>

    <h2>CEU Log</h2>
    <table class="data">
        <thead>
            <tr>
                <th style="width:30px;">#</th>
                <th>Course Title</th>
                <th>Provider</th>
                <th>Credits</th>
                <th>Completion Date</th>
                <th>Category</th>
            </tr>
        </thead>
        <tbody>
            {ceu_rows}
        </tbody>
    </table>
    <div class="total-line">Total CEUs Earned: {total_credits:.1f} / {required_ceus} required</div>

    <h2>Category Compliance Summary</h2>
    <table class="data">
        <thead>
            <tr>
                <th>Category</th>
                <th>Completed</th>
                <th>Required</th>
                <th>Remaining</th>
            </tr>
        </thead>
        <tbody>
            {category_rows}
        </tbody>
    </table>
    <div class="summary-box">
        <table>
            <tr><td>Total CEUs Completed:</td><td>{total_credits:.1f}</td></tr>
            <tr><td>Total CEUs Required:</td><td>{required_ceus}</td></tr>
            <tr><td>Remaining:</td><td>{max(0.0, required_ceus - total_credits):.1f}</td></tr>
            <tr><td>Renewal Cycle:</td><td>{cycle_years} years</td></tr>
        </table>
    </div>
    <p style="font-size:9pt;color:#666;font-style:italic;">
        Note: Texas requires {required_ceus} total CEUs per {cycle_years}-year renewal cycle.
        No specific category breakdown is mandated by TMB; the summary above is provided for professional reference.
    </p>

    <h2>Certifications &amp; Credentials</h2>
    <table class="data">
        <thead>
            <tr>
                <th>Credential</th>
                <th>Issuing Organization</th>
                <th>Expiry</th>
                <th>Cycle (yrs)</th>
            </tr>
        </thead>
        <tbody>
            {cred_rows}
        </tbody>
    </table>

    <h2>Certificate Attachments</h2>
    <ul class="certificates">
        {cert_list}
    </ul>
    <p class="cert-note">Certificates are attached as separate PDF files in the submission packet.</p>

    <div class="attestation">
        <p>
            <strong>Attestation:</strong> I certify that the continuing education records listed above
            are true and correct to the best of my knowledge. I understand that submission of false
            information may result in disciplinary action.
        </p>

        <div class="sig-info">
            <div class="sig-info-row">
                <span class="sig-info-label">Printed Name:</span> {user.name}
            </div>
            <div class="sig-info-row">
                <span class="sig-info-label">License Number:</span> {license_number}
            </div>
        </div>

        <div class="signature-line">
            <div class="sig-block">
                <div class="sig-line"></div>
                <div class="sig-label">Signature</div>
            </div>
            <div class="sig-block right">
                <div class="sig-line"></div>
                <div class="sig-label">Date</div>
            </div>
        </div>
    </div>

    <div class="footer">
        Generated by Breathe — RT CEU &amp; Competency Tracker<br>
        {today_iso}
    </div>
</body>
</html>
    """
    return html


def generate_tmb_pdf(user: User, licenses: list, ceus: list, credentials: list) -> bytes:
    """Generate TMB compliance PDF using WeasyPrint. Returns PDF bytes."""
    from weasyprint import HTML
    html_content = generate_tmb_report_html(user, licenses, ceus, credentials)
    pdf = HTML(string=html_content).write_pdf()
    return pdf


def generate_tmb_report(db: Session, user_id: int) -> bytes:
    """Fetch data from DB and generate full TMB report PDF."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError(f"User {user_id} not found")

    licenses = db.query(License).filter(License.user_id == user_id).all()
    ceus = db.query(CEU).filter(CEU.user_id == user_id).order_by(CEU.completion_date).all()
    credentials = db.query(Credential).filter(Credential.user_id == user_id).all()

    return generate_tmb_pdf(user, licenses, ceus, credentials)