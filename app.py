# ====================================================================
# WesmartAI 存證系統 (v7 - 全面文字圖像化)
# 核心架構:
# 1. 修正字體檔案的絕對路徑問題，確保 Pillow 能在任何環境下載入字體。
# 2. 全面棄用 fpdf 的文字寫入功能。所有動態、靜態文字（標題、內文、雜湊值等）
#    均先通過升級後的 render_text_to_image 函式轉換為 PNG 圖片。
# 3. PDF 報告生成過程只負責佈局和插入圖片，徹底解決字體依賴問題。
# 4. render_text_to_image 函式已升級，支援多行文字和自動換行。
# ====================================================================

import os
import uuid
import datetime
import hashlib
import json
import qrcode
import openai
import fitz
import textwrap
from flask import Flask, render_template, request, jsonify, url_for, session, send_from_directory
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image, ImageDraw, ImageFont

# --- Flask App 初始化 ---
app = Flask(__name__)
app.secret_key = os.urandom(24)

openai.api_key = os.getenv("OPENAI_API_KEY")

static_folder = 'static'
if not os.path.exists(static_folder):
    os.makedirs(static_folder)
app.config['UPLOAD_FOLDER'] = static_folder

# --- 核心修正: 定義絕對路徑 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, 'TaipeiSansTCBeta-Regular.ttf')

# --- 輔助函式 ---
def sha256_file(filepath):
    sha256_hash = hashlib.sha256();
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""): sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

# --- 升級版: 文字圖像化函式 (支援多行與自動換行) ---
def render_text_to_image(text, font_path, font_size, image_path, max_width_pixels=None):
    try:
        font = ImageFont.truetype(font_path, font_size)
    except IOError:
        print(f"警告: 無法載入字體 {font_path}。將使用預設字體。")
        font = ImageFont.load_default()
    
    # 自動換行
    if max_width_pixels:
        # 估算每個字元寬度來換行
        avg_char_width = font.getbbox("寬")[2] / 1
        chars_per_line = int(max_width_pixels / avg_char_width)
        lines = textwrap.wrap(text, width=chars_per_line)
        wrapped_text = "\n".join(lines)
    else:
        wrapped_text = text

    # 根據換行後的文字內容計算圖片大小
    draw = ImageDraw.Draw(Image.new("RGBA", (1,1))) # 臨時畫布
    text_bbox = draw.multiline_textbbox((0,0), wrapped_text, font=font)
    image_width = text_bbox[2] + 20
    image_height = text_bbox[3] + 10
    
    image = Image.new("RGBA", (image_width, image_height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    
    draw.multiline_text((10, 5), wrapped_text, font=font, fill=(0, 0, 0, 255))
    image.save(image_path, "PNG")
    return image_path

# --- 全新改造的 PDF 報告生成類別 ---
class WesmartPDFReport(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.font_path = FONT_PATH
        self.temp_images = [] # 用於追蹤臨時生成的文字圖片

    def render_and_place(self, text, x, y, font_size, max_width_mm=None):
        """一個整合方法，渲染文字並放置到 PDF 中"""
        # A4 寬度約 210mm，邊距 10mm*2，可用寬度 190mm
        max_width_pixels = (max_width_mm * 72 / 25.4) if max_width_mm else None # mm to pixels
        
        image_name = f"text_{uuid.uuid4()}.png"
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_name)
        
        render_text_to_image(text, self.font_path, font_size, image_path, max_width_pixels)
        
        # 將圖片寬度轉換回 mm
        with Image.open(image_path) as img:
            img_w, img_h = img.size
            img_w_mm = img_w * 25.4 / 72

        self.image(image_path, x=x, y=y, w=img_w_mm)
        self.temp_images.append(image_path)
        return self.get_y() + (img_h * 25.4 / 72) + 2 # 回傳新的 Y 座標

    def header(self):
        self.image('LOGO.jpg', x=10, y=8, w=30)
        self.render_and_place("WesmartAI 可信智慧科技存證報告", x=50, y=12, font_size=14)
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        # 頁碼仍使用 fpdf 預設字體
        self.set_font('helvetica', 'I', 8)
        self.cell(0, 10, f'頁碼 {self.page_no()}', align='C')

    def cleanup(self):
        """刪除所有臨時生成的文字圖片"""
        for path in self.temp_images:
            if os.path.exists(path):
                os.remove(path)
            
    def create_cover(self, d):
        self.add_page()
        y_pos = self.render_and_place("WesmartAI 數位證據存證報告", x=30, y=30, font_size=24)
        y_pos += 10
        y_pos = self.render_and_place(f"報告 ID: {d['report_id']}", x=10, y=y_pos, font_size=12)
        y_pos = self.render_and_place(f"出證申請人: {d['applicant_name']}", x=10, y=y_pos, font_size=12)
        y_pos = self.render_and_place(f"報告生成時間: {d['report_timestamp_utc']}", x=10, y=y_pos, font_size=12)
        y_pos = self.render_and_place(f"存證檔案總數: {len(d['files'])}", x=10, y=y_pos, font_size=12)
        y_pos += 5
        self.render_and_place("本報告記錄了在上述時間由指定申請人提交用於存證的數位檔案。詳細的檔案資訊和驗證雜湊值記錄於後續頁面。", x=10, y=y_pos, font_size=12, max_width_mm=190)

    def create_file_details_page(self, proof_data):
        self.add_page()
        y_pos = self.render_and_place("存證檔案詳細紀錄", x=10, y=25, font_size=16)
        
        for i, file_info in enumerate(proof_data['files']):
            self.set_fill_color(220, 220, 220)
            self.rect(x=10, y=y_pos, w=190, h=10, style='F')
            y_pos = self.render_and_place(f"主要檔案 #{i+1}: {file_info['original_filename']}", x=12, y=y_pos+1, font_size=12)
            y_pos = self.render_and_place(f"SHA256: {file_info['sha256_hash']}", x=10, y=y_pos, font_size=9)
            
            if file_info.get('analysis'):
                y_pos += 2
                y_pos = self.render_and_place(f"AI 摘要分析: {file_info['analysis']}", x=10, y=y_pos, font_size=11, max_width_mm=190)

            if 'pages' in file_info and file_info['pages']:
                y_pos += 5
                self.set_fill_color(240, 240, 240)
                self.rect(x=10, y=y_pos, w=190, h=8, style='F')
                y_pos = self.render_and_place('衍生預覽圖詳細資料:', x=12, y=y_pos, font_size=11)
                
                for page_data in file_info['pages']:
                    if y_pos > 220: self.add_page(); y_pos = 25
                    page_image_path = os.path.join(app.config['UPLOAD_FOLDER'], page_data['preview_filename'])
                    if os.path.exists(page_image_path): self.image(page_image_path, x=15, y=y_pos, w=70)
                    
                    text_x = 90
                    page_y = self.render_and_place(f"頁碼: {page_data['page_num']}", x=text_x, y=y_pos+5, font_size=11)
                    page_y = self.render_and_place(f"檔名: {page_data['preview_filename']}", x=text_x, y=page_y, font_size=11)
                    self.render_and_place(f"SHA256: {page_data['sha256_hash']}", x=text_x, y=page_y, font_size=8)
                    y_pos += 65
            y_pos += 10

    def create_conclusion_page(self, d):
        self.add_page()
        y_pos = self.render_and_place("報告總結與驗證", x=10, y=25, font_size=16)
        y_pos += 5
        
        qr_data = json.dumps(d, sort_keys=True, ensure_ascii=False)
        qr = qrcode.QRCode(version=1, box_size=10, border=5); qr.add_data(qr_data); qr.make(fit=True)
        img = qr.make_image(fill='black', back_color='white')
        qr_path = os.path.join(app.config['UPLOAD_FOLDER'], f"qr_{d['report_id']}.png"); img.save(qr_path)
        self.image(qr_path, w=80, h=80, x=115, y=y_pos)
        
        y_pos = self.render_and_place("本報告的所有內容（包含所有檔案的元數據）已被序列化並生成下方的主要驗證雜湊值。您可以使用此雜湊值或掃描右側的 QR Code 來核對報告的完整性與真實性。", x=10, y=y_pos, font_size=12, max_width_mm=100)
        y_pos += 10
        self.render_and_place(f"報告主驗證雜湊 (SHA256): {d['report_main_hash']}", x=10, y=y_pos, font_size=10, max_width_mm=190)

# --- (Flask 路由部分與 v6 版本完全相同) ---
@app.route('/')
def index(): session.clear(); return render_template('index.html')
@app.route('/static/<path:filename>')
def static_download(filename): return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return jsonify({"error": "請求中沒有檔案部分"}), 400
    file = request.files['file']; applicant_name = request.form.get('applicant_name', 'N/A')
    if file.filename == '': return jsonify({"error": "未選擇檔案"}), 400
    if not session.get('applicant_name') and applicant_name: session['applicant_name'] = applicant_name
    try:
        file_ext = os.path.splitext(file.filename)[1]; file_uuid = str(uuid.uuid4())
        stored_filename = f"{file_uuid}{file_ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], stored_filename); file.save(filepath)
        file_hash = sha256_file(filepath); preview_image_urls = []; pages_data = []
        if file_ext.lower() == '.pdf':
            doc = fitz.open(filepath)
            for page_num in range(len(doc)):
                page = doc.load_page(page_num); pix = page.get_pixmap(dpi=150)
                preview_filename = f"{file_uuid}_page_{page_num + 1}.jpg"
                preview_filepath = os.path.join(app.config['UPLOAD_FOLDER'], preview_filename); pix.save(preview_filepath)
                preview_hash = sha256_file(preview_filepath)
                preview_image_urls.append(url_for('static_download', filename=preview_filename))
                pages_data.append({"page_num": page_num + 1, "preview_filename": preview_filename, "sha256_hash": preview_hash})
            doc.close()
        file_info = {"original_filename": file.filename, "stored_filename": stored_filename, "sha256_hash": file_hash, "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "pages": pages_data}
        uploaded_files = session.get('uploaded_files', []); uploaded_files.append(file_info); session['uploaded_files'] = uploaded_files
        return jsonify({"success": True, "message": "檔案上傳成功", "stored_filename": stored_filename, "is_pdf": file_ext.lower() == '.pdf', "preview_urls": preview_image_urls})
    except Exception as e:
        print(f"檔案上傳失敗: {e}"); return jsonify({"error": f"檔案上傳失敗: {str(e)}"}), 500
@app.route('/analyze_file', methods=['POST'])
def analyze_file():
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
        session['uploaded_files'] = uploaded_files; return jsonify({"analysis": analysis_result})
    except Exception as e: print(f"AI 分析失敗: {e}"); return jsonify({"error": f"AI 分析失敗: {str(e)}"}), 500
@app.route('/create_report', methods=['POST'])
def create_report():
    uploaded_files = session.get('uploaded_files', []); applicant_name = session.get('applicant_name', 'N/A')
    if not uploaded_files: return jsonify({"error": "沒有已上傳的檔案可供生成報告"}), 400
    pdf = None
    try:
        report_id = str(uuid.uuid4()); report_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        proof_data = {"report_id": report_id, "applicant_name": applicant_name, "report_timestamp_utc": report_timestamp, "files": uploaded_files}
        proof_data_string = json.dumps(proof_data, sort_keys=True, ensure_ascii=False).encode('utf-8'); main_hash = hashlib.sha256(proof_data_string).hexdigest(); proof_data['report_main_hash'] = main_hash
        
        pdf = WesmartPDFReport()
        pdf.create_cover(proof_data)
        pdf.create_file_details_page(proof_data)
        pdf.create_conclusion_page(proof_data)
        
        report_filename = f"WesmartAI_Report_{report_id}.pdf"; report_filepath = os.path.join(app.config['UPLOAD_FOLDER'], report_filename); pdf.output(report_filepath)
        session.clear()
        return jsonify({"success": True, "report_url": url_for('static_download', filename=report_filename)})
    except Exception as e:
        print(f"報告生成失敗: {e}"); return jsonify({"error": f"報告生成失敗: {str(e)}"}), 500
    finally:
        if pdf: pdf.cleanup() # 確保不論成功或失敗都刪除臨時圖片

if __name__ == '__main__':
    app.run(debug=True, port=5001)
