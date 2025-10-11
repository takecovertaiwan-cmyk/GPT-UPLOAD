import os, uuid, hashlib, json, tempfile
from datetime import datetime, UTC
from flask import Flask, render_template, request, send_file
from fpdf import FPDF
from PIL import Image
from io import BytesIO
import google.generativeai as genai

app = Flask(__name__)

# === 初始化 Gemini API ===
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_KEY:
    raise RuntimeError("缺少 GEMINI_API_KEY 環境變數")
genai.configure(api_key=GEMINI_KEY)

# === 指定模型 ===
MODEL_ID = "gemini-2.5-flash"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate_pdf():
    applicant = request.form.get('applicant', '未命名申請人')
    files = request.files.getlist('files')
    if not files:
        return "未上傳任何檔案", 400

    tmp_dir = tempfile.mkdtemp()
    trace_token = str(uuid.uuid4())
    snapshots = []

    # 處理每張上傳圖片
    for f in files:
        file_path = os.path.join(tmp_dir, f.filename)
        f.save(file_path)
        with open(file_path, "rb") as fp:
            file_bytes = fp.read()

        sha256_hash = hashlib.sha256(file_bytes).hexdigest()
        snapshots.append({
            "filename": f.filename,
            "sha256_hash": sha256_hash,
            "size_kb": round(len(file_bytes)/1024, 2),
            "timestamp": datetime.now(UTC).isoformat()
        })

    # 使用 Gemini 生成摘要
    try:
        model = genai.GenerativeModel(MODEL_ID)
        content = [
            f"請生成一段50字以內的中文封存摘要，描述出證申請人 {applicant} 上傳的多媒體資料封存完成。",
        ]
        # 若上傳單一圖像可一併分析
        if len(files) == 1:
            file_path = os.path.join(tmp_dir, files[0].filename)
            with open(file_path, "rb") as fp:
                img_bytes = fp.read()
            content.append({"mime_type": "image/png", "data": img_bytes})
        response = model.generate_content(content)
        summary = response.text.strip()
    except Exception as e:
        summary = f"自動摘要失敗：{e}"

    # 生成 PDF 報告
    pdf_path = os.path.join(tmp_dir, f"WesmartAI_Report_{trace_token}.pdf")
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="WesmartAI 數位證據封存報告", ln=True, align='C')
    pdf.ln(10)
    pdf.multi_cell(0, 8, txt=f"出證申請人: {applicant}")
    pdf.multi_cell(0, 8, txt=f"Trace Token: {trace_token}")
    pdf.multi_cell(0, 8, txt=f"生成時間: {datetime.now(UTC).isoformat()}")
    pdf.multi_cell(0, 8, txt=f"摘要: {summary}")
    pdf.ln(5)
    pdf.multi_cell(0, 8, txt="=== 封存快照 ===")
    for snap in snapshots:
        pdf.multi_cell(0, 8, txt=json.dumps(snap, indent=2, ensure_ascii=False))
        pdf.ln(3)
    pdf.output(pdf_path)

    return send_file(pdf_path, as_attachment=True, download_name=os.path.basename(pdf_path))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
