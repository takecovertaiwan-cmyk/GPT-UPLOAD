# ====================================================================
# WesmartAI Evidence Report Web App (English PDF Version)
# Author: Gemini & User
# Core Architecture:
# 1. User flow: Generate multiple previews -> Finalize and download all original images -> Optionally generate a PDF report.
# 2. PDF report generation is now entirely in English to avoid font loading issues on deployment servers.
# 3. All dependencies on external font files have been removed.
# ====================================================================

import requests, json, hashlib, uuid, datetime, random, time, os, io, base64
from flask import Flask, render_template, request, jsonify, send_from_directory, url_for
from PIL import Image
from fpdf import FPDF
from fpdf.enums import XPos, YPos
import qrcode

# --- Read Environment Variables (Using BFL_API_KEY as per the original file) ---
API_key = os.getenv("BFL_API_KEY")
if not API_key:
    print("Warning: BFL_API_KEY environment variable is not set.")

# --- Flask App Initialization ---
app = Flask(__name__)
static_folder = 'static'
if not os.path.exists(static_folder): os.makedirs(static_folder)
app.config['UPLOAD_FOLDER'] = static_folder

# --- Helper Functions ---
def sha256_bytes(b): return hashlib.sha256(b).hexdigest()

# --- PDF Report Class (Modified to English) ---
class WesmartPDFReport(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Using built-in fonts, no need to add external ones.
        self.set_auto_page_break(auto=True, margin=25)
        self.alias_nb_pages()
        self.logo_path = "LOGO.jpg" if os.path.exists("LOGO.jpg") else None

    def header(self):
        if self.logo_path:
            with self.local_context(fill_opacity=0.08, stroke_opacity=0.08):
                img_w = 120
                center_x = (self.w - img_w) / 2
                center_y = (self.h - img_w) / 2
                self.image(self.logo_path, x=center_x, y=center_y, w=img_w)
        if self.page_no() > 1:
            self.set_font("Helvetica", "", 9)
            self.set_text_color(128)
            self.cell(0, 10, "WesmartAI Generative AI Evidence Report", new_x=XPos.LMARGIN, new_y=YPos.TOP, align='L')
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
        self.cell(0, 20, "WesmartAI Evidence Report", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.ln(20)
        self.set_font("Helvetica", "", 12)
        data = [
            ("Applicant:", meta.get('applicant', 'N/A')),
            ("Subject:", "WesmartAI Generative AI Evidence Report"),
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

    def create_generation_details_page(self, proof_data):
        self.add_page()
        self.chapter_title("I. Generation Task Information")
        self.set_font("Helvetica", "", 10)
        
        task_info = {
            "Trace Token": proof_data['event_proof']['trace_token'],
            "Total Number of Versions": len(proof_data['event_proof']['snapshots'])
        }
        for key, value in task_info.items():
            self.set_font("Helvetica", "B", 10)
            self.cell(60, 8, f"  {key}:", align='L')
            self.set_font("Helvetica", "", 10)
            self.multi_cell(0, 8, str(value), align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(10)

        self.chapter_title("II. Snapshots for Each Version")
        for snapshot in proof_data['event_proof']['snapshots']:
            self.set_font("Helvetica", "B", 12)
            self.cell(0, 10, f"Version Index: {snapshot['version_index']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
            self.ln(4)
            
            details = [
                ("Timestamp (UTC)", snapshot['timestamp_utc']),
                ("Image Hash (SHA-256 over Base64)", snapshot['snapshot_hash']),
                ("Prompt", snapshot['prompt']),
                ("Seed", snapshot['seed'])
            ]
            for key, value in details:
                self.set_font("Helvetica", "B", 10)
                self.cell(70, 7, f"  - {key}:", align='L')
                self.set_font("Helvetica", "", 9)
                self.multi_cell(0, 7, str(value), align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
            try:
                img_bytes = base64.b64decode(snapshot['content_base64'])
                img_file_obj = io.BytesIO(img_bytes)
                self.image(img_file_obj, w=150, x=(self.w - 150) / 2)
            except Exception as e:
                print(f"Failed to display image in PDF: {e}")
            self.ln(15)

    def create_conclusion_page(self, proof_data):
        self.add_page()
        self.chapter_title("III. Report Verification")
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
session_snapshots = []
latest_proof_data = None

# --- Main API Logic ---
def call_bfl_api(prompt, seed=None, width=512, height=512):
    # This is the logic from the original app.py
    url = "https://bfl-2.marscolony.space/bfl-api/v1/images/generation"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_key}"}
    payload = {
        "prompt": prompt, "model": "animagine-xl", "num_inference_steps": 30,
        "width": int(width), "height": int(height)
    }
    if seed: payload["seed"] = int(seed)
    else: payload["seed"] = random.randint(1, 2**32 - 1)
    
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json(), payload["seed"]

@app.route('/')
def index():
    global session_snapshots, latest_proof_data
    session_snapshots = []
    latest_proof_data = None
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate_image():
    try:
        data = request.json
        prompt = data.get('prompt')
        seed = data.get('seed')
        width = data.get('width', 512)
        height = data.get('height', 512)

        api_response, used_seed = call_bfl_api(prompt, seed, width, height)
        img_base64 = api_response['images'][0]
        
        snapshot = {
            "version_index": len(session_snapshots) + 1,
            "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "snapshot_hash": sha256_bytes(img_base64.encode('utf-8')),
            "prompt": prompt,
            "seed": used_seed,
            "content_base64": img_base64
        }
        session_snapshots.append(snapshot)
        
        preview_filename = f"preview_{snapshot['snapshot_hash'][:10]}.png"
        preview_filepath = os.path.join(app.config['UPLOAD_FOLDER'], preview_filename)
        with open(preview_filepath, "wb") as f:
            f.write(base64.b64decode(img_base64))

        return jsonify({
            "success": True,
            "preview_url": url_for('static_preview', filename=preview_filename),
            "version": snapshot['version_index']
        })
    except Exception as e:
        print(f"圖像生成失敗: {e}")
        return jsonify({"error": f"Image generation failed: {str(e)}"}), 500

@app.route('/finalize_session', methods=['POST'])
def finalize_session():
    global latest_proof_data
    applicant_name = request.json.get('applicant_name')
    if not applicant_name: return jsonify({"error": "Applicant name is required"}), 400
    if not session_snapshots: return jsonify({"error": "No images have been generated"}), 400

    try:
        image_urls = []
        for snapshot in session_snapshots:
            definitive_filename = f"definitive_{snapshot['snapshot_hash']}.png"
            definitive_filepath = os.path.join(app.config['UPLOAD_FOLDER'], definitive_filename)
            with open(definitive_filepath, "wb") as f:
                f.write(base64.b64decode(snapshot['content_base64']))
            image_urls.append(url_for('static_download', filename=definitive_filename))
        
        report_id = str(uuid.uuid4())
        trace_token = str(uuid.uuid4())
        issued_at_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        temp_proof_for_hashing = {"report_id": report_id, "event_proof": {"trace_token": trace_token, "snapshots": session_snapshots}}
        proof_string_for_hashing = json.dumps(temp_proof_for_hashing, sort_keys=True, ensure_ascii=False).encode('utf-8')
        final_event_hash = sha256_bytes(proof_string_for_hashing)

        proof_data = {
            "report_id": report_id, "issuer": "WesmartAI Inc.", "applicant": applicant_name, "issued_at": issued_at_iso,
            "event_proof": { "trace_token": trace_token, "final_event_hash": final_event_hash, "snapshots": session_snapshots },
            "verification": {"verify_url": f"https://wesmart.ai/verify?hash={final_event_hash}"}
        }
        
        json_filename = f"proof_event_{report_id}.json"
        json_filepath = os.path.join(app.config['UPLOAD_FOLDER'], json_filename)
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(proof_data, f, ensure_ascii=False, indent=2)
        
        latest_proof_data = proof_data
        return jsonify({"success": True, "image_urls": image_urls})

    except Exception as e:
        print(f"Session finalization failed: {e}")
        return jsonify({"error": f"Session finalization failed: {str(e)}"}), 500

@app.route('/create_report', methods=['POST'])
def create_report():
    if not latest_proof_data: return jsonify({"error": "Please finalize the session first to generate evidence"}), 400
    try:
        report_id = latest_proof_data['report_id']
        pdf = WesmartPDFReport()
        pdf.create_cover(latest_proof_data)
        pdf.create_generation_details_page(latest_proof_data)
        pdf.create_conclusion_page(latest_proof_data)
        
        report_filename = f"WesmartAI_Report_{report_id}.pdf"
        report_filepath = os.path.join(app.config['UPLOAD_FOLDER'], report_filename)
        pdf.output(report_filepath)

        return jsonify({"success": True, "report_url": url_for('static_download', filename=report_filename)})
    except Exception as e:
        print(f"Report generation failed: {e}")
        return jsonify({"error": f"Report generation failed: {str(e)}"}), 500

# --- Static File Routes ---
@app.route('/static/preview/<path:filename>')
def static_preview(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/static/download/<path:filename>')
def static_download(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
