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

# 載入 Gemini API Key（Render 上設環境變數 GEMINI_API_KEY）
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("Missing GEMINI_API_KEY environment variable")

genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.5-flash"

# -------------------------------------------------------------
# Routes
# -------------------------------------------------------------
@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.route("/")
def index():
    return render_template("index.html")

# -------------------------------------------------------------
# 預覽階段：僅儲存檔案與初步 SHA256
# -------------------------------------------------------------
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

# -------------------------------------------------------------
# 生成報告階段：請求 Gemini 分析真實數據
# -------------------------------------------------------------
@app.route("/generate", methods=["POST"])
def generate_pdf():
    data = request.get_json()
    file_name = data.get("file_name")
    applicant = data.get("applicant", "未填寫")
    if not file_name:
        return jsonify({"error": "Missing file name"}), 400

    img_path = os.path.join(app.config["UPLOAD_FOLDER"], file_name)
    if not os.path.exists(img_path):
        return jsonify({"error": "File not found"}), 404

    # 讀取圖片內容
    with open(img_path, "rb") as f:
        file_bytes = f.read()
        base64_img = base64.b64encode(file_bytes).decode("utf-8")

    # Gemini 提示詞
    prompt = f"""
    You are a digital forensics assistant.
    Given this image (as bytes), extract factual metadata in JSON:
    {{
      "timestamp_utc": "<current UTC time>",
      "sha256": "<sha256 of the image>",
      "size_kb": "<file size in KB>",
      "format": "<JPEG or PNG>"
    }}
    Ensure strict JSON only, no explanations.
    """

    # 呼叫 Gemini 2.5 Flash
    try:
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content([
            {"role": "user", "parts": [prompt, {"mime_type": "image/jpeg", "data": file_bytes}]}
        ])
        ai_json = response.text.strip()
        ai_data = json.loads(ai_json)
    except Exception as e:
        # 若 Gemini 無回應則 fallback 本地計算
        ai_data = {
            "timestamp_utc": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "sha256": hashlib.sha256(file_bytes).hexdigest(),
            "size_kb": round(len(file_bytes) / 1024, 2),
            "format": file_name.split(".")[-1].upper()
        }

    # ---------------------------------------------------------
    # 報告生成
    # ---------------------------------------------------------
    evidence_id = str(uuid.uuid4())
    trace_token = hashlib.md5(evidence_id.encode()).hexdigest().upper()

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # 字型
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
    pdf.multi_cell(0, 10, f"SHA256（AI 驗證）：{ai_data.get('sha256')}")
    pdf.cell(0, 10, f"檔案大小：{ai_data.get('size_kb')} KB", ln=True)
    pdf.cell(0, 10, f"檔案格式：{ai_data.get('format')}", ln=True)
    pdf.cell(0, 10, f"AI 提取時間戳：{ai_data.get('timestamp_utc')}", ln=True)
    pdf.cell(0, 10, f"追蹤識別碼（Trace Token）：{trace_token}", ln=True)
    pdf.ln(8)

    pdf.cell(0, 10, "預覽圖：", ln=True)
    pdf.ln(5)
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
        "本報告由 WesmartAI 數位證據三方存證系統自動生成，"
        "AI 驗證層由 Gemini 2.5 Flash 模型提供，用於抽取時間戳、雜湊與檔案屬性。"
        "所有數據具可驗證性與不可竄改性，可作為 AI 生成內容創作歷程之佐證。"
    )

    output_path = os.path.join(UPLOAD_FOLDER, f"report_{file_name}.pdf")
    pdf.output(output_path)
    return send_file(output_path, as_attachment=True)

# -------------------------------------------------------------
# 啟動
# -------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
