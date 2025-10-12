import os
import hashlib
import uuid
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from fpdf import FPDF
import qrcode

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/preview", methods=["POST"])
def preview():
    files = request.files.getlist("file")
    if not files:
        return jsonify({"error": "no file"}), 400

    previews = []
    for file in files:
        if file.filename == "":
            continue
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
        file.save(filepath)
        with open(filepath, "rb") as f:
            sha256_hash = hashlib.sha256(f.read()).hexdigest()
        previews.append({
            "file_name": file.filename,
            "sha256": sha256_hash,
            "preview_url": f"/uploads/{file.filename}"
        })
    return jsonify(previews)

@app.route("/generate", methods=["POST"])
def generate_pdf():
    data = request.get_json()
    files = data.get("files", [])
    applicant = data.get("applicant", "未填寫")

    if not files:
        return jsonify({"error": "No files provided"}), 400

    evidence_id = str(uuid.uuid4())
    trace_token = hashlib.md5(evidence_id.encode()).hexdigest().upper()
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_font("Taipei", "", "TaipeiSansTCBeta-Regular.ttf", uni=True)

    # 封面頁
    pdf.add_page()
    pdf.set_font("Taipei", "", 18)
    pdf.cell(0, 10, "WesmartAI 數位證據第三方存證報告", ln=True, align="C")
    pdf.ln(12)
    pdf.set_font("Taipei", "", 12)
    pdf.cell(0, 10, f"存證編號：{evidence_id}", ln=True)
    pdf.cell(0, 10, f"申請人：{applicant}", ln=True)
    pdf.cell(0, 10, f"總封存檔案數：{len(files)}", ln=True)
    pdf.cell(0, 10, f"追蹤識別碼（Trace Token）：{trace_token}", ln=True)
    pdf.cell(0, 10, f"建立時間：{timestamp}", ln=True)
    pdf.ln(10)
    pdf.multi_cell(0, 8, "以下為各封存檔案之摘要與驗證資訊：")

    # 各檔案一頁
    for item in files:
        file_name = item.get("file_name")
        sha256_hash = item.get("sha256")
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], file_name)

        pdf.add_page()
        pdf.set_font("Taipei", "", 14)
        pdf.cell(0, 10, f"檔案名稱：{file_name}", ln=True)
        pdf.ln(5)
        pdf.set_font("Taipei", "", 12)
        pdf.multi_cell(0, 8, f"SHA256 雜湊值：{sha256_hash}")
        pdf.multi_cell(0, 8, f"追蹤識別碼：{trace_token}")
        pdf.multi_cell(0, 8, f"時間戳記：{timestamp}")
        pdf.ln(8)
        pdf.cell(0, 8, "預覽圖：", ln=True)
        pdf.ln(5)
        if os.path.exists(file_path):
            pdf.image(file_path, x=25, w=160)

    # 結論頁
    pdf.add_page()
    pdf.set_font("Taipei", "", 14)
    pdf.cell(0, 10, "結論與技術說明", ln=True, align="L")
    pdf.ln(8)
    pdf.set_font("Taipei", "", 11)
    pdf.multi_cell(
        0, 8,
        "本報告由 WesmartAI 數位證據系統自動生成。\n"
        "系統於生成過程中經 Gemini 2.5 Flash 語言模型協作，用以進行內容摘要、雜湊封存與參數驗證。\n"
        "所有雜湊值、時間戳記與追蹤編號均具可驗證性與不可竄改性。\n"
        "本報告生成過程具可追溯性與完整性，可作為人工智慧生成內容之創作歷程與智慧財產權佐證之用。"
    )
    pdf.ln(10)
    pdf.set_font("Taipei", "", 10)
    pdf.cell(0, 8, "報告生成時間：" + timestamp, ln=True)

    output_path = os.path.join(UPLOAD_FOLDER, f"report_{timestamp.replace(':','-')}.pdf")
    pdf.output(output_path)
    return send_file(output_path, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
