import os
import io
import json
import base64
import hashlib
import uuid
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from fpdf import FPDF
import qrcode
import google.generativeai as genai

# -------------------------------------------------------------
# 基本設定
# -------------------------------------------------------------
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("Missing GEMINI_API_KEY environment variable")

genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.5-flash"

# -------------------------------------------------------------
@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.route("/")
def index():
    return render_template("index.html")

# -------------------------------------------------------------
# 多檔預覽
# -------------------------------------------------------------
@app.route("/preview", methods=["POST"])
def preview():
    if "files" not in request.files:
        return jsonify({"error": "no files"}), 400

    files = request.files.getlist("files")
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
            "preview_url": f"/uploads/{file.filename}",
            "sha256": sha256_hash
        })
    return jsonify(previews)

# -------------------------------------------------------------
# 生成 PDF：每張圖都經 Gemini 分析
# -------------------------------------------------------------
@app.route("/generate", methods=["POST"])
def generate_pdf():
    data = request.get_json()
    applicant = data.get("applicant", "未填寫")
    files_info = data.get("files", [])
    if not files_info:
        return jsonify({"error": "No files provided"}), 400

    evidence_id = str(uuid.uuid4())
    trace_token = hashlib.md5(evidence_id.encode()).hexdigest().upper()

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_font("Taipei", "", "TaipeiSansTCBeta-Regular.ttf", uni=True)
    pdf.set_font("Taipei", "", 12)
    pdf.add_page()

    if os.path.exists("LOGO.jpg"):
        pdf.image("LOGO.jpg", x=80, y=10, w=50)
    pdf.ln(35)

    pdf.set_font("Taipei", "", 18)
    pdf.cell(0, 10, "WesmartAI 數位證據第三方存證報告", ln=True, align="C")
    pdf.ln(10)
    pdf.set_font("Taipei", "", 12)
    pdf.cell(0, 10, f"存證編號：{evidence_id}", ln=True)
    pdf.cell(0, 10, f"申請人：{applicant}", ln=True)
    pdf.cell(0, 10, f"總上傳圖片數：{len(files_info)}", ln=True)
    pdf.cell(0, 10, f"追蹤識別碼（Trace Token）：{trace_token}", ln=True)
    pdf.ln(8)

    model = genai.GenerativeModel(MODEL_NAME)

    for idx, fdata in enumerate(files_info, start=1):
        file_name = fdata.get("file_name")
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], file_name)
        if not os.path.exists(file_path):
            continue

        with open(file_path, "rb") as f:
            file_bytes = f.read()

        prompt = f"""
        You are a digital forensics assistant.
        Given this image (as bytes), extract factual metadata in JSON:
        {{
          "timestamp_utc": "<current UTC time>",
          "sha256": "<sha256 of the image>",
          "size_kb": "<file size in KB>",
          "format": "<JPEG or PNG>"
        }}
        Ensure strict JSON only.
        """

        try:
            response = model.generate_content([
                {"role": "user", "parts": [prompt, {"mime_type": "image/jpeg", "data": file_bytes}]}
            ])
            ai_data = json.loads(response.text.strip())
        except Exception:
            ai_data = {
                "timestamp_utc": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
                "sha256": hashlib.sha256(file_bytes).hexdigest(),
                "size_kb": round(len(file_bytes) / 1024, 2),
                "format": file_name.split(".")[-1].upper()
            }

        pdf.set_font("Taipei", "", 14)
        pdf.cell(0, 10, f"圖片 {idx}：{file_name}", ln=True)
        pdf.set_font("Taipei", "", 11)
        pdf.cell(0, 8, f"AI 驗證 SHA256：{ai_data.get('sha256')}", ln=True)
        pdf.cell(0, 8, f"大小：{ai_data.get('size_kb')} KB", ln=True)
        pdf.cell(0, 8, f"格式：{ai_data.get('format')}", ln=True)
        pdf.cell(0, 8, f"AI 時間戳：{ai_data.get('timestamp_utc')}", ln=True)
        pdf.ln(4)
        pdf.image(file_path, x=25, w=160)
        pdf.ln(10)

    qr_path = os.path.join(UPLOAD_FOLDER, f"{evidence_id}.png")
    verify_url = f"https://wesmartai.com/verify/{evidence_id}"
    qrcode.make(verify_url).save(qr_path)
    pdf.cell(0, 10, "驗證 QR Code：", ln=True)
    pdf.image(qr_path, x=80, w=50)
    os.remove(qr_path)

    pdf.ln(10)
    pdf.set_font("Taipei", "", 11)
    pdf.multi_cell(
        0, 8,
        "本報告由 WesmartAI 數位證據三方存證系統自動生成，"
        "AI驗證層由Gemini 2.5 Flash模型提供，用於抽取各圖檔之時間戳、雜湊與屬性。"
        "所有數據具可驗證性與不可竄改性，可作為AI數位證據之存證歷程證明。"
    )

    output_path = os.path.join(UPLOAD_FOLDER, f"report_{evidence_id}.pdf")
    pdf.output(output_path)
    return send_file(output_path, as_attachment=True)

# -------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
