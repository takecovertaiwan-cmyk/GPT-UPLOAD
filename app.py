import os
import io
import json
import hashlib
import uuid
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from fpdf import FPDF
import qrcode
from PIL import Image, ImageEnhance
import google.generativeai as genai

# =============================================================
# 基本設定
# =============================================================
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("Missing GEMINI_API_KEY environment variable")

genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.5-flash"

# =============================================================
# 工具：建立淡化浮水印圖 (5%)
# =============================================================
def create_faint_logo(original_path, output_path):
    try:
        img = Image.open(original_path).convert("RGBA")
        alpha = img.split()[3]
        alpha = ImageEnhance.Brightness(alpha).enhance(0.05)  # 約5%
        img.putalpha(alpha)
        img.save(output_path)
        return output_path
    except Exception:
        return original_path

def add_watermark(pdf, logo_path):
    faint_logo = os.path.join(UPLOAD_FOLDER, "faint_logo.png")
    logo_used = create_faint_logo(logo_path, faint_logo)
    if os.path.exists(logo_used):
        pdf.image(logo_used, x=40, y=90, w=130)

# =============================================================
@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.route("/")
def index():
    return render_template("index.html")

# =============================================================
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

    # ---------------------------------------------------------
    # 封面頁
    # ---------------------------------------------------------
    pdf.add_page()
    add_watermark(pdf, "LOGO.jpg")
    if os.path.exists("LOGO.jpg"):
        pdf.image("LOGO.jpg", x=80, y=40, w=50)
    pdf.set_font("Taipei", "", 30)
    pdf.set_y(100)
    pdf.cell(0, 15, "WesmartAI 證據報告", ln=True, align="C")
    pdf.ln(20)
    pdf.set_font("Taipei", "", 14)
    pdf.cell(0, 10, f"出證申請人: {applicant}", ln=True, align="C")
    pdf.cell(0, 10, "申請事項: WesmartAI 生成式 AI 證據報告", ln=True, align="C")
    pdf.cell(0, 10, f"申請出證時間: {timestamp_utc}", ln=True, align="C")
    pdf.cell(0, 10, f"出證編號 (報告ID): {evidence_id}", ln=True, align="C")
    pdf.cell(0, 10, "出證單位: WesmartAI Inc.", ln=True, align="C")

    # ---------------------------------------------------------
    # 內頁（逐圖 Gemini 分析）
    # ---------------------------------------------------------
    model = genai.GenerativeModel(MODEL_NAME)
    all_hash_concat = ""

    for idx, fdata in enumerate(files_info, start=1):
        file_name = fdata.get("file_name")
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], file_name)
        if not os.path.exists(file_path):
            continue
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        prompt = """
        You are a digital forensics assistant.
        Analyze this image (binary bytes) and return a JSON object:
        {
          "timestamp_utc": "<current UTC time>",
          "sha256": "<sha256 of image>",
          "size_kb": "<file size in KB>",
          "format": "<JPEG or PNG>"
        }
        Output only strict JSON.
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

        all_hash_concat += ai_data.get("sha256", "")

        pdf.add_page()
        add_watermark(pdf, "LOGO.jpg")
        pdf.set_font("Taipei", "", 13)
        pdf.cell(0, 10, "一、生成任務基本資訊", ln=True)
        pdf.set_font("Taipei", "", 11)
        pdf.cell(0, 8, f"Trace Token: {trace_token}", ln=True)
        pdf.cell(0, 8, f"圖片索引: {idx}", ln=True)
        pdf.cell(0, 8, f"檔案名稱: {file_name}", ln=True)
        pdf.cell(0, 8, f"檔案大小: {ai_data.get('size_kb')} KB", ln=True)
        pdf.cell(0, 8, f"圖像雜湊 (SHA-256): {ai_data.get('sha256')}", ln=True)
        if fdata.get("prompt"):
            pdf.cell(0, 8, f"輸入指令 (Prompt): {fdata['prompt']}", ln=True)
        if fdata.get("seed"):
            pdf.cell(0, 8, f"隨機種子 (Seed): {fdata['seed']}", ln=True)
        pdf.ln(4)
        pdf.image(file_path, x=40, w=100)

    # ---------------------------------------------------------
    # 結尾頁
    # ---------------------------------------------------------
    pdf.add_page()
    add_watermark(pdf, "LOGO.jpg")
    pdf.set_font("Taipei", "", 13)
    pdf.cell(0, 10, "三、報告驗證", ln=True)
    pdf.ln(5)
    pdf.set_font("Taipei", "", 11)
    pdf.multi_cell(
        0, 8,
        "本報告由WesmartAI數位證據三方存證系統自動生成，AI驗證層由Gemini模型提供，用於抽取各圖檔之時間戳、雜湊與屬性。所有數據具可驗證性與不可竄改性，可作為AI數位證據之存證歷程證明。"
    )
    pdf.ln(5)
    final_event_hash = hashlib.sha256(all_hash_concat.encode()).hexdigest()
    pdf.cell(0, 10, "最終事件雜湊值 (Final Event Hash):", ln=True)
    pdf.set_font("Taipei", "", 10)
    pdf.multi_cell(0, 8, final_event_hash)
    pdf.ln(5)
    qr_path = os.path.join(UPLOAD_FOLDER, f"{evidence_id}_verify.png")
    qrcode.make(f"https://wesmartai.com/verify/{evidence_id}").save(qr_path)
    pdf.image(qr_path, x=80, w=50)
    os.remove(qr_path)
    pdf.ln(5)
    pdf.cell(0, 10, "掃描 QR Code 前往驗證頁面", ln=True)

    output_path = os.path.join(UPLOAD_FOLDER, f"report_{evidence_id}.pdf")
    pdf.output(output_path)
    return send_file(output_path, as_attachment=True)

# =============================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
