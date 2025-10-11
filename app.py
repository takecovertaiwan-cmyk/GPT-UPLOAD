# ====================================================================
# WesmartAI Archival System (v6-EN)
# English Edition — Compatible with Render/Colab
# 1. Removed all Chinese text and font dependencies
# 2. All headers, labels, and report fields converted to English
# 3. Uses built-in Helvetica font (no TTF required)
# ====================================================================

import os
import uuid
import datetime
import hashlib
import json
import qrcode
import openai
import fitz
from flask import Flask, render_template, request, jsonify, url_for, session, send_from_directory
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image, ImageDraw, ImageFont

# --- Flask Initialization ---
app = Flask(__name__)
app.secret_key = os.urandom(24)

openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    print("Warning: OPENAI_API_KEY not found. AI summarization will be disabled.")

static_folder = "static"
if not os.path.exists(static_folder):
    os.makedirs(static_folder)
app.config["UPLOAD_FOLDER"] = static_folder

# --- Utility Function ---
def sha256_file(filepath):
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

# --- Text Rendering Helper (for headers) ---
def render_text_to_image(text, image_path, font_size=22):
    """Render header text into transparent PNG image."""
    font = ImageFont.load_default()
    bbox = font.getbbox(text)
    w, h = bbox[2] + 30, bbox[3] + 15
    img = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    draw.text((10, 5), text, font=font, fill=(0, 0, 0))
    img.save(image_path)

# --- PDF Report Generator ---
class WesmartPDFReport(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title_images = {}
        self.preload_titles()

    def preload_titles(self):
        """Pre-render static title images."""
        titles = {
            "main_header": ("WesmartAI Digital Evidence Report", 14),
            "cover_title": ("WesmartAI Archival Proof Report", 24),
            "details_header": ("Archived File Details", 16),
            "conclusion_header": ("Report Summary & Verification", 16),
        }
        for key, (text, size) in titles.items():
            path = os.path.join(app.config["UPLOAD_FOLDER"], f"title_{key}.png")
            render_text_to_image(text, path, size)
            self.title_images[key] = path

    def header(self):
        if os.path.exists("LOGO.jpg"):
            self.image("LOGO.jpg", x=10, y=8, w=30)
        if "main_header" in self.title_images:
            self.image(self.title_images["main_header"], w=120, x=50, y=12)
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

    def create_cover(self, d):
        self.add_page()
        if "cover_title" in self.title_images:
            self.image(self.title_images["cover_title"], w=150, x=30)
        self.ln(25)

        self.set_font("Helvetica", "", 12)
        self.cell(0, 10, f"Report ID: {d['report_id']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 10, f"Applicant: {d['applicant_name']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 10, f"Generated at (UTC): {d['report_timestamp_utc']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 10, f"Total Files Archived: {len(d['files'])}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(10)
        self.multi_cell(0, 10, "This report records all files submitted by the applicant at the above timestamp. Detailed metadata and hash verifications are listed on the following pages.")

    def create_file_details_page(self, proof_data):
        self.add_page()
        if "details_header" in self.title_images:
            self.image(self.title_images["details_header"], w=100, x=55, y=self.get_y() + 5)
        self.ln(25)

        for i, file_info in enumerate(proof_data["files"]):
            self.set_font("Helvetica", "B", 12)
            self.set_fill_color(220, 220, 220)
            self.cell(0, 10, f"File #{i+1}: {file_info['original_filename']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True, border=1)
            self.set_font("Courier", "", 9)
            self.multi_cell(0, 6, f"SHA256: {file_info['sha256_hash']}", border="LR", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.cell(0, 2, "", border="LBR", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            if file_info.get("analysis"):
                self.set_font("Helvetica", "I", 10)
                self.multi_cell(0, 7, f"AI Summary:\n{file_info['analysis']}", border=0)
            if "pages" in file_info and file_info["pages"]:
                self.set_font("Helvetica", "B", 11)
                self.cell(0, 8, "Preview Details:", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=False)
                for page_data in file_info["pages"]:
                    if self.get_y() > 220:
                        self.add_page()
                    img_path = os.path.join(app.config["UPLOAD_FOLDER"], page_data["preview_filename"])
                    if os.path.exists(img_path):
                        self.image(img_path, x=self.get_x() + 5, y=self.get_y() + 5, w=70)
                    self.set_xy(self.get_x() + 80, self.get_y())
                    self.set_font("Helvetica", "", 10)
                    self.multi_cell(110, 6, f"Page: {page_data['page_num']}\nPreview File: {page_data['preview_filename']}", border=0)
                    self.set_font("Courier", "", 8)
                    self.multi_cell(110, 4, f"SHA256: {page_data['sha256_hash']}", border=0)
                    self.ln(60)
            self.ln(10)

    def create_conclusion_page(self, d):
        self.add_page()
        if "conclusion_header" in self.title_images:
            self.image(self.title_images["conclusion_header"], w=100, x=55, y=self.get_y() + 5)
        self.ln(25)

        qr_data = json.dumps(d, sort_keys=True, ensure_ascii=False)
        qr = qrcode.QRCode(version=1, box_size=8, border=4)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        qr_path = os.path.join(app.config["UPLOAD_FOLDER"], f"qr_{d['report_id']}.png")
        img.save(qr_path)

        self.image(qr_path, w=80, h=80, x=self.get_x() + 110)
        self.set_font("Helvetica", "", 11)
        self.multi_cell(100, 8, "All metadata and file hashes have been serialized and summarized in the main verification hash below. You can scan the QR code to verify the integrity and authenticity of this report.")
        self.ln(10)
        self.set_font("Courier", "B", 10)
        self.multi_cell(0, 5, f"Main Verification Hash (SHA256):\n{d['report_main_hash']}")

# --- Flask Routes ---
@app.route("/")
def index():
    session.clear()
    return render_template("index.html")

@app.route("/static/<path:filename>")
def static_download(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file part in request"}), 400
    file = request.files["file"]
    applicant_name = request.form.get("applicant_name", "N/A")
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not session.get("applicant_name") and applicant_name:
        session["applicant_name"] = applicant_name
    try:
        ext = os.path.splitext(file.filename)[1]
        file_uuid = str(uuid.uuid4())
        stored_filename = f"{file_uuid}{ext}"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], stored_filename)
        file.save(filepath)
        file_hash = sha256_file(filepath)
        preview_urls = []
        pages_data = []
        if ext.lower() == ".pdf":
            doc = fitz.open(filepath)
            for i in range(len(doc)):
                page = doc.load_page(i)
                pix = page.get_pixmap(dpi=150)
                preview_filename = f"{file_uuid}_page_{i + 1}.jpg"
                preview_filepath = os.path.join(app.config["UPLOAD_FOLDER"], preview_filename)
                pix.save(preview_filepath)
                preview_hash = sha256_file(preview_filepath)
                preview_urls.append(url_for("static_download", filename=preview_filename))
                pages_data.append({"page_num": i + 1, "preview_filename": preview_filename, "sha256_hash": preview_hash})
            doc.close()
        file_info = {"original_filename": file.filename, "stored_filename": stored_filename, "sha256_hash": file_hash, "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "pages": pages_data}
        uploaded_files = session.get("uploaded_files", [])
        uploaded_files.append(file_info)
        session["uploaded_files"] = uploaded_files
        return jsonify({"success": True, "message": "File uploaded successfully", "stored_filename": stored_filename, "is_pdf": ext.lower() == ".pdf", "preview_urls": preview_urls})
    except Exception as e:
        print(f"Upload failed: {e}")
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500

@app.route("/create_report", methods=["POST"])
def create_report():
    uploaded_files = session.get("uploaded_files", [])
    applicant_name = session.get("applicant_name", "N/A")
    if not uploaded_files:
        return jsonify({"error": "No uploaded files to generate report"}), 400
    try:
        report_id = str(uuid.uuid4())
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        proof_data = {"report_id": report_id, "applicant_name": applicant_name, "report_timestamp_utc": timestamp, "files": uploaded_files}
        proof_bytes = json.dumps(proof_data, sort_keys=True, ensure_ascii=False).encode("utf-8")
        main_hash = hashlib.sha256(proof_bytes).hexdigest()
        proof_data["report_main_hash"] = main_hash
        pdf = WesmartPDFReport()
        pdf.create_cover(proof_data)
        pdf.create_file_details_page(proof_data)
        pdf.create_conclusion_page(proof_data)
        report_filename = f"WesmartAI_Report_{report_id}.pdf"
        report_path = os.path.join(app.config["UPLOAD_FOLDER"], report_filename)
        pdf.output(report_path)
        session.pop("uploaded_files", None)
        session.pop("applicant_name", None)
        return jsonify({"success": True, "report_url": url_for("static_download", filename=report_filename)})
    except Exception as e:
        print(f"Report generation failed: {e}")
        return jsonify({"error": f"Report generation failed: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5001)
