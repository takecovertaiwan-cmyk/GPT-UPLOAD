import os, hashlib, json, tempfile, uuid
from datetime import datetime, UTC
from flask import Flask, render_template, request, jsonify, send_file
from fpdf import FPDF
from PIL import Image
import google.generativeai as genai

app = Flask(__name__)

# 初始化 Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
MODEL_ID = "gemini-2.5-flash"

# 暫存區
UPLOAD_TEMP = tempfile.gettempdir()

# === 首頁 ===
@app.route('/')
def index():
    return render_template('index.html')

# === 步驟1：生成預覽與 hash ===
@app.route('/preview', methods=['POST'])
def preview():
    files = request.files.getlist('files')
    if not files:
        return jsonify({"error": "未上傳檔案"}), 400

    results = []
    for f in files:
        file_id = str(uuid.uuid4())
        path = os.path.join(UPLOAD_TEMP, file_id + "_" + f.filename)
        f.save(path)
        with open(path, "rb") as fp:
            b = fp.read()
        sha = hashlib.sha256(b).hexdigest()
        results.append({
            "file_id": file_id,
            "filename": f.filename,
            "sha256": sha,
            "size_kb": round(len(b)/1024, 2),
            "timestamp": datetime.now(UTC).isoformat(),
        })
    return jsonify({"status": "ok", "snapshots": results})

# === 步驟2：生成 PDF 報告 ===
@app.route('/generate', methods=['POST'])
def generate_pdf():
    data = json.loads(request.form.get("data"))
    applicant = data.get("applicant", "未命名申請人")
    snapshots = data.get("snapshots", [])
    trace_token = str(uuid.uuid4())

    # 生成摘要（使用第一張圖）
    summary = "未生成摘要"
    if snapshots:
        first_file = snapshots[0]["filename"]
        path = os.path.join(UPLOAD_TEMP, snapshots[0]["file_id"] + "_" + first_file)
        try:
            model = genai.GenerativeModel(MODEL_ID)
            with open(path, "rb") as fp:
                img = fp.read()
            prompt = f"請為出證申請人 {applicant} 上傳的圖片生成50字以內封存摘要。"
            res = model.generate_content([prompt, {"mime_type": "image/png", "data": img}])
            summary = res.text.strip()
        except Exception as e:
            summary = f"摘要生成失敗：{e}"

    # 生成 PDF
    pdf_path = os.path.join(UPLOAD_TEMP, f"WesmartAI_Report_{trace_token}.pdf")
    pdf = FPDF()
    pdf.add_page()
    pdf.add_font("NotoSansTC", "", "NotoSansTC.otf", uni=True)
    pdf.set_font("NotoSansTC", size=12)
    pdf.cell(200, 10, txt="WesmartAI 數位證據封存報告", ln=True, align="C")
    pdf.ln(8)
    pdf.multi_cell(0, 8, f"出證申請人：{applicant}")
    pdf.multi_cell(0, 8, f"Trace Token：{trace_token}")
    pdf.multi_cell(0, 8, f"生成時間：{datetime.now(UTC).isoformat()}")
    pdf.multi_cell(0, 8, f"摘要：{summary}")
    pdf.ln(5)
    pdf.multi_cell(0, 8, "=== 封存快照 ===")
    pdf.multi_cell(0, 8, json.dumps(snapshots, indent=2, ensure_ascii=False))
    pdf.output(pdf_path)

    return send_file(pdf_path, as_attachment=True, download_name=os.path.basename(pdf_path))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
