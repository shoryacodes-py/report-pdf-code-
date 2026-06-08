from pymongo import MongoClient
from bson import ObjectId
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table,
    TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import datetime

MONGO_URI = "enter db url"
DB_NAME   = "new-highscores-2"

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=8000)
db     = client[DB_NAME]

col_classrooms        = db["classrooms"]
col_classroom_members = db["classroomMembers"]
col_attempts          = db["attempts"]
col_attempt_items     = db["attemptItems"]
col_users             = db["users"]

C_HEADER_BG  = colors.HexColor("#1a1a2e")
C_INCORRECT  = colors.HexColor("#f4c2c2")
C_PARTIAL    = colors.HexColor("#fde8a0")
C_CORRECT    = colors.white
C_UNANSWERED = colors.HexColor("#e8e8e8")
C_BORDER     = colors.HexColor("#cccccc")
C_LIGHT_BG   = colors.HexColor("#f5f5f5")
C_ACCENT     = colors.HexColor("#0077b6")
C_WHITE      = colors.white
C_BLACK      = colors.black

ss = getSampleStyleSheet()

S_TITLE   = ParagraphStyle("ti", parent=ss["Normal"], fontSize=18,
                            textColor=C_WHITE, fontName="Helvetica-Bold",
                            alignment=TA_CENTER)
S_SUBHEAD = ParagraphStyle("sh", parent=ss["Normal"], fontSize=10,
                            textColor=C_BLACK, fontName="Helvetica-Bold")
S_BODY    = ParagraphStyle("bo", parent=ss["Normal"], fontSize=8,
                            textColor=C_BLACK, fontName="Helvetica")
S_BODY_C  = ParagraphStyle("bc", parent=ss["Normal"], fontSize=8,
                            textColor=C_BLACK, fontName="Helvetica",
                            alignment=TA_CENTER)
S_SMALL   = ParagraphStyle("sm", parent=ss["Normal"], fontSize=7,
                            textColor=C_BLACK, fontName="Helvetica",
                            alignment=TA_CENTER)
S_FOOTER  = ParagraphStyle("fo", parent=ss["Normal"], fontSize=7,
                            textColor=colors.grey, fontName="Helvetica",
                            alignment=TA_CENTER)


def grade_label(score, max_score):
    if max_score == 0: return "N/A"
    p = score / max_score * 100
    if p >= 90: return "A+"
    if p >= 80: return "A"
    if p >= 70: return "B"
    if p >= 60: return "C"
    if p >= 50: return "D"
    return "F"

def cell_color(obtained, actual, is_missed):
    if is_missed:              return C_UNANSWERED
    if obtained >= actual > 0: return C_CORRECT
    if obtained > 0:           return C_PARTIAL
    return C_INCORRECT

def fmt_date(d):
    if isinstance(d, datetime.datetime):
        return d.strftime("%d %b %Y")
    return str(d)[:10] if d else "—"

def get_attempt_items_dict(attempt_id):
    items = list(col_attempt_items.find({"attemptId": attempt_id}))
    return {item.get("questionIndex", i): item for i, item in enumerate(items)}

def get_one_evaluated_attempt():
    return col_attempts.find_one({
        "status": "evaluated",
        "userRole": "student",
        "totalQuestions": {"$gt": 0},
        "studentName": {"$exists": True, "$ne": None},
    })

def get_best_classroom():
    pipeline = [
        {"$match": {"role": "student", "status": "active"}},
        {"$group": {"_id": "$classroomId", "count": {"$sum": 1}}},
        {"$match": {"count": {"$gte": 3}}},
        {"$sort":  {"count": -1}},
        {"$limit": 1},
    ]
    result = list(col_classroom_members.aggregate(pipeline))
    if not result: return None, None
    cid = result[0]["_id"]
    return col_classrooms.find_one({"_id": cid}), cid

def get_common_assessment(classroom_id):
    members  = list(col_classroom_members.find(
        {"classroomId": classroom_id, "role": "student", "status": "active"}))
    user_ids = [m["userId"] for m in members]
    pipeline = [
        {"$match": {"userId": {"$in": user_ids}, "status": "evaluated",
                    "totalQuestions": {"$gt": 0}}},
        {"$group": {"_id": "$assessmentId", "count": {"$sum": 1}}},
        {"$sort":  {"count": -1}},
        {"$limit": 1},
    ]
    res = list(col_attempts.aggregate(pipeline))
    return res[0]["_id"] if res else None


def build_student_report(output_path):
    print("\n[Report 1] Fetching data ...")

    attempt = get_one_evaluated_attempt()
    if not attempt:
        print("  No evaluated attempt found."); return

    student_name  = attempt.get("studentName", "Unknown")
    student_email = attempt.get("email", "")
    assessment_id = attempt.get("assessmentId", "")
    total_mark    = attempt.get("totalMark", 0)
    max_marks     = attempt.get("maximumMarks", attempt.get("totalQuestions", 1))
    total_qs      = attempt.get("totalQuestions", 0)
    attempt_date  = fmt_date(attempt.get("createdAt"))

    items_dict = get_attempt_items_dict(attempt["_id"])
    print(f"  Student: {student_name}  |  Questions: {len(items_dict)}")

    pct       = round(total_mark / max_marks * 100) if max_marks else 0
    grade_str = grade_label(total_mark, max_marks)

    doc = SimpleDocTemplate(output_path, pagesize=A4,
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    W     = A4[0] - 3*cm
    story = []

    header_t = Table(
        [[Paragraph("Student Grade Report", S_TITLE)]],
        colWidths=[W], rowHeights=[1.2*cm]
    )
    header_t.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), C_HEADER_BG),
        ("VALIGN",     (0,0),(-1,-1), "MIDDLE"),
    ]))
    story.append(header_t)
    story.append(Spacer(1, 10))

    top_row = Table([[
        Paragraph(f"<b>Student:</b> {student_name}", S_BODY),
        Paragraph(f"<b>Assessment ID:</b> {str(assessment_id)[:20]}...", S_BODY),
    ]], colWidths=[W/2, W/2])
    top_row.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),0)]))
    story.append(top_row)
    story.append(Spacer(1, 10))

    bar_filled = int(pct / 100 * 6 * cm)
    bar_t = Table(
        [[""]],
        colWidths=[max(0.1, bar_filled / cm) * cm],
        rowHeights=[0.3*cm]
    )
    bar_t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1), C_ACCENT)]))

    score_data = [
        [Paragraph("", S_BODY_C),
         Paragraph("<b>Grade</b>", S_BODY_C),
         Paragraph("<b>Total Score</b>", S_BODY_C),
         Paragraph("<b>Score (%)</b>", S_BODY_C)],
        [Paragraph(f"<b>{student_email[:28]}</b>\n{attempt_date}", S_BODY),
         Paragraph(f"<b>{grade_str}</b>", S_BODY_C),
         Paragraph(f"<b>{total_mark} / {max_marks}</b>", S_BODY_C),
         bar_t],
    ]
    score_t = Table(score_data,
                    colWidths=[W*0.40, W*0.15, W*0.20, W*0.25],
                    rowHeights=[0.7*cm, 1.0*cm])
    score_t.setStyle(TableStyle([
        ("BOX",           (0,0),(-1,-1), 0.5, C_BORDER),
        ("INNERGRID",     (0,0),(-1,-1), 0.5, C_BORDER),
        ("BACKGROUND",    (0,0),(-1,0), C_LIGHT_BG),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ]))
    story.append(score_t)
    story.append(Spacer(1, 14))

    story.append(Paragraph("<b>Responses</b>", S_SUBHEAD))
    story.append(Spacer(1, 4))

    leg_data = [[
        Paragraph("Legend:", S_BODY),
        Paragraph("", S_BODY),
        Paragraph("Correct", S_BODY),
        Paragraph("", S_BODY),
        Paragraph("Incorrect", S_BODY),
        Paragraph("", S_BODY),
        Paragraph("Partial Credit", S_BODY),
        Paragraph("", S_BODY),
        Paragraph("Unanswered", S_BODY),
    ]]
    leg_t = Table(leg_data,
                  colWidths=[1.4*cm, 0.45*cm, 1.6*cm,
                              0.45*cm, 1.7*cm,
                              0.45*cm, 2.2*cm,
                              0.45*cm, 2.0*cm],
                  rowHeights=[0.45*cm])
    leg_t.setStyle(TableStyle([
        ("BACKGROUND",    (1,0),(1,0), C_CORRECT),
        ("BOX",           (1,0),(1,0), 0.5, C_BORDER),
        ("BACKGROUND",    (3,0),(3,0), C_INCORRECT),
        ("BOX",           (3,0),(3,0), 0.5, C_BORDER),
        ("BACKGROUND",    (5,0),(5,0), C_PARTIAL),
        ("BOX",           (5,0),(5,0), 0.5, C_BORDER),
        ("BACKGROUND",    (7,0),(7,0), C_UNANSWERED),
        ("BOX",           (7,0),(7,0), 0.5, C_BORDER),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0),(-1,-1), 0),
        ("BOTTOMPADDING", (0,0),(-1,-1), 0),
        ("LEFTPADDING",   (0,0),(-1,-1), 2),
        ("RIGHTPADDING",  (0,0),(-1,-1), 2),
    ]))
    story.append(leg_t)
    story.append(Spacer(1, 8))

    sorted_indices  = sorted(items_dict.keys())
    num_qs          = len(sorted_indices)
    block_size      = 5
    blocks          = []
    for start in range(0, num_qs, block_size):
        blocks.append(sorted_indices[start:start+block_size])

    blocks_per_row = 3
    col_w          = W / blocks_per_row

    for row_start in range(0, len(blocks), blocks_per_row):
        row_blocks = blocks[row_start:row_start+blocks_per_row]

        mini_tables = []
        for block in row_blocks:
            mini_rows = [
                [Paragraph("<b>Q#</b>", S_SMALL),
                 Paragraph("<b>Response</b>", S_SMALL),
                 Paragraph("<b>Result</b>", S_SMALL)]
            ]
            mini_styles = [
                ("BACKGROUND",    (0,0),(-1,0), C_LIGHT_BG),
                ("BOX",           (0,0),(-1,-1), 0.5, C_BORDER),
                ("INNERGRID",     (0,0),(-1,-1), 0.3, C_BORDER),
                ("TOPPADDING",    (0,0),(-1,-1), 3),
                ("BOTTOMPADDING", (0,0),(-1,-1), 3),
                ("ALIGN",         (0,0),(-1,-1), "CENTER"),
                ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
            ]
            for row_i, q_idx in enumerate(block, 1):
                item     = items_dict[q_idx]
                obtained = item.get("obtainedMarks", 0)
                actual   = item.get("actualMarks", 1)
                is_miss  = item.get("isMissed", False)
                bg       = cell_color(obtained, actual, is_miss)

                if is_miss:
                    resp_str   = "—"
                    result_str = "Skip"
                elif obtained >= actual and actual > 0:
                    resp_str   = str(obtained)
                    result_str = "✓"
                elif obtained > 0:
                    resp_str   = str(obtained)
                    result_str = "~"
                else:
                    resp_str   = str(obtained)
                    result_str = "✗"

                mini_rows.append([
                    Paragraph(str(q_idx + 1), S_SMALL),
                    Paragraph(resp_str, S_SMALL),
                    Paragraph(result_str, S_SMALL),
                ])
                mini_styles.append(("BACKGROUND", (0,row_i),(-1,row_i), bg))

            bw     = col_w - 0.3*cm
            mini_t = Table(mini_rows, colWidths=[bw*0.25, bw*0.40, bw*0.35])
            mini_t.setStyle(TableStyle(mini_styles))
            mini_tables.append(mini_t)

        while len(mini_tables) < blocks_per_row:
            mini_tables.append(Paragraph("", S_BODY))

        row_t = Table([mini_tables], colWidths=[col_w]*blocks_per_row)
        row_t.setStyle(TableStyle([
            ("VALIGN",        (0,0),(-1,-1), "TOP"),
            ("LEFTPADDING",   (0,0),(-1,-1), 3),
            ("RIGHTPADDING",  (0,0),(-1,-1), 3),
        ]))
        story.append(row_t)
        story.append(Spacer(1, 8))

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width=W, color=C_BORDER, thickness=0.5, spaceAfter=4))
    story.append(Paragraph(
        f"{fmt_date(attempt.get('createdAt'))}   ·   Student Grade Report   ·   Confidential",
        S_FOOTER
    ))

    doc.build(story)
    print(f"  Saved -> {output_path}")


def build_classroom_report(output_path):
    print("\n[Report 2] Fetching data ...")

    classroom, classroom_id = get_best_classroom()
    if not classroom:
        print("  No classroom found."); return

    classroom_name = classroom.get("name", str(classroom_id))
    assessment_id  = get_common_assessment(classroom_id)
    print(f"  Classroom: '{classroom_name}'  |  Assessment: {assessment_id}")

    members = list(col_classroom_members.find({
        "classroomId": classroom_id,
        "role": "student",
        "status": "active",
    }))

    rows = []
    for m in members:
        attempt = col_attempts.find_one({
            "userId": m["userId"],
            "assessmentId": assessment_id,
            "status": "evaluated",
        })
        if attempt:
            rows.append({"member": m, "attempt": attempt})

    if not rows:
        print("  No matching attempts."); return

    print(f"  Students with attempts: {len(rows)}")

    max_qs = max(r["attempt"].get("totalQuestions", 0) for r in rows)
    max_qs = min(max_qs, 38)

    for r in rows:
        r["items"] = get_attempt_items_dict(r["attempt"]["_id"])

    doc = SimpleDocTemplate(output_path, pagesize=landscape(A4),
                            leftMargin=1*cm, rightMargin=1*cm,
                            topMargin=1.2*cm, bottomMargin=1.2*cm)
    W     = landscape(A4)[0] - 2*cm
    story = []

    header_t = Table(
        [[Paragraph("Student Response Report", S_TITLE)]],
        colWidths=[W], rowHeights=[1.1*cm]
    )
    header_t.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), C_HEADER_BG),
        ("VALIGN",     (0,0),(-1,-1), "MIDDLE"),
    ]))
    story.append(header_t)
    story.append(Spacer(1, 6))

    story.append(Paragraph(
        f"<b>Classroom:</b> {classroom_name}   "
        f"<b>Date:</b> {datetime.datetime.now().strftime('%d %b %Y')}",
        S_BODY
    ))
    story.append(Spacer(1, 4))

    leg2_data = [[
        Paragraph("Legend:", S_BODY),
        Paragraph("", S_BODY),
        Paragraph("Correct", S_BODY),
        Paragraph("", S_BODY),
        Paragraph("Incorrect", S_BODY),
        Paragraph("", S_BODY),
        Paragraph("Partial", S_BODY),
        Paragraph("", S_BODY),
        Paragraph("Unanswered", S_BODY),
    ]]
    leg2_t = Table(leg2_data,
                   colWidths=[1.3*cm, 0.45*cm, 1.6*cm,
                               0.45*cm, 1.7*cm,
                               0.45*cm, 1.6*cm,
                               0.45*cm, 2.0*cm],
                   rowHeights=[0.45*cm])
    leg2_t.setStyle(TableStyle([
        ("BACKGROUND",    (1,0),(1,0), C_CORRECT),
        ("BOX",           (1,0),(1,0), 0.5, C_BORDER),
        ("BACKGROUND",    (3,0),(3,0), C_INCORRECT),
        ("BOX",           (3,0),(3,0), 0.5, C_BORDER),
        ("BACKGROUND",    (5,0),(5,0), C_PARTIAL),
        ("BOX",           (5,0),(5,0), 0.5, C_BORDER),
        ("BACKGROUND",    (7,0),(7,0), C_UNANSWERED),
        ("BOX",           (7,0),(7,0), 0.5, C_BORDER),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0),(-1,-1), 0),
        ("BOTTOMPADDING", (0,0),(-1,-1), 0),
        ("LEFTPADDING",   (0,0),(-1,-1), 2),
        ("RIGHTPADDING",  (0,0),(-1,-1), 2),
    ]))
    story.append(leg2_t)
    story.append(Spacer(1, 6))

    fixed_cols = 4
    q_indices  = list(range(max_qs))

    name_w    = 3.5*cm
    score_w   = 1.5*cm
    pct_w     = 1.5*cm
    grade_w   = 1.0*cm
    remaining = W - name_w - score_w - pct_w - grade_w
    q_w       = max(0.4*cm, remaining / max(max_qs, 1))

    col_widths = [name_w, score_w, pct_w, grade_w] + [q_w] * max_qs

    hdr = [
        Paragraph("<b>Students:</b>", S_SMALL),
        Paragraph("<b>Total\nScore</b>", S_SMALL),
        Paragraph("<b>Pct\nScore</b>", S_SMALL),
        Paragraph("<b>Grade</b>", S_SMALL),
    ] + [Paragraph(f"<b>{i+1}</b>", S_SMALL) for i in q_indices]

    grid_data   = [hdr]
    grid_styles = [
        ("BACKGROUND",    (0,0),(-1,0), C_LIGHT_BG),
        ("BOX",           (0,0),(-1,-1), 0.5, C_BORDER),
        ("INNERGRID",     (0,0),(-1,-1), 0.3, C_BORDER),
        ("TOPPADDING",    (0,0),(-1,-1), 2),
        ("BOTTOMPADDING", (0,0),(-1,-1), 2),
        ("LEFTPADDING",   (0,0),(-1,-1), 2),
        ("RIGHTPADDING",  (0,0),(-1,-1), 2),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("ALIGN",         (1,0),(-1,-1), "CENTER"),
        ("FONTSIZE",      (0,0),(-1,-1), 6.5),
    ]

    q_correct_counts = [0] * max_qs
    q_total_counts   = [0] * max_qs

    for row_i, r in enumerate(rows, 1):
        attempt = r["attempt"]
        items   = r["items"]
        name    = attempt.get("studentName", r["member"].get("email", "Unknown"))
        name    = name[:28]
        score   = attempt.get("totalMark", 0)
        max_m   = attempt.get("maximumMarks", 1) or 1
        pct     = round(score / max_m * 100)
        grade   = grade_label(score, max_m)

        row_data = [
            Paragraph(name, S_SMALL),
            Paragraph(str(score), S_SMALL),
            Paragraph(f"{pct}", S_SMALL),
            Paragraph(grade, S_SMALL),
        ]

        for q_idx in q_indices:
            item = items.get(q_idx)
            if item:
                obtained = item.get("obtainedMarks", 0)
                actual   = item.get("actualMarks", 1)
                is_miss  = item.get("isMissed", False)
                bg       = cell_color(obtained, actual, is_miss)

                if not is_miss:
                    q_total_counts[q_idx] += 1
                    if obtained >= actual and actual > 0:
                        q_correct_counts[q_idx] += 1
                        cell_text = "✓"
                    elif obtained > 0:
                        cell_text = "~"
                    else:
                        cell_text = "✗"
                else:
                    cell_text = ""
                    bg = C_UNANSWERED
            else:
                bg        = C_UNANSWERED
                cell_text = ""

            col_pos = fixed_cols + q_idx
            grid_styles.append(("BACKGROUND", (col_pos, row_i), (col_pos, row_i), bg))
            row_data.append(Paragraph(cell_text, S_SMALL))

        grid_data.append(row_data)

        if row_i % 2 == 0:
            grid_styles.append(("BACKGROUND", (0,row_i),(3,row_i), colors.HexColor("#f9f9f9")))

    num_students  = len(rows)
    total_scores  = [r["attempt"].get("totalMark", 0) for r in rows]
    avg_score     = sum(total_scores) / num_students if num_students else 0
    max_m_overall = max((r["attempt"].get("maximumMarks",1) or 1) for r in rows)
    avg_pct       = round(avg_score / max_m_overall * 100)

    avg_row = [
        Paragraph("<b>Average:</b>", S_SMALL),
        Paragraph(f"{avg_score:.1f}", S_SMALL),
        Paragraph(f"{avg_pct}", S_SMALL),
        Paragraph(grade_label(avg_score, max_m_overall), S_SMALL),
    ]
    avg_row_i = len(rows) + 1
    for q_idx in q_indices:
        pct_q = round(q_correct_counts[q_idx] / q_total_counts[q_idx] * 100) \
                if q_total_counts[q_idx] else 0
        avg_row.append(Paragraph(f"{pct_q}", S_SMALL))
    grid_data.append(avg_row)
    grid_styles.append(("BACKGROUND", (0, avg_row_i),(-1, avg_row_i), C_LIGHT_BG))
    grid_styles.append(("FONTNAME",   (0, avg_row_i),(-1, avg_row_i), "Helvetica-Bold"))

    grid_t = Table(grid_data, colWidths=col_widths, repeatRows=1)
    grid_t.setStyle(TableStyle(grid_styles))
    story.append(grid_t)

    story.append(Spacer(1, 8))
    story.append(HRFlowable(width=W, color=C_BORDER, thickness=0.5, spaceAfter=3))
    story.append(Table(
        [[Paragraph(datetime.datetime.now().strftime("%m/%d/%Y"), S_FOOTER),
          Paragraph("Student Response Report", S_FOOTER)]],
        colWidths=[W/2, W/2]
    ))

    doc.build(story)
    print(f"  Saved -> {output_path}")


if __name__ == "__main__":
    print("Connecting to MongoDB ...")
    try:
        client.admin.command("ping")
        print("  Connected!")
    except Exception as e:
        print(f"  Connection failed: {e}"); exit(1)

    build_student_report("student_grade_report.pdf")
    build_classroom_report("student_response_report.pdf")

    print("\nDone!")
    print("  -> student_grade_report.pdf")
    print("  -> student_response_report.pdf")
    client.close()
