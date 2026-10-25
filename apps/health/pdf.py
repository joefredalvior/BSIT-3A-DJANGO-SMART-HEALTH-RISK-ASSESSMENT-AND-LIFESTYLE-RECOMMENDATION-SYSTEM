"""Server-side PDF rendering for assessment reports."""

from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from . import engine


def _p(value):
    return Paragraph(escape(str(value or '')), getSampleStyleSheet()['BodyText'])


def build_report_pdf(record):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f'HealthWise report {record.pk}',
        author='HealthWise',
    )

    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        'TitleCustom', parent=styles['Title'], fontSize=20, leading=24,
        textColor=colors.HexColor('#111827'), spaceAfter=4,
    )
    subtitle = ParagraphStyle(
        'Subtitle', parent=styles['Normal'], fontSize=10, leading=14,
        textColor=colors.HexColor('#6b7280'), alignment=TA_CENTER,
    )
    heading = ParagraphStyle(
        'HeadingCustom', parent=styles['Heading2'], fontSize=13, leading=16,
        textColor=colors.HexColor('#0f766e'), spaceBefore=10, spaceAfter=6,
    )
    body = ParagraphStyle(
        'BodyCustom', parent=styles['BodyText'], fontSize=9.5, leading=13,
        textColor=colors.HexColor('#374151'),
    )
    small = ParagraphStyle(
        'SmallCustom', parent=body, fontSize=8, leading=11,
    )

    story = []
    story.append(Paragraph('HealthWise', title))
    story.append(Paragraph('Personal Health Risk Report', subtitle))
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width='100%', color=colors.HexColor('#d1d5db')))
    story.append(Spacer(1, 3 * mm))

    patient = record.user.get_full_name() or record.user.username
    meta = [
        ['Patient', patient, 'Completed', record.created_at.strftime('%d %b %Y, %H:%M')],
        ['Engine', f'v{record.engine_version}', 'Risk level', record.risk_level],
    ]
    meta_table = Table(meta, colWidths=[24 * mm, 58 * mm, 26 * mm, 58 * mm])
    meta_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#6b7280')),
        ('TEXTCOLOR', (2, 0), (2, -1), colors.HexColor('#6b7280')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)

    story.append(Spacer(1, 5 * mm))
    level_colour = {
        'Low': colors.HexColor('#15803d'),
        'Moderate': colors.HexColor('#b45309'),
        'High': colors.HexColor('#b91c1c'),
        'Critical': colors.HexColor('#6d28d9'),
    }.get(record.risk_level, colors.HexColor('#374151'))
    score_style = ParagraphStyle(
        'Score', parent=styles['Title'], fontSize=36, leading=40,
        textColor=level_colour, alignment=TA_CENTER,
    )
    story.append(Paragraph(f'{record.risk_score}/100', score_style))
    story.append(Paragraph(f'{record.risk_level} risk', ParagraphStyle(
        'Level', parent=subtitle, textColor=level_colour, fontSize=11,
    )))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(record.summary, body))

    projected = max(
        int(round(record.risk_score - (
            sum(rec.get('points_saved', 0) for rec in record.recommendation_list
                if rec.get('modifiable', True)) / engine.MAX_SCORE) * 100)),
        0,
    )
    if projected < record.risk_score:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(
            f'Following the recommendations could bring the score to about '
            f'<b>{projected}/100</b>.', body,
        ))

    story.append(Paragraph('Key measurements', heading))
    measurements = [
        ['Measure', 'Value', 'Category / note'],
        ['BMI', str(record.bmi or '-'), record.bmi_category or '-'],
        ['Waist-to-height ratio', str(record.whtr or '-'), record.whtr_category or '-'],
        ['Blood pressure', f'{record.systolic}/{record.diastolic}',
         record.get_blood_pressure_band_display()],
        ['Sleep', f'{record.sleep_hours} h/night', ''],
        ['Activity', record.get_activity_level_display(), ''],
        ['Smoking', record.get_smoking_status_display(), ''],
        ['Alcohol', record.get_alcohol_status_display(), ''],
        ['Diet', record.get_diet_quality_display(), ''],
    ]
    measure_table = Table(measurements, colWidths=[45 * mm, 50 * mm, 70 * mm])
    measure_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f3f4f6')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#e5e7eb')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(measure_table)

    if record.finding_list:
        story.append(Paragraph('Risk factors', heading))
        rows = [['Factor', 'Band', 'Points', 'Detail']]
        for finding in record.finding_list:
            rows.append([
                Paragraph(escape(str(finding.get('label', ''))), small),
                Paragraph(escape(str(finding.get('band', ''))), small),
                f"{finding.get('points', 0)}/{finding.get('max_points', 0)}",
                Paragraph(escape(str(finding.get('detail', ''))), small),
            ])
        finding_table = Table(rows, colWidths=[38 * mm, 28 * mm, 20 * mm, 79 * mm], repeatRows=1)
        finding_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f3f4f6')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#e5e7eb')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(finding_table)

    if record.top_recommendations:
        story.append(Paragraph('Priority recommendations', heading))
        for rec in record.top_recommendations:
            story.append(Paragraph(
                f"<b>{escape(str(rec.get('title', '')))}</b> "
                f"({escape(str(rec.get('timeframe', '')))})", body,
            ))
            story.append(Paragraph(escape(str(rec.get('advice', ''))), small))
            story.append(Paragraph(
                f"Target: {escape(str(rec.get('target', '')))} | "
                f"Potential saving: {rec.get('points_saved', 0)} points",
                small,
            ))
            story.append(Spacer(1, 2 * mm))

    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width='100%', color=colors.HexColor('#d1d5db')))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(escape(engine.MEDICAL_DISCLAIMER), small))

    def footer(canvas, doc_obj):
        canvas.saveState()
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(colors.HexColor('#9ca3af'))
        canvas.drawString(18 * mm, 9 * mm, 'HealthWise — educational screening aid')
        canvas.drawRightString(A4[0] - 18 * mm, 9 * mm, f'Page {doc_obj.page}')
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
