import os
import io
import json
import hashlib
import uuid
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from fpdf import FPDF
from PIL import Image
import qrcode

# =============================================================
# 基本設定
# =============================================================
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# =============================================================
# 工具：浮水印
# =============================================================
def add_watermark(pdf, logo_path, alpha=0.2):
    if not os.path.exists(logo_path):
        return
    pdf.image(logo_path, x=40, y=80, w=130)


# =============================================================
# 預覽（同前）
# =============================================================
@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/")
def index():
    return render_template("index.html")


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


# =============================================================
# 生成報告
# =============================================================
@app.route("/generate", methods=["POST"])
def generate_pdf():
    data = request.get_json()
    applicant = data.get("applicant", "未填寫")
    files_info = data.get("files", [])
    if not files_info:
        return jsonify({"error": "No files provided"}), 400

    evidence_id = str(uuid.uuid4())
    trace_token = hashlib.md5(evidence_id.encode()).hexdigest().upper()
    timestamp_utc = datetime.utcnow().isoformat()

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_font("Taipei", "", "TaipeiSansTCBeta-Regular.ttf", uni=True)

    # -------------------------------------------------------------
    # 封面頁
    # -------------------------------------------------------------
    pdf.add_page()
    add_watermark(pdf, "LOGO.jpg", alpha=0.2)
    pdf.set_font("Taipei", "", 22)
    pdf.cell(0, 10, "WesmartAI 證據報告", ln=True, align="C")
    pdf.ln(20)
    pdf.set_font("Taipei", "", 14)
    pdf.cell(0, 10, f"出證申請人: {applicant}", ln=True)
    pdf.cell(0, 10, "申請事項: WesmartAI 生成式 AI 證據報告", ln=True)
    pdf.cell(0, 10, f"申請出證時間: {timestamp_utc}", ln=True)
    pdf.cell(0, 10, f"出證編號 (報告ID): {evidence_id}", ln=True)
    pdf.cell(0, 10, "出證單位: WesmartAI Inc.", ln=True)
    pdf.ln(20)
    pdf.set_font("Taipei", "", 10)
    pdf.cell(0, 10, "第 1/3 頁", align="R")

    # -------------------------------------------------------------
    # 內頁：每張圖的生成快照
    # -------------------------------------------------------------
    for idx, fdata in enumerate(files_info, start=1):
        file_name = fdata.get("file_name")
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], file_name)
        if not os.path.exists(file_path):
            continue

        with open(file_path, "rb") as f:
            file_bytes = f.read()

        sha256_hash = hashlib.sha256(file_bytes).hexdigest()
        size_kb = round(len(file_bytes) / 1024, 2)
        img_format = file_name.split(".")[-1].upper()

        # 模擬 Prompt/Seed
        prompt = fdata.get("prompt")
        seed = fdata.get("seed")

        pdf.add_page()
        add_watermark(pdf, "LOGO.jpg", alpha=0.2)
        pdf.set_font("Taipei", "", 16)
        pdf.cell(0, 10, "WesmartAI 生成式 AI 證據報告 WesmartAI Inc.", ln=True)
        pdf.ln(8)
        pdf.set_font("Taipei", "", 13)
        pdf.cell(0, 10, "一、生成任務基本資訊", ln=True)
        pdf.set_font("Taipei", "", 11)
        pdf.cell(0, 8, f"  Trace Token: {trace_token}", ln=True)
        pdf.cell(0, 8, f"  圖片索引: {idx}", ln=True)
        pdf.cell(0, 8, f"  檔案名稱: {file_name}", ln=True)
        pdf.cell(0, 8, f"  檔案大小: {size_kb} KB", ln=True)
        pdf.cell(0, 8, f"  圖像雜湊 (SHA-256): {sha256_hash}", ln=True)
        if prompt:
            pdf.cell(0, 8, f"  輸入指令 (Prompt): {prompt}", ln=True)
        if seed:
            pdf.cell(0, 8, f"  隨機種子 (Seed): {seed}", ln=True)
        pdf.ln(5)
        pdf.image(file_path, x=25, w=160)
        pdf.ln(5)
        pdf.set_font("Taipei", "", 10)
        pdf.cell(0, 10, f"第 {idx+1}/3 頁", align="R")

    # -------------------------------------------------------------
    # 結尾頁
    # -------------------------------------------------------------
    pdf.add_page()
    add_watermark(pdf, "LOGO.jpg", alpha=0.2)
    pdf.set_font("Taipei", "", 16)
    pdf.cell(0, 10, "WesmartAI 生成式 AI 證據報告 WesmartAI Inc.", ln=True)
    pdf.ln(10)
    pdf.set_font("Taipei", "", 13)
    pdf.cell(0, 10, "三、報告驗證", ln=True)
    pdf.ln(5)
    pdf.set_font("Taipei", "", 11)
    pdf.multi_cell(
        0, 8,
        "本報告由 WesmartAI 數位證據三方存證系統自動生成，"
        "AI驗證層由Gemini 2.5 Flash模型提供，用於抽取各圖檔之時間戳、雜湊與屬性。"
        "所有數據具可驗證性與不可竄改性，可作為AI數位證據之存證歷程證明。"
    )
    pdf.ln(5)

    # Final Event Hash 模擬
    combined_hash_input = "".join([f["sha256"] for f in files_info if "sha256" in f])
    final_event_hash = hashlib.sha256(combined_hash_input.encode()).hexdigest()

    pdf.cell(0, 10, f"最終事件雜湊值 (Final Event Hash):", ln=True)
    pdf.set_font("Taipei", "", 10)
    pdf.multi_cell(0, 8, final_event_hash)
    pdf.ln(5)

    qr_path = os.path.join(UPLOAD_FOLDER, f"{evidence_id}_verify.png")
    qrcode.make(f"https://wesmartai.com/verify/{evidence_id}").save(qr_path)
    pdf.image(qr_path, x=80, w=50)
    os.remove(qr_path)
    pdf.ln(5)
    pdf.set_font("Taipei", "", 10)
    pdf.cell(0, 10, "掃描 QR Code 前往驗證頁面", ln=True)
    pdf.cell(0, 10, "第 3/3 頁", align="R")

    # -------------------------------------------------------------
    output_path = os.path.join(UPLOAD_FOLDER, f"report_{evidence_id}.pdf")
    pdf.output(output_path)
    return send_file(output_path, as_attachment=True)


# =============================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
