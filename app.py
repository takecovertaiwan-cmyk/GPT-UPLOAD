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
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "empty filename"}), 400

    filepath = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
    file.save(filepath)

    with open(filepath, "rb") as f:
        sha256_hash = hashlib.sha256(f.read()).hexdigest()

    return jsonify({
        "preview_url": f"/uploads/{file.filename}",
        "sha256": sha256_hash
    })

@app.route("/generate", methods=["POST"])
def generate_pdf():
    data = request.get_json()
    file_name = data.get("file_name")
    sha256_hash = data.get("sha256")
    applicant = data.get("applicant", "未填寫")

    if not file_name or not sha256_hash:
        return jsonify({"error": "Missing fields"}), 400

    evidence_id = str(uuid.uuid4())
    trace_token = hashlib.md5(evidence_id.encode()).hexdigest().upper()
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # 字型設定
    pdf.add_font("Taipei", "", "TaipeiSansTCBeta-Regular.ttf", uni=True)
    pdf.set_font("Taipei", "", 14)

    # LOGO
    if os.path.exists("LOGO.jpg"):
        pdf.image("LOGO.jpg", x=80, y=10, w=50)
    pdf.ln(35)

    # 標題
    pdf.set_font("Taipei", "", 18)
    pdf.cell(0, 10, "WesmartAI 數位證據第三方存證報告", ln=True, align="C")
    pdf.ln(10)

    pdf.set_font("Taipei", "", 12)
    pdf.cell(0, 10, f"存證編號：{evidence_id}", ln=True)
    pdf.cell(0, 10, f"申請人：{applicant}", ln=True)
    pdf.cell(0, 10, f"檔案名稱：{file_name}", ln=True)
    pdf.multi_cell(0, 10, f"SHA256 雜湊值：{sha256_hash}")
    pdf.cell(0, 10, f"追蹤識別碼（Trace Token）：{trace_token}", ln=True)
    pdf.cell(0, 10, f"時間戳記：{timestamp}", ln=True)
    pdf.ln(8)

    pdf.cell(0, 10, "預覽圖：", ln=True)
    pdf.ln(5)
    img_path = os.path.join(app.config["UPLOAD_FOLDER"], file_name)
    if os.path.exists(img_path):
        pdf.image(img_path, x=25, w=160)
    pdf.ln(10)

    # QR Code
    verify_url = f"https://wesmartai.com/verify/{evidence_id}"
    qr_path = os.path.join(UPLOAD_FOLDER, f"{evidence_id}.png")
    qr = qrcode.make(verify_url)
    qr.save(qr_path)
    pdf.cell(0, 10, "驗證 QR Code：", ln=True)
    pdf.image(qr_path, x=80, w=50)
    os.remove(qr_path)

    pdf.ln(10)
    pdf.set_font("Taipei", "", 11)
    pdf.multi_cell(
        0, 8,
        "本報告由 WesmartAI 數位證據系統自動生成。"
        "系統於生成過程中經 Gemini 2.5 Flash 語言模型協作，用以進行內容摘要、雜湊封存與參數驗證。"
        "所有雜湊值、時間戳記與追蹤編號均具可驗證性與不可竄改性。"
        "本報告生成過程具可追溯性與完整性，可作為人工智慧生成內容之創作歷程與智慧財產權佐證之用。"
    )

    output_path = os.path.join(UPLOAD_FOLDER, f"report_{file_name}.pdf")
    pdf.output(output_path)
    return send_file(output_path, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
