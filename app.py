# ====================================================================
# WesmartAI Notarization System (Final Version)
# Author: Gemini & User
# Core Logic:
# 1. User UPLOADS an image. The system is for notarization, NOT generation.
# 2. The server calculates the image's hash locally using hashlib.
# 3. The server calls the GPT API, sending the hash to get a "notarization statement".
# 4. An all-English PDF report is generated using built-in fonts, guaranteeing success on any platform.
# ====================================================================

import json, hashlib, uuid, datetime, os, io, base64
from flask import Flask, render_template, request, jsonify, send_from_directory, url_for
from PIL import Image
from fpdf import FPDF
from fpdf.enums import XPos, YPos
import qrcode
from werkzeug.utils import secure_filename
import openai

# --- Read Environment Variables for OpenAI ---
try:
    openai.api_key = os.getenv("OPENAI_API_KEY")
    if not openai.api_key:
        print("Warning: OPENAI_API_KEY environment variable is not set. AI Notarization will fail.")
except Exception as e:
    print(f"Error reading OpenAI API Key: {e}")

# --- Flask App Initialization ---
app = Flask(__name__)
static_folder = 'static'
if not os.path.exists(static_folder): os.makedirs(static_folder)
app.config['UPLOAD_FOLDER'] = static_folder
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# --- Helper Functions ---
def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# --- GPT API Call for Notarization ---
def get_gpt_notarization(image_hash, timestamp_utc):
    if not openai.api_key:
        return "Error: OpenAI API Key is not configured. AI Notarization is unavailable."
    
    prompt_content = f"""
    As a Digital Notary Public, please provide a standard confirmation statement for the following digital asset notarization event.
    Your response must explicitly include these two key pieces of information:
    1.  **Image Hash (SHA-256)**: `{image_hash}`
    2.  **Notarization Timestamp (UTC)**: `{timestamp_utc}`
    Please reply in a concise, formal format confirming that you have recorded this event.
    """
    try:
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a Digital Notary Public. Your duty is to provide formal confirmation statements for the data you receive."},
                {"role": "user", "content": prompt_content}
            ],
            temperature=0.2,
            max_tokens=250
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Call to GPT API failed: {e}")
        return f"AI Notarization failed: Could not connect to OpenAI service. Error: {str(e)}"

# --- PDF Report Class (All English, No External Fonts) ---
class WesmartPDFReport(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_auto_page_break(auto=True, margin=25)
        self.alias_nb_pages()
        self.logo_path = "LOGO.jpg" if os.path.exists("LOGO.jpg") else None

    def header(self):
        if self.logo_path:
            with self.local_context(fill_opacity=0.08):
                img_w, center_x, center_y = 120, (self.w - 120) / 2, (self.h - 120) / 2
                self.image(self.logo_path, x=center_x, y=center_y, w=img_w)
        if self.page_no() > 1:
            self.set_font("Helvetica", "", 9)
            self.set_text_color(128)
            self.cell(0, 10, "WesmartAI Third-Party Notarization Report", new_x=XPos.LMARGIN, new_y=YPos.TOP, align='L')
            self.cell(0, 10, "WesmartAI Inc.", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(128)
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', align='C')

    def chapter_title(self, title):
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(0)
        self.cell(0, 12, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
        self.ln(6)

    def chapter_body(self, content):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(50)
        self.multi_cell(0, 7, content, align='L')
        self.ln()

    def create_cover(self, meta):
        self.add_page()
        if self.logo_path: self.image(self.logo_path, x=(self.w - 60) / 2, y=25, w=60)
        self.set_y(100)
        self.set_font("Helvetica", "B", 28)
        self.cell(0, 20, "WesmartAI Notarization Report", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.ln(20)
        self.set_font("Helvetica", "", 12)
        data = [
            ("Applicant:", meta.get('applicant', 'N/A')),
            ("Subject:", "WesmartAI Image Upload Notarization Report"),
            ("Time of Issuance (UTC):", meta.get('issued_at', 'N/A')),
            ("Report ID:", meta.get('report_id', 'N/A')),
            ("Issuing Body:", meta.get('issuer', 'N/A'))
        ]
        for row in data:
            self.cell(20)
            self.set_font("Helvetica", "B", 11)
            self.cell(55, 10, row[0], align='L')
            self.set_font("Helvetica", "", 11)
            self.multi_cell(0, 10, row[1], new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')

    def create_evidence_pages(self, proof_data):
        self.chapter_title("I. Notarized Image Details")
        for snapshot in proof_data['event_proof']['snapshots']:
            self.add_page()
            self.set_font("Helvetica", "B", 12)
            self.cell(0, 10, f"Image Index: {snapshot['version_index']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
            self.ln(4)
            
            details = [
                ("Timestamp (UTC)", snapshot['timestamp_utc']),
                ("Image Hash (SHA-256)", snapshot['snapshot_hash'])
            ]
            for key, value in details:
                self.set_font("Helvetica", "B", 10)
                self.cell(60, 7, f"  - {key}:", align='L')
                self.set_font("Helvetica", "", 9)
                self.multi_cell(0, 7, str(value), align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(5)

            self.set_font("Helvetica", "B", 10)
            self.cell(0, 7, "  - AI Notarization Record (by GPT-4o-mini):", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font("Helvetica", "", 9)
            self.set_text_color(80)
            with self.local_context(x=self.get_x() + 5):
                 self.multi_cell(0, 6, snapshot.get('gpt_notarization', 'N/A'), border=1, padding=3)
            self.ln(10)

            try:
                img_bytes = base64.b64decode(snapshot['content_base64'])
                self.image(io.BytesIO(img_bytes), w=150, x=(self.w - 150) / 2)
            except Exception as e:
                print(f"Failed to display image in PDF: {e}")

    def create_conclusion_page(self, proof_data):
        self.add_page()
        self.chapter_title("II. Report Verification")
        self.chapter_body("The authenticity and integrity of this report depend on its corresponding `proof_event.json` evidence file. The hash of this JSON file (Final Event Hash) is recorded below for comparison and verification.")
        self.ln(10)
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 10, "Final Event Hash:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Courier", "B", 11)
        self.multi_cell(0, 8, proof_data['event_proof']['final_event_hash'], border=1, align='C', padding=5)
        
        qr_data = proof_data['verification']['verify_url']
        qr = qrcode.make(qr_data)
        qr_path = os.path.join(app.config['UPLOAD_FOLDER'], f"qr_{proof_data['report_id'][:10]}.png")
        qr.save(qr_path)
        
        self.ln(10)
        self.set_font("Helvetica", "", 10)
        self.cell(0, 10, "Scan QR Code to visit the verification page", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.image(qr_path, w=50, x=(self.w - 50) / 2)

# --- Global Variables ---
session_uploads = []
latest_proof_data = None

# --- Flask Routes ---
@app.route('/')
def index():
    global session_uploads, latest_proof_data
    session_uploads = []
    latest_proof_data = None
    return render_template('index.html') # You will need a matching index.html

@app.route('/upload', methods=['POST'])
def upload_image():
    if 'image' not in request.files: return jsonify({"error": "No image file in request"}), 400
    file = request.files['image']
    if file.filename == '': return jsonify({"error": "No file selected"}), 400
    
    if file and allowed_file(file.filename):
        try:
            unique_filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)

            with open(filepath, "rb") as f: img_bytes = f.read()
            file_hash = sha256_bytes(img_bytes)
            timestamp_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

            print(f"Requesting AI notarization for image hash: {file_hash[:10]}...")
            gpt_response = get_gpt_notarization(file_hash, timestamp_utc)
            print("AI notarization received.")

            session_uploads.append({
                "filepath": filepath,
                "file_hash": file_hash,
                "timestamp_utc": timestamp_utc,
                "gpt_notarization": gpt_response
            })
            
            return jsonify({
                "success": True,
                "preview_url": url_for('static_preview', filename=unique_filename),
                "version": len(session_uploads)
            })
        except Exception as e:
            return jsonify({"error": f"File processing failed: {str(e)}"}), 500
    else:
        return jsonify({"error": "Unsupported file type"}), 400

@app.route('/finalize_session', methods=['POST'])
def finalize_session():
    global latest_proof_data
    applicant_name = request.json.get('applicant_name')
    if not applicant_name: return jsonify({"error": "Applicant name is required"}), 400
    if not session_uploads: return jsonify({"error": "No images have been uploaded"}), 400

    try:
        snapshots = []
        for i, upload in enumerate(session_uploads):
            with open(upload['filepath'], "rb") as f: img_bytes = f.read()
            img_base64_str = base64.b64encode(img_bytes).decode('utf-8')
            
            snapshots.append({
                "version_index": i + 1,
                "timestamp_utc": upload['timestamp_utc'],
                "snapshot_hash": upload['file_hash'],
                "gpt_notarization": upload['gpt_notarization'],
                "content_base64": img_base64_str
            })
        
        report_id = str(uuid.uuid4())
        trace_token = str(uuid.uuid4())
        issued_at_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        # The hash is now calculated over all data, including the AI notarization
        temp_proof = {"report_id": report_id, "event_proof": {"trace_token": trace_token, "snapshots": snapshots}}
        final_event_hash = sha256_bytes(json.dumps(temp_proof, sort_keys=True).encode('utf-8'))

        proof_data = {
            "report_id": report_id, "issuer": "WesmartAI Inc.", "applicant": applicant_name, "issued_at": issued_at_iso,
            "event_proof": { "trace_token": trace_token, "final_event_hash": final_event_hash, "snapshots": snapshots },
            "verification": {"verify_url": f"https://wesmart.ai/verify?hash={final_event_hash}"}
        }
        
        json_filename = f"proof_event_{report_id}.json"
        json_filepath = os.path.join(app.config['UPLOAD_FOLDER'], json_filename)
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(proof_data, f, ensure_ascii=False, indent=2)

        latest_proof_data = proof_data
        return jsonify({"success": True, "report_id": report_id})
    except Exception as e:
        print(f"Session finalization failed: {e}")
        return jsonify({"error": f"Session finalization failed: {str(e)}"}), 500

@app.route('/create_report', methods=['POST'])
def create_report():
    if not latest_proof_data: return jsonify({"error": "Please finalize the session first"}), 400
    try:
        pdf = WesmartPDFReport()
        pdf.create_cover(latest_proof_data)
        pdf.create_evidence_pages(latest_proof_data)
        pdf.create_conclusion_page(latest_proof_data)
        
        report_id = latest_proof_data['report_id']
        report_filename = f"WesmartAI_Report_{report_id}.pdf"
        report_filepath = os.path.join(app.config['UPLOAD_FOLDER'], report_filename)
        pdf.output(report_filepath)

        return jsonify({"success": True, "report_url": url_for('static_download', filename=report_filename)})
    except Exception as e:
        print(f"Report generation failed: {e}")
        return jsonify({"error": f"Report generation failed: {str(e)}"}), 500

@app.route('/static/preview/<path:filename>')
def static_preview(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/static/download/<path:filename>')
def static_download(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
