from flask import Flask, render_template, request, send_file, jsonify
from fpdf import FPDF
import os, hashlib, datetime

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---- 計算 SHA256 ----
def calc_sha256(file_path):
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

# ---- 頁面 ----
@app.route("/")
def index():
    return render_template("index.html")

# ---- 預覽 ----
@app.route("/preview", methods=["POST"])
def preview():
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "no filename"}), 400
    save_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(save_path)
    sha256 = calc_sha256(save_path)
    return jsonify({"preview_url": f"/{save_path}", "sha256": sha256})

# ---- 生成 PDF ----
@app.route("/generate", methods=["POST"])
def generate_pdf():
    data = request.json or {}
    file_name = data.get("file_name", "")
    sha256 = data.get("sha256", "")
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    pdf = FPDF(format="A4")
    pdf.add_page()

    # 嘗試插入 LOGO
    if os.path.exists("LOGO.jpg"):
        try:
            pdf.image("LOGO.jpg", x=70, y=10, w=70)
            pdf.ln(40)
        except Exception as e:
            print("Logo insert error:", e)
            pdf.set_font("Helvetica", size=16)
            pdf.cell(0, 10, "WesmartAI Digital Evidence Report", ln=True, align="C")
    else:
        pdf.set_font("Helvetica", size=16)
        pdf.cell(0, 10, "WesmartAI Digital Evidence Report", ln=True, align="C")

    pdf.ln(10)
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, f"File: {file_name}", ln=True)
    pdf.cell(0, 10, f"SHA256: {sha256}", ln=True)
    pdf.cell(0, 10, f"Timestamp: {timestamp}", ln=True)

    # 嵌入圖片預覽
    img_path = os.path.join(UPLOAD_FOLDER, file_name)
    if os.path.exists(img_path):
        try:
            pdf.image(img_path, x=25, y=80, w=160)
        except Exception as e:
            print("Image insert error:", e)

    pdf.ln(120)
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(0, 8, (
        "Creative Process Statement:\n"
        "This report records the digital evidence chain starting from user input. "
        "Each artifact includes hash and timestamp to ensure integrity and verifiability."
    ))

    out_path = os.path.join(UPLOAD_FOLDER, f"report_{file_name}.pdf")
    pdf.output(out_path)
    return send_file(out_path, as_attachment=True)

# ---- 啟動 ----
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
