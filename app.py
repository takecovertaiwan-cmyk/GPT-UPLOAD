# ====================================================================
# WesmartAI Archival System (v9.1-TC-DynamicData-FinalFont)
# Traditional Chinese Edition with Dynamic Data and Correct Font
# 1. Generates report based on actual user-uploaded image files.
# 2. Uses Traditional Chinese text to match the sample PDF.
# 3. CONFIGURED: Uses the 'NotoSansTC.otf' font file from your GitHub repo.
# 4. Removes mock data generation. Report ID and timestamps are dynamic.
# 5. Each uploaded image gets its own page with its hash value.
# ====================================================================

import os
import uuid
import datetime
import hashlib
import json
import qrcode
from flask import Flask, render_template, request, jsonify, url_for, session, send_from_directory
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image

# --- Flask Initialization ---
app = Flask(__name__)
app.secret_key = os.urandom(24)

static_folder = "static"
if not os.path.exists(static_folder):
    os.makedirs(static_folder)
app.config["UPLOAD_FOLDER"] = static_folder

# --- Configuration for allowed file types ---
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Utility Function ---
def sha256_file(filepath):
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

# --- PDF Report Generator (Traditional Chinese Version) ---
class WesmartPDFReport(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Load the Chinese font provided in your repository root.
        try:
            # ---> UPDATED to use your font file <---
            self.add_font("NotoSansTC", "", "NotoSansTC.otf")
            self.has_chinese_font = True
        except RuntimeError:
            self.has_chinese_font = False
            print("WARNING: 'NotoSansTC.otf' not found. PDF text will not render correctly.")

    def set_chinese_font(self, style="", size=12):
        if self.has_chinese_font:
            # ---> UPDATED to use your font name <---
            self.set_font("NotoSansTC", style, size)
        else:
            self.set_font("Helvetica", style, size) # Fallback font

    def footer(self):
        self.set_y(-15)
        self.set_chinese_font("I", 8)
        self.cell(0, 10, f"第 {self.page_no()} / {self.alias_nb_pages()} 頁", align="C")

    def create_cover(self, d):
        self.add_page()
        if os.path.exists("LOGO.jpg"):
            self.image("LOGO.jpg", x=10, y=8, w=50)
        
        self.set_y(60)
        self.set_chinese_font("B", 20)
        self.cell(0, 15, "WesmartAI 證據報告", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.ln(15)

        self.set_chinese_font("", 12)
        field_width = 45
        self.cell(field_width, 10, "出證申請人:")
        self.cell(0, 10, d['applicant_name'], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(field_width, 10, "申請事項:")
        self.cell(0, 10, d['application_matter'], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(field_width, 10, "出證時間:")
        self.cell(0, 10, d['report_timestamp_utc'], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(field_width, 10, "出證編號 (報告ID):")
        self.cell(0, 10, d['report_id'], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(field_width, 10, "出證單位:")
        self.cell(0, 10, d.get('issuing_unit', 'WesmartAI Inc.'), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def create_file_detail_pages(self, d):
        files = d.get("archived_files", [])
        
        for i, file_info in enumerate(files):
            self.add_page()
            
            self.set_chinese_font("B", 14)
            self.cell(0, 12, f"存證檔案快照 ({i+1}/{len(files)})", new_x=XPos.LMARGIN, new_y=YPos.NEXT, border='B')
            self.ln(10)
            
            image_path = os.path.join(app.config["UPLOAD_FOLDER"], file_info['stored_filename'])
            if os.path.exists(image_path):
                try:
                    with Image.open(image_path) as img:
                        w, h = img.size
                        aspect_ratio = h / w
                        display_w = 160 
                        display_h = display_w * aspect_ratio
                        if display_h > 180:
                            display_h = 180
                            display_w = display_h / aspect_ratio
                        
                        pos_x = (self.w - display_w) / 2
                        self.image(image_path, x=pos_x, y=self.get_y(), w=display_w, h=display_h)
                        self.set_y(self.get_y() + display_h + 10)
                except Exception as e:
                    self.cell(0, 10, f"[無法預覽圖片: {e}]", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

            self.set_chinese_font("B", 12)
            self.cell(0, 10, f"檔案索引: {i+1}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
            self.set_chinese_font("", 10)
            self.multi_cell(0, 7, f"- 原始檔名:\n  {file_info['original_filename']}")
            self.ln(2)
            self.multi_cell(0, 7, f"- 存證時間戳記 (UTC):\n  {file_info['timestamp_utc']}")
            self.ln(2)
            self.multi_cell(0, 7, f"- 檔案雜湊 (SHA-256):\n")
            self.set_font("Courier", "", 8)
            self.multi_cell(0, 5, f"  {file_info['sha256_hash']}")
            self.ln(2)

    def create_conclusion_page(self, d):
        self.add_page()
        self.set_chinese_font("B", 14)
        self.cell(0, 12, "報告驗證", new_x=XPos.LMARGIN, new_y=YPos.NEXT, border='B')
        self.ln(10)

        qr_data = json.dumps({"report_id": d['report_id'], "hash": d['report_main_hash']}, sort_keys=True)
        qr = qrcode.QRCode(version=1, box_size=8, border=4)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        qr_path = os.path.join(app.config["UPLOAD_FOLDER"], f"qr_{d['report_id']}.png")
        img.save(qr_path)
        
        self.set_chinese_font("", 11)
        self.cell(0, 10, "掃描 QR Code 前往驗證頁面", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.image(qr_path, w=80, h=80, x=65)
        self.ln(5)

        self.set_chinese_font("", 11)
        text = "本報告的真實性與完整性，取決於其對應的 'proof_event.json' 證據檔案。此 JSON 檔案的雜湊值 (Final Event Hash) 被記錄於下，可用於比對與驗證。"
        self.multi_cell(0, 8, text, align='L')
        self.ln(8)

        self.set_chinese_font("B", 12)
        self.cell(0, 8, "最終事件雜湊值 (Final Event Hash):", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Courier", "", 9)
        self.multi_cell(0, 5, d['report_main_hash'])

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
    if "file" not in request.files: return jsonify({"error": "No file part in request"}), 400
    file = request.files["file"]
    applicant_name = request.form.get("applicant_name", "N/A")
    if file.filename == "": return jsonify({"error": "No file selected"}), 400
    if not allowed_file(file.filename): return jsonify({"error": f"Invalid file type. Please upload an image ({', '.join(ALLOWED_EXTENSIONS)})"}), 400
    if not session.get("applicant_name") and applicant_name: session["applicant_name"] = applicant_name
        
    try:
        ext = os.path.splitext(file.filename)[1]
        file_uuid = str(uuid.uuid4())
        stored_filename = f"{file_uuid}{ext}"
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], stored_filename)
        file.save(filepath)
        file_hash = sha256_file(filepath)
        
        file_info = {
            "original_filename": file.filename,
            "stored_filename": stored_filename,
            "sha256_hash": file_hash,
            "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        
        uploaded_files = session.get("uploaded_files", [])
        uploaded_files.append(file_info)
        session["uploaded_files"] = uploaded_files
        
        return jsonify({
            "success": True, "message": "Image uploaded successfully", "stored_filename": stored_filename,
            "is_pdf": False, "preview_urls": [url_for("static_download", filename=stored_filename)]
        })
    except Exception as e:
        print(f"Upload failed: {e}")
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500

@app.route("/create_report", methods=["POST"])
def create_report():
    try:
        uploaded_files = session.get("uploaded_files", [])
        if not uploaded_files:
            return jsonify({"error": "No files have been uploaded to include in the report."}), 400

        proof_data = {
            "report_id": str(uuid.uuid4()),
            "applicant_name": session.get("applicant_name", "N/A"),
            "application_matter": "WesmartAI 檔案存證報告",
            "report_timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "issuing_unit": "WesmartAI Inc.",
            "archived_files": uploaded_files
        }
        
        proof_bytes = json.dumps(proof_data, sort_keys=True, ensure_ascii=False).encode("utf-8")
        main_hash = hashlib.sha256(proof_bytes).hexdigest()
        proof_data["report_main_hash"] = main_hash
        
        pdf = WesmartPDFReport()
        if not pdf.has_chinese_font:
             return jsonify({"error": "Server is missing Chinese font file, cannot generate report."}), 500

        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.alias_nb_pages()
        pdf.create_cover(proof_data)
        pdf.create_file_detail_pages(proof_data)
        pdf.create_conclusion_page(proof_data)
        
        report_filename = f"WesmartAI_Report_{proof_data['report_id']}.pdf"
        report_path = os.path.join(app.config["UPLOAD_FOLDER"], report_filename)
        pdf.output(report_path)
        
        return jsonify({
            "success": True, 
            "report_url": url_for("static_download", filename=report_filename)
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Report generation failed: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5001)
