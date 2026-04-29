import base64
import html
from datetime import datetime
from django.utils import timezone

def _svg_data_uri(svg_markup: str) -> str:
    encoded = base64.b64encode(svg_markup.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"

def get_brand_logo_data_uri(left: bool) -> str:
    if left:
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg" width="320" height="72" viewBox="0 0 320 72">
          <rect width="320" height="72" rx="14" fill="#0f4c5c"/>
          <rect x="14" y="14" width="44" height="44" rx="12" fill="#ffffff" opacity="0.18"/>
          <circle cx="36" cy="36" r="15" fill="#8ecae6"/>
          <path d="M36 18 L42 36 L36 54 L30 36 Z" fill="#ffffff"/>
          <text x="72" y="30" font-size="17" font-family="Inter, Roboto, Arial, sans-serif" font-weight="700" fill="#ffffff">Renewable Lesotho</text>
          <text x="72" y="50" font-size="11" font-family="Inter, Roboto, Arial, sans-serif" fill="#d7eef6">Results-Based Financing Digital Platform</text>
        </svg>
        """
    else:
        svg = """
        <svg xmlns="http://www.w3.org/2000/svg" width="336" height="72" viewBox="0 0 336 72">
          <rect width="336" height="72" rx="14" fill="#123b64"/>
          <rect x="16" y="16" width="42" height="40" rx="8" fill="#ffffff"/>
          <rect x="22" y="22" width="8" height="28" fill="#ef476f"/>
          <rect x="34" y="22" width="8" height="28" fill="#ffd166"/>
          <text x="72" y="30" font-size="16" font-family="Inter, Roboto, Arial, sans-serif" font-weight="700" fill="#ffffff">Department of Energy / UNDP</text>
          <text x="72" y="50" font-size="11" font-family="Inter, Roboto, Arial, sans-serif" fill="#dce7f5">Contracting authority and programme oversight</text>
        </svg>
        """
    return _svg_data_uri(" ".join(line.strip() for line in svg.splitlines()))

def get_report_base_styles():
    return """
    @page {
      size: A4;
      margin: 0;
    }
    body {
      margin: 0;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
      color: #1e293b;
      background: #ffffff;
      line-height: 1.5;
    }
    .page {
      padding: 100px 50px 80px 50px;
      box-sizing: border-box;
    }
    .header-info {
      display: flex;
      justify-content: space-between;
      margin-bottom: 30px;
      padding-bottom: 20px;
      border-bottom: 2px solid #f1f5f9;
    }
    .report-title {
      font-size: 28px;
      font-weight: 800;
      color: #0f172a;
      letter-spacing: -0.025em;
      margin: 0;
    }
    .report-meta {
      font-size: 12px;
      color: #64748b;
      margin-top: 5px;
    }
    h2 {
      font-size: 18px;
      font-weight: 700;
      color: #0f172a;
      margin: 32px 0 16px 0;
      padding-bottom: 8px;
      border-bottom: 1px solid #e2e8f0;
    }
    h3 {
      font-size: 14px;
      font-weight: 700;
      color: #334155;
      margin: 24px 0 12px 0;
    }
    p {
      font-size: 13px;
      margin: 0 0 12px 0;
    }
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 16px;
      margin-bottom: 24px;
    }
    .stat-card {
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      padding: 16px;
    }
    .stat-label {
      font-size: 11px;
      font-weight: 600;
      color: #64748b;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 4px;
    }
    .stat-value {
      font-size: 20px;
      font-weight: 700;
      color: #0f172a;
    }
    .table-container {
      margin-top: 16px;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      overflow: hidden;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }
    th {
      background: #f1f5f9;
      color: #475569;
      font-weight: 600;
      text-align: left;
      padding: 12px 16px;
      border-bottom: 1px solid #e2e8f0;
    }
    td {
      padding: 12px 16px;
      border-bottom: 1px solid #f1f5f9;
      color: #1e293b;
    }
    tr:last-child td {
      border-bottom: none;
    }
    .badge {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 9999px;
      font-size: 11px;
      font-weight: 600;
    }
    .badge-success { background: #dcfce7; color: #15803d; }
    .badge-warning { background: #fef9c3; color: #a16207; }
    .badge-danger { background: #fee2e2; color: #b91c1c; }
    .badge-info { background: #e0f2fe; color: #0369a1; }
    
    .section-box {
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 24px;
    }
    .footer-note {
      margin-top: 40px;
      font-size: 11px;
      color: #94a3b8;
      text-align: center;
      border-top: 1px solid #f1f5f9;
      padding-top: 20px;
    }
    """

def render_section(title, content_html):
    return f"""
    <div class="section-box">
      <h2 style="margin-top: 0;">{html.escape(title)}</h2>
      {content_html}
    </div>
    """

def render_table(headers, rows):
    header_html = "".join([f"<th>{html.escape(str(h))}</th>" for h in headers])
    rows_html = "".join([
        "<tr>" + "".join([f"<td>{html.escape(str(c))}</td>" for c in row]) + "</tr>"
        for row in rows
    ])
    return f"""
    <div class="table-container">
      <table>
        <thead><tr>{header_html}</tr></thead>
        <tbody>{rows_html or '<tr><td colspan="' + str(len(headers)) + '">No records found.</td></tr>'}</tbody>
      </table>
    </div>
    """

def render_kv_list(items):
    rows_html = "".join([
        f'<tr><td style="width: 200px; font-weight: 600; color: #64748b;">{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>'
        for k, v in items
    ])
    return f"""
    <div class="table-container">
      <table style="border: none;">
        <tbody>{rows_html}</tbody>
      </table>
    </div>
    """

def render_stats_grid(stats):
    cards_html = "".join([
        f"""
        <div class="stat-card">
          <div class="stat-label">{html.escape(str(s['label']))}</div>
          <div class="stat-value">{html.escape(str(s['value']))}</div>
        </div>
        """
        for s in stats
    ])
    return f'<div class="stats-grid">{cards_html}</div>'

def render_report_html(title, content_html, meta_items=None):
    left_logo = get_brand_logo_data_uri(True)
    right_logo = get_brand_logo_data_uri(False)
    
    meta_html = ""
    if meta_items:
        meta_html = " · ".join([f"<strong>{k}:</strong> {v}" for k, v in meta_items.items()])
    
    generated_at = timezone.localtime(timezone.now()).strftime('%B %d, %Y at %H:%M:%S %Z')
    
    return f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      <style>
        {get_report_base_styles()}
      </style>
      <title>{html.escape(title)}</title>
    </head>
    <body>
      <div class="page">
        <div class="header-info">
          <div>
            <h1 class="report-title">{html.escape(title)}</h1>
            <div class="report-meta">
              {meta_html}
            </div>
            <div class="report-meta">
              Generated on {generated_at}
            </div>
          </div>
          <div style="text-align: right;">
            <img src="{left_logo}" style="height: 40px; margin-bottom: 8px;" /><br/>
            <img src="{right_logo}" style="height: 40px;" />
          </div>
        </div>
        
        {content_html}
        
        <div class="footer-note">
          This is an official document generated by the Renewable Lesotho RBF Digital Platform.<br/>
          &copy; {datetime.now().year} Department of Energy, Lesotho / UNDP. All rights reserved.
        </div>
      </div>
    </body>
    </html>
    """
