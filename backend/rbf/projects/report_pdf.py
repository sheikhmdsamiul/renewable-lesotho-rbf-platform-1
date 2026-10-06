"""PDF output for programme reports: programme header, and a footer with page numbers,
generation time and a confidentiality line naming the person who generated it.

(Contract PDFs keep their own "Performance-Based Agreement" header and initials box.)
"""
import html
import tempfile
import uuid
from pathlib import Path

from django.utils import timezone


def report_header(title: str) -> str:
    from rbf.tenders.pba_pdf import _brand_logo_data_uri

    return f"""
    <div style="width:100%;padding:0 24px 6px 24px;font-size:10px;color:#334155;">
      <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #cbd5e1;padding-bottom:8px;">
        <img src="{_brand_logo_data_uri(True)}" style="height:34px;" />
        <span style="font-family:Inter,Roboto,Arial,sans-serif;font-size:9px;letter-spacing:0.08em;text-transform:uppercase;color:#64748b;">
          Renewable Lesotho RBF Programme · {html.escape(title)}
        </span>
        <img src="{_brand_logo_data_uri(False)}" style="height:34px;" />
      </div>
    </div>
    """


def report_footer(viewer: str, reference: str = '') -> str:
    generated = timezone.localtime(timezone.now()).strftime('%Y-%m-%d %H:%M %Z')
    ref = f'{html.escape(reference)} · ' if reference else ''
    return f"""
    <div style="width:100%;padding:0 24px 12px 24px;font-family:Inter,Roboto,Arial,sans-serif;font-size:8.5px;color:#475569;">
      <div style="border-top:1px solid #cbd5e1;padding-top:6px;display:flex;justify-content:space-between;align-items:center;">
        <div>{ref}Confidential · generated for {html.escape(viewer)} · {html.escape(generated)}</div>
        <div>Page <span class="pageNumber"></span> of <span class="totalPages"></span></div>
      </div>
    </div>
    """


def render_report_pdf(report_html: str, *, title: str, viewer: str, reference: str = '') -> bytes:
    from rbf.tenders.pba_pdf import _render_pdf

    output = Path(tempfile.mkdtemp(prefix='report_pdf_')) / f'report_{uuid.uuid4().hex}.pdf'
    _render_pdf(report_html, output, title[:40], header_template=report_header(title), footer_template=report_footer(viewer, reference))
    return output.read_bytes()
