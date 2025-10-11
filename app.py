# ====================================================================
# WesmartAI Archival System (v8-EN-GenAI)
# English Edition for Generative AI Reports
# 1. Uses the structure from the sample PDF but with all English text.
# 2. Removed the Chinese font dependency and uses built-in Helvetica.
# 3. Retains the new data structure for AI generation tasks.
# 4. Uses hard-coded mock data for demonstration purposes.
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
from PIL import Image

# --- Flask Initialization ---
app = Flask(__name__)
app.secret_key = os.urandom(24)

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

# --- PDF Report Generator (English Version) ---
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
        self.add_page()
        task = d.get("generation_task", {})

        self.set_font("Helvetica", "B", 14)
        self.cell(0, 12, "1. Generation Task Information", new_x=XPos.LMARGIN, new_y=YPos.NEXT, border='B')
        self.ln(5)
        self.set_font("Helvetica", "", 11)
        self.cell(40, 8, "Trace Token:")
        self.set_font("Courier", "", 11)
        self.cell(0, 8, task.get("trace_token"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Helvetica", "", 11)
        self.cell(40, 8, "Total Versions:")
        self.cell(0, 8, str(task.get("total_versions")), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(10)

        self.set_font("Helvetica", "B", 14)
        self.cell(0, 12, "2. Snapshots of Generated Versions", new_x=XPos.LMARGIN, new_y=YPos.NEXT, border='B')
        self.ln(5)

        for version in task.get("versions", []):
            if self.get_y() > 160:
                self.add_page()

            self.set_font("Helvetica", "B", 12)
            self.cell(0, 10, f"Version Index: {version['index']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
            if os.path.exists(version['image_path']):
                self.image(version['image_path'], w=80, x=15)
            
            self.set_xy(100, self.get_y() - 80)
            
            self.set_font("Helvetica", "", 10)
            self.multi_cell(0, 7, f"- Timestamp (UTC):\n  {version['timestamp_utc']}")
            self.ln(2)
            self.set_x(100)
            self.multi_cell(0, 7, f"- Image Hash (SHA-256 over Base64):\n")
            self.set_font("Courier", "", 8)
            self.set_x(102)
            self.multi_cell(0, 4, f"{version['image_hash']}")
            self.ln(2)
            self.set_font("Helvetica", "", 10)
            self.set_x(100)
            self.multi_cell(0, 7, f"- Input Prompt:\n  {version['prompt']}")
            self.ln(2)
            self.set_x(100)
            self.multi_cell(0, 7, f"- Seed:\n  {version['seed']}")
            self.ln(30)

    def create_conclusion_page(self, d):
        self.add_page()
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 12, "3. Report Verification", new_x=XPos.LMARGIN, new_y=YPos.NEXT, border='B')
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

# The /upload route is kept, but it is NOT used by the new /create_report logic.
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
        # --- Create Mock Images for Demonstration ---
        img_folder = app.config["UPLOAD_FOLDER"]
        Image.new('RGB', (400, 400), color = '#1a237e').save(os.path.join(img_folder, "wolf.jpg"))
        Image.new('RGB', (400, 400), color = '#ffc107').save(os.path.join(img_folder, "lion.jpg"))
        Image.new('RGB', (400, 400), color = '#795548').save(os.path.join(img_folder, "bear.jpg"))

        # --- Mock Data Structure to Match Sample PDF (in English) ---
        proof_data = {
            "report_id": "9e55900e-ca03-46f0-9368-0b0f32282b35",
            "applicant_name": "Wes Huang",
            "application_matter": "WesmartAI Generative AI Evidence Report",
            "report_timestamp_utc": "2025-10-08T16:03:41.692913+00:00",
            "issuing_unit": "WesmartAI Inc.",
            "generation_task": {
                "trace_token": "3e6b72f0-96a6-4aea-9b94-bada98eed4de",
                "total_versions": 3,
                "versions": [
                    {
                        "index": 1,
                        "timestamp_utc": "2025-10-08T16:03:20.167531+00:00",
                        "image_hash": "c4b0845c7635a8e51c5f85777ccb3c8a67172b0c99fedc69cd038da9cb08a6f2",
                        "prompt": "WOLF",
                        "seed": "8516076",
                        "image_path": os.path.join(img_folder, "wolf.jpg")
                    },
                    {
                        "index": 2,
                        "timestamp_utc": "2025-10-08T16:03:28.452910+00:00",
                        "image_hash": "f2d3a17e2c908db6a2b5c5b0e1b6a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2a1",
                        "prompt": "LION",
                        "seed": "9924102",
                        "image_path": os.path.join(img_folder, "lion.jpg")
                    },
                    {
                        "index": 3,
                        "timestamp_utc": "2025-10-08T16:03:35.918245+00:00",
                        "image_hash": "a9b8c7d6e5f4a3b2c1d0e9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8",
                        "prompt": "BEAR",
                        "seed": "1130548",
                        "image_path": os.path.join(img_folder, "bear.jpg")
                    }
                ]
            }
        }
        
        # Calculate the main hash for the entire data structure
        proof_bytes = json.dumps(proof_data, sort_keys=True, ensure_ascii=False).encode("utf-8")
        main_hash = hashlib.sha256(proof_bytes).hexdigest()
        proof_data["report_main_hash"] = main_hash
        
        # Generate the PDF
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
        print(f"Report generation failed: {e}")
        # Add traceback for detailed debugging
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Report generation failed: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5001)
