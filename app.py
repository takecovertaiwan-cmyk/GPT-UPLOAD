# ====================================================================
# WesmartAI Archival System (v9-EN-Final)
# Final English Edition for Contract Archival
# 1. Generates realistic mock contract images instead of color blocks.
# 2. Each image preview is displayed on its own separate page.
# 3. Simplified detail pages to show only the large image and its hash.
# 4. Retains the overall report structure (cover, details, verification).
# ====================================================================

import os
import uuid
import datetime
import hashlib
import json
import qrcode
import fitz # This is PyMuPDF, kept for potential future use
from flask import Flask, render_template, request, jsonify, url_for, session, send_from_directory
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image, ImageDraw, ImageFont

# --- Flask Initialization ---
app = Flask(__name__)
app.secret_key = os.urandom(24)

static_folder = "static"
if not os.path.exists(static_folder):
    os.makedirs(static_folder)
app.config["UPLOAD_FOLDER"] = static_folder

# --- Utility Functions ---
def sha256_file(filepath):
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

# Function to create a mock contract image for demonstration
def create_mock_contract_image(filepath, page_num, total_pages):
    img = Image.new('RGB', (800, 1100), color = 'white')
    d = ImageDraw.Draw(img)
    
    # Try to use a common font, fallback to default if not found
    try:
        font_header = ImageFont.truetype("arial.ttf", 40)
        font_text = ImageFont.truetype("arial.ttf", 20)
    except IOError:
        font_header = ImageFont.load_default()
        font_text = ImageFont.load_default()

    d.text((50, 50), "CONFIDENTIAL AGREEMENT", fill=(0,0,0), font=font_header)
    
    sample_text = """
    This Agreement is made and entered into as of this day by and between
    Party A ("Disclosing Party") and Party B ("Receiving Party").

    1.  Confidential Information. The term "Confidential Information" shall
        include any and all information, whether written or oral, that is
        disclosed or made available by the Disclosing Party to the
        Receiving Party.

    2.  Obligations. The Receiving Party shall hold and maintain the
        Confidential Information in strictest confidence for the sole and
        exclusive benefit of the Disclosing Party.

    3.  Term. The nondisclosure provisions of this Agreement shall survive
        the termination of this Agreement and the Receiving Party's duty
        to hold Confidential Information in confidence shall remain in
        effect until the Confidential Information no longer qualifies as a
        trade secret.
        
    [... More legal text follows ...]
    """
    d.multiline_text((50, 150), sample_text, fill=(0,0,0), font=font_text)
    d.text((400, 1050), f"- Page {page_num} of {total_pages} -", fill=(100,100,100), font=font_text)
    img.save(filepath)

# --- PDF Report Generator (Final Version) ---
class WesmartPDFReport(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}/{self.alias_nb_pages()}", align="C")

    def create_cover(self, d):
        self.add_page()
        if os.path.exists("LOGO.jpg"):
            self.image("LOGO.jpg", x=10, y=8, w=50)
        self.set_y(60)
        self.set_font("Helvetica", "B", 20)
        self.cell(0, 15, "WesmartAI Evidence Report", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.ln(15)
        self.set_font("Helvetica", "", 12)
        field_width = 50
        self.cell(field_width, 10, "Applicant:")
        self.cell(0, 10, d['applicant_name'], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(field_width, 10, "Subject:")
        self.cell(0, 10, d['application_matter'], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(field_width, 10, "Timestamp (UTC):")
        self.cell(0, 10, d['report_timestamp_utc'], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(field_width, 10, "Report ID:")
        self.cell(0, 10, d['report_id'], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(field_width, 10, "Issuing Unit:")
        self.cell(0, 10, d.get('issuing_unit', 'WesmartAI Inc.'), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def create_generation_details(self, d):
        task = d.get("generation_task", {})

        for version in task.get("versions", []):
            # --- Each version gets its own page ---
            self.add_page()
            
            self.set_font("Helvetica", "B", 14)
            self.cell(0, 12, f"Evidence Snapshot - Index: {version['index']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, border='B')
            self.ln(10)
            
            # --- Display large, clear image ---
            if os.path.exists(version['image_path']):
                # A4 page width is 210mm, margins are 10mm each side. Usable width is ~190mm
                self.image(version['image_path'], w=190)
            
            self.ln(5)

            # --- Simplified details: Only the hash ---
            self.set_font("Helvetica", "B", 11)
            self.cell(0, 8, "Image Hash (SHA-256):", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font("Courier", "", 9)
            self.multi_cell(0, 5, version['image_hash'])

    def create_conclusion_page(self, d):
        self.add_page()
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 12, "Report Verification", new_x=XPos.LMARGIN, new_y=YPos.NEXT, border='B')
        self.ln(10)
        qr_data = json.dumps(d, sort_keys=True, ensure_ascii=False)
        qr = qrcode.QRCode(version=1, box_size=8, border=4)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        qr_path = os.path.join(app.config["UPLOAD_FOLDER"], f"qr_{d['report_id']}.png")
        img.save(qr_path)
        self.set_font("Helvetica", "", 11)
        self.cell(0, 10, "Scan QR Code to visit the verification page", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.image(qr_path, w=80, h=80, x=65)
        self.ln(5)
        self.set_font("Helvetica", "", 11)
        text = "The authenticity and integrity of this report depend on its corresponding 'proof_event.json' evidence file. The hash of this JSON file (Final Event Hash) is recorded below and can be used for comparison and verification."
        self.multi_cell(0, 8, text, align='L')
        self.ln(8)
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 8, "Final Event Hash:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
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
    # ... (original upload logic remains here, unchanged)
    if "file" not in request.files: return jsonify({"error": "No file part in request"}), 400
    file = request.files["file"]
    applicant_name = request.form.get("applicant_name", "N/A")
    if file.filename == "": return jsonify({"error": "No file selected"}), 400
    if not session.get("applicant_name") and applicant_name: session["applicant_name"] = applicant_name
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
    try:
        # --- Create Mock Contract Images for a Realistic Demonstration ---
        img_folder = app.config["UPLOAD_FOLDER"]
        total_versions = 3
        image_paths = []
        for i in range(total_versions):
            path = os.path.join(img_folder, f"contract_page_{i+1}.jpg")
            create_mock_contract_image(path, i+1, total_versions)
            image_paths.append(path)

        # --- Simplified Mock Data Structure ---
        proof_data = {
            "report_id": "9e55900e-ca03-46f0-9368-0b0f32282b35",
            "applicant_name": "Wes Huang",
            "application_matter": "WesmartAI Contract Archival Report",
            "report_timestamp_utc": "2025-10-08T16:03:41.692913+00:00",
            "issuing_unit": "WesmartAI Inc.",
            "generation_task": {
                "trace_token": "3e6b72f0-96a6-4aea-9b94-bada98eed4de",
                "total_versions": total_versions,
                "versions": [
                    {
                        "index": 1,
                        "timestamp_utc": "2025-10-08T16:03:20.167531+00:00",
                        "image_hash": sha256_file(image_paths[0]),
                        "image_path": image_paths[0]
                    },
                    {
                        "index": 2,
                        "timestamp_utc": "2025-10-08T16:03:28.452910+00:00",
                        "image_hash": sha256_file(image_paths[1]),
                        "image_path": image_paths[1]
                    },
                    {
                        "index": 3,
                        "timestamp_utc": "2025-10-08T16:03:35.918245+00:00",
                        "image_hash": sha256_file(image_paths[2]),
                        "image_path": image_paths[2]
                    }
                ]
            }
        }
        
        proof_bytes = json.dumps(proof_data, sort_keys=True, ensure_ascii=False).encode("utf-8")
        main_hash = hashlib.sha256(proof_bytes).hexdigest()
        proof_data["report_main_hash"] = main_hash
        
        pdf = WesmartPDFReport()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.create_cover(proof_data)
        pdf.create_generation_details(proof_data)
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
