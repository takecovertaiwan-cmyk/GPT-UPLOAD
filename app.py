import os, uuid, hashlib, base64, json
from datetime import datetime, UTC
from flask import Flask, render_template, request, send_file
from fpdf import FPDF
from openai import OpenAI
import tempfile

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate_pdf():
    applicant = request.form.get('applicant', '未命名申請人')
    files = request.files.getlist('files')
    if not files:
        return "未上傳任何檔案", 400

    # 建立暫存目錄
    tmp_dir = tempfile.mkdtemp()
    trace_token = str(uuid.uuid4())
    snapshots = []

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

    # GPT 生成摘要
    prompt = f"請撰寫50字以內中文摘要，描述封存人 {applicant} 於 {datetime.now(UTC).isoformat()} 上傳的多媒體檔案已完成存證。"
    try:
        summary = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        ).choices[0].message.content.strip()
    except Exception as e:
        summary = f"自動摘要失敗：{e}"

    # 生成 PDF
    pdf_path = os.path.join(tmp_dir, f"WesmartAI_Report_{trace_token}.pdf")
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="WesmartAI 數位證據存證報告", ln=True, align='C')
    pdf.ln(10)
    pdf.multi_cell(0, 8, txt=f"出證申請人: {applicant}")
    pdf.multi_cell(0, 8, txt=f"Trace Token: {trace_token}")
    pdf.multi_cell(0, 8, txt=f"生成時間: {datetime.now(UTC).isoformat()}")
    pdf.multi_cell(0, 8, txt=f"摘要: {summary}")
    pdf.ln(5)
    for snap in snapshots:
        pdf.multi_cell(0, 8, txt=json.dumps(snap, indent=2, ensure_ascii=False))
        pdf.ln(3)
    pdf.output(pdf_path)

    return send_file(pdf_path, as_attachment=True, download_name=os.path.basename(pdf_path))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
