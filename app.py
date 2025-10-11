from flask import Flask, render_template, request, send_file, jsonify, send_from_directory
import hashlib, os
from fpdf import FPDF
from PIL import Image
from datetime import datetime

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def calc_sha256(file_path):
    with open(file_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def resize_image(path, max_width=800):
    try:
        img = Image.open(path)
        if img.width > max_width:
            ratio = max_width / float(img.width)
            new_height = int(float(img.height) * ratio)
            img = img.resize((max_width, new_height))
            img.save(path)
    except Exception:
        pass

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/preview", methods=["POST"])
def preview():
    files = request.files.getlist("files")
    previews = []
    for f in files:
        save_path = os.path.join(UPLOAD_FOLDER, f.filename)
        f.save(save_path)
        resize_image(save_path)
        sha256_hash = calc_sha256(save_path)
        file_size = os.path.getsize(save_path)
        previews.append({
            "filename": f.filename,
            "sha256": sha256_hash,
            "size": f"{file_size / 1024:.2f} KB"
        })
    return jsonify(previews)

@app.route("/generate", methods=["POST"])
def generate_pdf():
    applicant = request.form.get("applicant", "未命名")
    file_list = os.listdir(UPLOAD_FOLDER)

    pdf = FPDF()
    pdf.add_page()
    try:
        pdf.add_font("NotoSansTC", "", "NotoSansTC.otf", uni=True)
        pdf.set_font("NotoSansTC", size=12)
    except Exception:
        pdf.set_font("Helvetica", size=12)

    pdf.cell(0, 10, "WesmartAI 數位證據第三方存證報告", ln=True, align="C")
    pdf.cell(0, 10, f"出證申請人：{applicant}", ln=True)
    pdf.cell(0, 10, f"生成時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True)
    pdf.ln(10)

    for filename in file_list:
        path = os.path.join(UPLOAD_FOLDER, filename)
        if not os.path.isfile(path):
            continue
        sha256_hash = calc_sha256(path)
        pdf.cell(0, 10, f"檔名：{filename}", ln=True)
        pdf.multi_cell(0, 10, f"SHA256：{sha256_hash}")
        pdf.ln(3)
        try:
            pdf.image(path, w=100)
        except Exception:
            pass
        pdf.ln(5)

    pdf.ln(10)
    pdf.multi_cell(0, 10,
        "創作歷程說明：\n"
        "本報告封存自使用者之創意輸入（檔案）起始，並記錄其雜湊值（Hash）與時間戳。"
        "生成過程具人為主導性與可驗證性，可用於佐證創作歷程與權屬歸屬。"
    )

    output_path = os.path.join(UPLOAD_FOLDER, f"WesmartAI_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
    pdf.output(output_path)
    return send_file(output_path, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
