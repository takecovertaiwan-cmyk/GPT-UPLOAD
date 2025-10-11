# ====================================================================
# WesmartAI 可信智慧科技三方存證系統 (整合 GPT-4o-mini 分析版)
# 作者: Gemini & User
# 核心架構 (新版):
# 1. 新增 /analyze_file 接口，接收前端請求，讀取指定檔案內容。
# 2. 呼叫 OpenAI GPT-4o-mini 模型對檔案內容進行摘要。
# 3. 將 AI 生成的摘要存入 session，並整合進最終的 PDF 報告中。
# ====================================================================

import os
import uuid
import datetime
import hashlib
import json
import qrcode
import openai # <-- 新增
from flask import Flask, render_template, request, jsonify, url_for, session, send_from_directory
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image

# --- Flask App 初始化 ---
app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- 新增: 設定 OpenAI API 金鑰 ---
# 注意：您需要在您的部署環境中設定一個名為 OPENAI_API_KEY 的環境變數。
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    print("警告: 找不到 OPENAI_API_KEY 環境變數。AI 分析功能將無法使用。")

# 確保 static 資料夾存在
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

# --- PDF 報告生成類別 (已修改以顯示 AI 分析) ---

class WesmartPDFReport(FPDF):
    def header(self):
        self.set_font('helvetica', 'B', 12)
        self.image('LOGO.jpg', x=10, y=8, w=30)
        self.cell(0, 10, 'WesmartAI 可信智慧科技存證報告', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        self.set_font('helvetica', 'I', 8)
        self.cell(0, 10, f'頁碼 {self.page_no()}', align='C')

    def add_cjk_font(self):
        try:
            # 您需要自行下載並放置一個支援中文的 ttf 字體檔
            self.add_font('TaipeiSans', '', 'TaipeiSansTCBeta-Regular.ttf')
            self.set_font('TaipeiSans', '', 12)
        except RuntimeError:
            print("警告: 找不到中文字體 'TaipeiSansTCBeta-Regular.ttf'。")
            self.set_font('helvetica', '', 12)
            
    def create_cover(self, proof_data):
        self.add_page()
        self.add_cjk_font()
        self.set_font_size(24)
        self.cell(0, 20, 'WesmartAI 數位證據存證報告', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.ln(20)
        self.set_font_size(12)
        self.cell(0, 10, f"報告 ID: {proof_data['report_id']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 10, f"出證申請人: {proof_data['applicant_name']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 10, f"報告生成時間: {proof_data['report_timestamp_utc']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 10, f"存證檔案總數: {len(proof_data['files'])}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(10)
        self.multi_cell(0, 10, "本報告記錄了在上述時間由指定申請人提交用於存證的數位檔案。詳細的檔案資訊和驗證雜湊值記錄於後續頁面。")

    def create_file_details_page(self, proof_data):
        self.add_page()
        self.add_cjk_font()
        self.set_font_size(16)
        self.cell(0, 15, '存證檔案詳細紀錄', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
        self.set_font_size(12)
        
        for i, file_info in enumerate(proof_data['files']):
            self.set_fill_color(240, 240, 240)
            self.cell(0, 10, f"檔案 #{i+1}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True, border=1)
            
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_info['stored_filename'])
            is_image = False
            img_height = 0
            try:
                with Image.open(file_path) as img:
                    is_image = True
                    original_width, original_height = img.size
                    max_width = 60
                    ratio = max_width / original_width
                    img_height = original_height * ratio
                    self.image(file_path, x=self.get_x() + 120, y=self.get_y()+15, w=max_width)
            except Exception:
                is_image = False

            details_text = (
                f"原始檔名: {file_info['original_filename']}\n"
                f"上傳時間 (UTC): {file_info['timestamp_utc']}\n"
                f"SHA256 雜湊值: {file_info['sha256_hash']}"
            )
            self.multi_cell(110, 8, details_text, border=0)
            
            if is_image:
                 self.ln(img_height if img_height > 20 else 20)

            # --- 新增: 顯示 AI 分析結果 ---
            if file_info.get('analysis'):
                self.ln(5)
                self.set_font_size(11)
                self.set_text_color(70, 70, 70)
                self.multi_cell(0, 7, f"AI 摘要分析:\n{file_info['analysis']}", border='T')
                self.set_text_color(0, 0, 0)
                self.set_font_size(12) # 恢復字體大小

            self.ln(10)

    def create_conclusion_page(self, proof_data):
        self.add_page()
        self.add_cjk_font()
        self.set_font_size(16)
        self.cell(0, 15, '報告總結與驗證', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
        self.set_font_size(12)
        
        qr_data = json.dumps(proof_data, sort_keys=True, ensure_ascii=False)
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill='black', back_color='white')
        qr_path = os.path.join(app.config['UPLOAD_FOLDER'], f'qr_{proof_data["report_id"]}.png')
        img.save(qr_path)
        
        self.image(qr_path, w=80, h=80, x=self.get_x() + 110)
        
        self.multi_cell(100, 8, "本報告的所有內容（包含所有檔案的元數據）已被序列化並生成下方的主要驗證雜湊值。您可以使用此雜湊值或掃描右側的 QR Code 來核對報告的完整性與真實性。")
        self.ln(10)
        
        self.set_font('Courier', 'B', 10)
        self.multi_cell(0, 5, f"報告主驗證雜湊 (SHA256):\n{proof_data['report_main_hash']}")

# --- Flask 路由 ---

@app.route('/')
def index():
    session['uploaded_files'] = []
    session['applicant_name'] = ""
    return render_template('index.html')

@app.route('/static/<path:filename>')
def static_download(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return jsonify({"error": "請求中沒有檔案部分"}), 400
    
    file = request.files['file']
    applicant_name = request.form.get('applicant_name', 'N/A')

    if file.filename == '': return jsonify({"error": "未選擇檔案"}), 400
        
    if not session.get('applicant_name') and applicant_name:
        session['applicant_name'] = applicant_name

    try:
        file_ext = os.path.splitext(file.filename)[1]
        stored_filename = f"{uuid.uuid4()}{file_ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], stored_filename)
        file.save(filepath)

        file_hash = sha256_file(filepath)
        
        file_info = {
            "original_filename": file.filename,
            "stored_filename": stored_filename,
            "sha256_hash": file_hash,
            "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

        uploaded_files = session.get('uploaded_files', [])
        uploaded_files.append(file_info)
        session['uploaded_files'] = uploaded_files
        
        return jsonify({
            "success": True, 
            "message": "檔案上傳成功",
            "stored_filename": stored_filename # 回傳儲存檔名給前端
        })

    except Exception as e:
        print(f"檔案上傳失敗: {e}")
        return jsonify({"error": f"檔案上傳失敗: {str(e)}"}), 500

# --- 新增: AI 分析路由 ---
@app.route('/analyze_file', methods=['POST'])
def analyze_file():
    if not openai.api_key:
        return jsonify({"error": "伺服器未設定 OpenAI API 金鑰"}), 500

    data = request.get_json()
    stored_filename = data.get('stored_filename')
    if not stored_filename:
        return jsonify({"error": "未提供檔案名稱"}), 400

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], stored_filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "找不到指定的檔案"}), 404
        
    if not stored_filename.lower().endswith(('.txt', '.md', '.json', '.py', '.html', '.css', '.js')):
        return jsonify({"analysis": "AI 分析目前僅支援純文字格式的檔案。"}), 200

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read(15000) # 限制讀取長度

        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "你是一位專業的文件分析師，你的任務是為使用者提供的內容做一個精簡、準確的摘要。請使用繁體中文回答。"},
                {"role": "user", "content": f"請為以下文件內容生成一段不超過150字的摘要：\n\n---\n{content}\n---"}
            ],
            temperature=0.5,
            max_tokens=500
        )
        analysis_result = response.choices[0].message.content

        uploaded_files = session.get('uploaded_files', [])
        for file_info in uploaded_files:
            if file_info['stored_filename'] == stored_filename:
                file_info['analysis'] = analysis_result
                break
        session['uploaded_files'] = uploaded_files

        return jsonify({"analysis": analysis_result})

    except Exception as e:
        print(f"AI 分析失敗: {e}")
        return jsonify({"error": f"AI 分析失敗: {str(e)}"}), 500

@app.route('/create_report', methods=['POST'])
def create_report():
    uploaded_files = session.get('uploaded_files', [])
    applicant_name = session.get('applicant_name', 'N/A')

    if not uploaded_files:
        return jsonify({"error": "沒有已上傳的檔案可供生成報告"}), 400
    
    try:
        report_id = str(uuid.uuid4())
        report_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        proof_data = {
            "report_id": report_id,
            "applicant_name": applicant_name,
            "report_timestamp_utc": report_timestamp,
            "files": uploaded_files
        }
        
        proof_data_string = json.dumps(proof_data, sort_keys=True, ensure_ascii=False).encode('utf-8')
        main_hash = hashlib.sha256(proof_data_string).hexdigest()
        proof_data['report_main_hash'] = main_hash
        
        pdf = WesmartPDFReport()
        pdf.create_cover(proof_data)
        pdf.create_file_details_page(proof_data)
        pdf.create_conclusion_page(proof_data)
        
        report_filename = f"WesmartAI_Report_{report_id}.pdf"
        report_filepath = os.path.join(app.config['UPLOAD_FOLDER'], report_filename)
        pdf.output(report_filepath)

        session.pop('uploaded_files', None)
        session.pop('applicant_name', None)

        return jsonify({"success": True, "report_url": url_for('static_download', filename=report_filename)})
    except Exception as e:
        print(f"報告生成失敗: {e}")
        return jsonify({"error": f"報告生成失敗: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)
