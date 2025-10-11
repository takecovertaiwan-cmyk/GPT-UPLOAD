# ====================================================================
# WesmartAI 存證系統 (v4 - 逐頁雜湊與報告內預覽)
# 核心升級:
# 1. 在 /upload 接口中，對 PDF 轉出的每一頁 JPG 預覽圖，都單獨計算 SHA256 雜湊值。
# 2. 將原始檔案及其所有衍生頁面的雜湊資訊，以巢狀結構完整存入 session。
# 3. 大幅修改 WesmartPDFReport 類別，使其能夠在最終報告中，
#    圖文並茂地展示原始檔案資訊、每一頁的預覽圖及其對應的獨立雜湊值。
# ====================================================================

import os
import uuid
import datetime
import hashlib
import json
import qrcode
import openai
import fitz  # PyMuPDF
from flask import Flask, render_template, request, jsonify, url_for, session, send_from_directory
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image

# --- Flask App 初始化 ---
app = Flask(__name__)
app.secret_key = os.urandom(24)

openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    print("警告: 找不到 OPENAI_API_KEY 環境變數。AI 分析功能將無法使用。")

static_folder = 'static'
if not os.path.exists(static_folder):
    os.makedirs(static_folder)
app.config['UPLOAD_FOLDER'] = static_folder

# --- 輔助函式 ---
def sha256_file(filepath):
    """計算檔案的 SHA256 雜湊值"""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

# --- PDF 報告生成類別 (已大幅修改) ---

class WesmartPDFReport(FPDF):
    def header(self):
        self.set_font('helvetica', 'B', 12); self.image('LOGO.jpg', x=10, y=8, w=30); self.cell(0, 10, 'WesmartAI 可信智慧科技存證報告', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C'); self.ln(20)
    def footer(self):
        self.set_y(-15); self.set_font('helvetica', 'I', 8); self.cell(0, 10, f'頁碼 {self.page_no()}', align='C')
    def add_cjk_font(self):
        try:
            self.add_font('TaipeiSans', '', 'TaipeiSansTCBeta-Regular.ttf'); self.set_font('TaipeiSans', '', 12)
        except RuntimeError:
            print("警告: 找不到中文字體 'TaipeiSansTCBeta-Regular.ttf'。"); self.set_font('helvetica', '', 12)
            
    def create_cover(self, d):
        self.add_page(); self.add_cjk_font(); self.set_font_size(24); self.cell(0, 20, 'WesmartAI 數位證據存證報告', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C'); self.ln(20); self.set_font_size(12); self.cell(0, 10, f"報告 ID: {d['report_id']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT); self.cell(0, 10, f"出證申請人: {d['applicant_name']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT); self.cell(0, 10, f"報告生成時間: {d['report_timestamp_utc']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT); self.cell(0, 10, f"存證檔案總數: {len(d['files'])}", new_x=XPos.LMARGIN, new_y=YPos.NEXT); self.ln(10); self.multi_cell(0, 10, "本報告記錄了在上述時間由指定申請人提交用於存證的數位檔案。詳細的檔案資訊和驗證雜湊值記錄於後續頁面。")

    def create_file_details_page(self, proof_data):
        self.add_page(); self.add_cjk_font(); self.set_font_size(16); self.cell(0, 15, '存證檔案詳細紀錄', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
        
        for i, file_info in enumerate(proof_data['files']):
            self.set_font_size(12)
            self.set_fill_color(220, 220, 220)
            self.cell(0, 10, f"主要檔案 #{i+1}: {file_info['original_filename']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True, border=1)
            
            # 顯示主要檔案的雜湊值
            self.set_font('Courier', '', 9)
            self.multi_cell(0, 5, f"SHA256: {file_info['sha256_hash']}", border='LR', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.cell(0, 2, '', border='LBR', new_x=XPos.LMARGIN, new_y=YPos.NEXT) # 增加間隔
            
            self.add_cjk_font() # 恢復中文字體
            self.set_font_size(12)
            
            # 如果有 AI 分析，顯示它
            if file_info.get('analysis'):
                self.ln(2); self.set_font_size(11); self.set_text_color(70, 70, 70)
                self.multi_cell(0, 7, f"AI 摘要分析:\n{file_info['analysis']}", border=0)
                self.set_text_color(0, 0, 0); self.set_font_size(12); self.ln(5)

            # --- 新增: 處理並顯示衍生頁面 (預覽圖) ---
            if 'pages' in file_info and file_info['pages']:
                self.set_font_size(11); self.set_fill_color(240, 240, 240)
                self.cell(0, 8, '衍生預覽圖詳細資料:', new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
                
                for page_data in file_info['pages']:
                    # 檢查空間是否足夠，不足則換頁
                    if self.get_y() > 220: self.add_page(); self.add_cjk_font()
                        
                    page_image_path = os.path.join(app.config['UPLOAD_FOLDER'], page_data['preview_filename'])
                    if os.path.exists(page_image_path):
                        self.image(page_image_path, x=self.get_x()+5, y=self.get_y()+5, w=70)

                    self.set_xy(self.get_x() + 80, self.get_y()) # 移動到圖片右側
                    self.multi_cell(110, 6, f"頁碼: {page_data['page_num']}\n"
                                             f"檔名: {page_data['preview_filename']}", border=0)
                    self.set_x(self.get_x() + 80) # 再次定位
                    self.set_font('Courier', '', 8)
                    self.multi_cell(110, 4, f"SHA256: {page_data['sha256_hash']}", border=0)
                    self.add_cjk_font(); self.set_font_size(11)
                    self.ln(60) # 為圖片和文字保留足夠空間

            self.ln(10)

    def create_conclusion_page(self, d):
        # ... (此處程式碼與前一版相同，為節省篇幅故省略) ...
        self.add_page(); self.add_cjk_font(); self.set_font_size(16); self.cell(0, 15, '報告總結與驗證', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L'); self.set_font_size(12); qr_data = json.dumps(d, sort_keys=True, ensure_ascii=False); qr = qrcode.QRCode(version=1, box_size=10, border=5); qr.add_data(qr_data); qr.make(fit=True); img = qr.make_image(fill='black', back_color='white'); qr_path = os.path.join(app.config['UPLOAD_FOLDER'], f"qr_{d['report_id']}.png"); img.save(qr_path); self.image(qr_path, w=80, h=80, x=self.get_x() + 110); self.multi_cell(100, 8, "本報告的所有內容（包含所有檔案的元數據）已被序列化並生成下方的主要驗證雜湊值。您可以使用此雜湊值或掃描右側的 QR Code 來核對報告的完整性與真實性。"); self.ln(10); self.set_font('Courier', 'B', 10); self.multi_cell(0, 5, f"報告主驗證雜湊 (SHA256):\n{d['report_main_hash']}")

# --- Flask 路由 ---
@app.route('/')
def index():
    session.clear(); return render_template('index.html')

@app.route('/static/<path:filename>')
def static_download(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- 修改後的 /upload 路由，增加逐頁雜湊 ---
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return jsonify({"error": "請求中沒有檔案部分"}), 400
    file = request.files['file']; applicant_name = request.form.get('applicant_name', 'N/A')
    if file.filename == '': return jsonify({"error": "未選擇檔案"}), 400
    if not session.get('applicant_name') and applicant_name: session['applicant_name'] = applicant_name

    try:
        file_ext = os.path.splitext(file.filename)[1]; file_uuid = str(uuid.uuid4())
        stored_filename = f"{file_uuid}{file_ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], stored_filename)
        file.save(filepath)

        file_hash = sha256_file(filepath)
        preview_image_urls = []
        pages_data = []

        if file_ext.lower() == '.pdf':
            doc = fitz.open(filepath)
            for page_num in range(len(doc)):
                page = doc.load_page(page_num); pix = page.get_pixmap(dpi=150)
                preview_filename = f"{file_uuid}_page_{page_num + 1}.jpg"
                preview_filepath = os.path.join(app.config['UPLOAD_FOLDER'], preview_filename)
                pix.save(preview_filepath)
                
                # --- 新增: 計算預覽圖的雜湊值 ---
                preview_hash = sha256_file(preview_filepath)
                
                preview_image_urls.append(url_for('static_download', filename=preview_filename))
                pages_data.append({
                    "page_num": page_num + 1,
                    "preview_filename": preview_filename,
                    "sha256_hash": preview_hash
                })
            doc.close()

        file_info = {
            "original_filename": file.filename,
            "stored_filename": stored_filename,
            "sha256_hash": file_hash,
            "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "pages": pages_data # <-- 儲存所有頁面的詳細資訊
        }

        uploaded_files = session.get('uploaded_files', []); uploaded_files.append(file_info)
        session['uploaded_files'] = uploaded_files
        
        return jsonify({
            "success": True, "message": "檔案上傳成功",
            "stored_filename": stored_filename,
            "is_pdf": file_ext.lower() == '.pdf',
            "preview_urls": preview_image_urls
        })
    except Exception as e:
        print(f"檔案上傳失敗: {e}"); return jsonify({"error": f"檔案上傳失敗: {str(e)}"}), 500

# --- (analyze_file 和 create_report 路由與前版相同) ---
@app.route('/analyze_file', methods=['POST'])
def analyze_file():
    # ... (此處程式碼與前一版相同) ...
    if not openai.api_key: return jsonify({"error": "伺服器未設定 OpenAI API 金鑰"}), 500
    data = request.get_json(); stored_filename = data.get('stored_filename')
    if not stored_filename: return jsonify({"error": "未提供檔案名稱"}), 400
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], stored_filename);
    if not os.path.exists(filepath): return jsonify({"error": "找不到指定的檔案"}), 404
    if not stored_filename.lower().endswith(('.txt', '.md', '.json', '.py', '.html', '.css', '.js')): return jsonify({"analysis": "AI 分析目前僅支援純文字格式的檔案。"}), 200
    try:
        with open(filepath, 'r', encoding='utf-8') as f: content = f.read(15000)
        client = openai.OpenAI(); response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "system", "content": "你是一位專業的文件分析師，你的任務是為使用者提供的內容做一個精簡、準確的摘要。請使用繁體中文回答。"},{"role": "user", "content": f"請為以下文件內容生成一段不超過150字的摘要：\n\n---\n{content}\n---"}], temperature=0.5, max_tokens=500); analysis_result = response.choices[0].message.content
        uploaded_files = session.get('uploaded_files', []);
        for file_info in uploaded_files:
            if file_info['stored_filename'] == stored_filename: file_info['analysis'] = analysis_result; break
        session['uploaded_files'] = uploaded_files
        return jsonify({"analysis": analysis_result})
    except Exception as e: print(f"AI 分析失敗: {e}"); return jsonify({"error": f"AI 分析失敗: {str(e)}"}), 500
@app.route('/create_report', methods=['POST'])
def create_report():
    # ... (此處程式碼與前一版相同) ...
    uploaded_files = session.get('uploaded_files', []); applicant_name = session.get('applicant_name', 'N/A')
    if not uploaded_files: return jsonify({"error": "沒有已上傳的檔案可供生成報告"}), 400
    try:
        report_id = str(uuid.uuid4()); report_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        proof_data = {"report_id": report_id, "applicant_name": applicant_name, "report_timestamp_utc": report_timestamp, "files": uploaded_files}
        proof_data_string = json.dumps(proof_data, sort_keys=True, ensure_ascii=False).encode('utf-8'); main_hash = hashlib.sha256(proof_data_string).hexdigest(); proof_data['report_main_hash'] = main_hash
        pdf = WesmartPDFReport(); pdf.create_cover(proof_data); pdf.create_file_details_page(proof_data); pdf.create_conclusion_page(proof_data)
        report_filename = f"WesmartAI_Report_{report_id}.pdf"; report_filepath = os.path.join(app.config['UPLOAD_FOLDER'], report_filename); pdf.output(report_filepath)
        session.pop('uploaded_files', None); session.pop('applicant_name', None)
        return jsonify({"success": True, "report_url": url_for('static_download', filename=report_filename)})
    except Exception as e: print(f"報告生成失敗: {e}"); return jsonify({"error": f"報告生成失敗: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)
