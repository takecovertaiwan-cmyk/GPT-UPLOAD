# ====================================================================
# WesmartAI 存證系統 (v5 - 修正字體載入順序)
# 核心升級:
# 1. 修改 WesmartPDFReport 類別，在 __init__ 初始化時就載入中文字體。
# 2. 確保 header 和所有其他方法在需要時都能正確使用已載入的中文字體。
# 3. 解決因字體未及時載入導致的 PDF 生成失敗問題。
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
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

# --- PDF 報告生成類別 (已修正) ---
class WesmartPDFReport(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # --- 修正: 在初始化時就載入中文字體 ---
        try:
            self.add_font('TaipeiSans', '', 'TaipeiSansTCBeta-Regular.ttf')
            self.cjk_font_loaded = True
        except RuntimeError:
            print("警告: 找不到中文字體 'TaipeiSansTCBeta-Regular.ttf'。報告中的中文可能無法正確顯示。")
            self.cjk_font_loaded = False

    def set_cjk_font(self, style='', size=12):
        if self.cjk_font_loaded:
            self.set_font('TaipeiSans', style, size)
        else:
            # 如果中文字體載入失敗，則退回使用預設字體
            self.set_font('helvetica', style, size)

    def header(self):
        # --- 修正: 在頁首中使用設定好的中文字體 ---
        self.set_cjk_font('B', 12)
        self.image('LOGO.jpg', x=10, y=8, w=30)
        self.cell(0, 10, 'WesmartAI 可信智慧科技存證報告', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        self.set_font('helvetica', 'I', 8)
        self.cell(0, 10, f'頁碼 {self.page_no()}', align='C')
            
    def create_cover(self, d):
        self.add_page()
        self.set_cjk_font(size=24)
        self.cell(0, 20, 'WesmartAI 數位證據存證報告', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.ln(20)
        self.set_cjk_font(size=12)
        self.cell(0, 10, f"報告 ID: {d['report_id']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 10, f"出證申請人: {d['applicant_name']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 10, f"報告生成時間: {d['report_timestamp_utc']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 10, f"存證檔案總數: {len(d['files'])}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(10)
        self.multi_cell(0, 10, "本報告記錄了在上述時間由指定申請人提交用於存證的數位檔案。詳細的檔案資訊和驗證雜湊值記錄於後續頁面。")

    def create_file_details_page(self, proof_data):
        self.add_page()
        self.set_cjk_font(size=16)
        self.cell(0, 15, '存證檔案詳細紀錄', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
        
        for i, file_info in enumerate(proof_data['files']):
            self.set_cjk_font(size=12)
            self.set_fill_color(220, 220, 220)
            self.cell(0, 10, f"主要檔案 #{i+1}: {file_info['original_filename']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True, border=1)
            
            self.set_font('Courier', '', 9)
            self.multi_cell(0, 5, f"SHA256: {file_info['sha256_hash']}", border='LR', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.cell(0, 2, '', border='LBR', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
            if file_info.get('analysis'):
                self.set_cjk_font(size=11); self.set_text_color(70, 70, 70); self.ln(2)
                self.multi_cell(0, 7, f"AI 摘要分析:\n{file_info['analysis']}", border=0)
                self.set_text_color(0, 0, 0); self.ln(5)

            if 'pages' in file_info and file_info['pages']:
                self.set_cjk_font(size=11); self.set_fill_color(240, 240, 240)
                self.cell(0, 8, '衍生預覽圖詳細資料:', new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
                
                for page_data in file_info['pages']:
                    if self.get_y() > 220: self.add_page()
                    page_image_path = os.path.join(app.config['UPLOAD_FOLDER'], page_data['preview_filename'])
                    if os.path.exists(page_image_path):
                        self.image(page_image_path, x=self.get_x()+5, y=self.get_y()+5, w=70)
                    self.set_xy(self.get_x() + 80, self.get_y()); self.set_cjk_font(size=11)
                    self.multi_cell(110, 6, f"頁碼: {page_data['page_num']}\n檔名: {page_data['preview_filename']}", border=0)
                    self.set_x(self.get_x() + 80); self.set_font('Courier', '', 8)
                    self.multi_cell(110, 4, f"SHA256: {page_data['sha256_hash']}", border=0)
                    self.ln(60)

            self.ln(10)

    def create_conclusion_page(self, d):
        self.add_page(); self.set_cjk_font(size=16)
        self.cell(0, 15, '報告總結與驗證', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
        self.set_cjk_font(size=12)
        qr_data = json.dumps(d, sort_keys=True, ensure_ascii=False)
        qr = qrcode.QRCode(version=1, box_size=10, border=5); qr.add_data(qr_data); qr.make(fit=True)
        img = qr.make_image(fill='black', back_color='white')
        qr_path = os.path.join(app.config['UPLOAD_FOLDER'], f"qr_{d['report_id']}.png"); img.save(qr_path)
        self.image(qr_path, w=80, h=80, x=self.get_x() + 110)
        self.multi_cell(100, 8, "本報告的所有內容（包含所有檔案的元數據）已被序列化並生成下方的主要驗證雜湊值。您可以使用此雜湊值或掃描右側的 QR Code 來核對報告的完整性與真實性。")
        self.ln(10); self.set_font('Courier', 'B', 10)
        self.multi_cell(0, 5, f"報告主驗證雜湊 (SHA256):\n{d['report_main_hash']}")

# --- (Flask 路由部分與前一版完全相同，此處為節省篇幅故省略) ---
@app.route('/')
def index():
    session.clear(); return render_template('index.html')
@app.route('/static/<path:filename>')
def static_download(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
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

```eof
```html:index.html (優化後的 JavaScript):index.html
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WesmartAI 可信智慧科技三方存證系統</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 0; padding: 2em; background-color: #f4f6f8; color: #333; }
        .container { max-width: 900px; margin: auto; background: #fff; padding: 2em; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        h1, h2 { color: #1a237e; text-align: center; }
        .form-grid { display: grid; grid-template-columns: 1fr; gap: 1.5em; margin-bottom: 1.5em; }
        .form-group { display: flex; flex-direction: column; }
        label { font-weight: 600; margin-bottom: 0.5em; color: #555; }
        input, button { font-size: 1em; padding: 0.8em; border-radius: 6px; border: 1px solid #ccc; }
        .upload-btn-wrapper { position: relative; overflow: hidden; display: inline-block; width: 100%; }
        .btn { display: block; width: 100%; box-sizing: border-box; text-align: center; background-color: #3f51b5; color: white; border: none; cursor: pointer; font-weight: bold; transition: background-color 0.2s ease; }
        .upload-btn-wrapper input[type=file] { font-size: 100px; position: absolute; left: 0; top: 0; opacity: 0; cursor: pointer; }
        button:disabled { background-color: #9fa8da; cursor: not-allowed; }
        #report-btn { background-color: #d32f2f; }
        #results-grid { display: grid; grid-template-columns: 1fr; gap: 1.5em; margin-top: 1.5em; }
        .result-card { border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; text-align: center; box-shadow: 0 2px 6px rgba(0,0,0,0.05); }
        .pdf-page-img { max-width: 100%; height: auto; display: block; border-bottom: 1px solid #eee; }
        .spinner { margin: 2em auto; width: 40px; height: 40px; border: 4px solid #f3f3f3; border-top: 4px solid #3f51b5; border-radius: 50%; animation: spin 1s linear infinite; display: none; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        #status { text-align: center; margin-top: 1em; font-weight: 500; min-height: 1.2em; }
        hr { border: none; height: 1px; background-color: #e0e0e0; margin: 2em 0; }
        .analyze-btn { background-color: #1976d2; color: white; border: none; padding: 6px 10px; font-size: 0.8em; border-radius: 4px; cursor: pointer; margin-top: 8px; }
        .analysis-result { font-size: 0.9em; padding: 10px; margin: 10px; background-color: #e3f2fd; border-left: 4px solid #1976d2; text-align: left; white-space: pre-wrap; word-wrap: break-word; }
    </style>
</head>
<body>
    <div class="container">
        <h1>WesmartAI<br>可信智慧科技三方存證系統</h1>
        <h2>1. 上傳檔案及預覽</h2>
        <div class="form-grid">
            <div class="form-group"><label for="applicant_name">出證申請人名稱</label><input type="text" id="applicant_name" placeholder="請在此處輸入您的姓名或公司名稱"></div>
            <div class="form-group"><div class="upload-btn-wrapper"><button class="btn">上傳檔案</button><input type="file" id="file-upload" /></div></div>
        </div>
        <div id="spinner" class="spinner"></div><div id="status"></div><div id="results-grid"></div><hr>
        <h2>2. 生成 PDF 報告</h2>
        <div class="form-group full-width"><button id="report-btn" disabled>下載 PDF 摘要報告</button></div>
    </div>

    <script>
        const fileUpload = document.getElementById('file-upload');
        const reportBtn = document.getElementById('report-btn');
        const spinner = document.getElementById('spinner');
        const statusEl = document.getElementById('status');
        const resultsGrid = document.getElementById('results-grid');

        fileUpload.addEventListener('change', async (event) => {
            const applicantName = document.getElementById('applicant_name').value;
            if (!applicantName) {
                alert('請先填寫 申請人名稱！');
                event.target.value = ''; return;
            }
            const file = event.target.files[0];
            if (!file) return;

            const formData = new FormData();
            formData.append('file', file);
            formData.append('applicant_name', applicantName);

            spinner.style.display = 'block';
            statusEl.textContent = `正在上傳並處理檔案 "${file.name}"...`;
            
            try {
                const response = await fetch('/upload', { method: 'POST', body: formData });
                const contentType = response.headers.get("content-type");
                if (!contentType || !contentType.includes("application/json")) {
                    throw new Error("伺服器回應格式錯誤，請檢查後端日誌。");
                }
                const result = await response.json();
                console.log("從後端收到的回應:", result); // 新增日誌以供偵錯

                if (!response.ok) throw new Error(result.error || '檔案上傳失敗');
                
                statusEl.textContent = `✅ 檔案 "${file.name}" 已成功處理。`;
                reportBtn.disabled = false;

                // --- 使用更穩健的 DOM 操作來建立預覽卡片 ---
                const card = document.createElement('div');
                card.className = 'result-card';
                card.id = `card-${result.stored_filename}`;

                const cardFooter = document.createElement('div');
                cardFooter.style.padding = '1em';
                cardFooter.style.background = '#fafafa';
                cardFooter.style.borderBottom = '1px solid #eee';

                const fileNameStrong = document.createElement('strong');
                fileNameStrong.textContent = file.name;
                cardFooter.appendChild(fileNameStrong);

                if (file.name.match(/\.(txt|md|json|py|html|css|js)$/i)) {
                    cardFooter.appendChild(document.createElement('br'));
                    const analyzeBtn = document.createElement('button');
                    analyzeBtn.className = 'analyze-btn';
                    analyzeBtn.dataset.filename = result.stored_filename;
                    analyzeBtn.textContent = '使用 AI 分析';
                    cardFooter.appendChild(analyzeBtn);
                }
                card.appendChild(cardFooter);

                if (result.is_pdf && result.preview_urls && result.preview_urls.length > 0) {
                    result.preview_urls.forEach(url => {
                        const img = document.createElement('img');
                        img.src = url;
                        img.className = 'pdf-page-img';
                        card.appendChild(img);
                    });
                } else if (file.type.startsWith('image/')) {
                    const img = document.createElement('img');
                    img.src = URL.createObjectURL(file);
                    card.appendChild(img);
                } else {
                    const p = document.createElement('p');
                    p.style.padding = '2em 1em';
                    p.innerHTML = `📄<br>${file.name}`;
                    card.appendChild(p);
                }
                resultsGrid.appendChild(card);

            } catch (error) {
                statusEl.textContent = `❌ 錯誤: ${error.message}`;
            } finally {
                spinner.style.display = 'none';
                event.target.value = ''; 
            }
        });
        
        resultsGrid.addEventListener('click', async (event) => {
            if (event.target.classList.contains('analyze-btn')) {
                const button = event.target; const storedFilename = button.dataset.filename; const card = document.getElementById(`card-${storedFilename}`);
                button.disabled = true; button.textContent = '分析中...';
                try {
                    const response = await fetch('/analyze_file', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ stored_filename: storedFilename }) });
                    const result = await response.json();
                    if (!response.ok) throw new Error(result.error || '分析失敗');
                    
                    let analysisDiv = card.querySelector('.analysis-result');
                    if (!analysisDiv) {
                        analysisDiv = document.createElement('div');
                        analysisDiv.className = 'analysis-result';
                        card.appendChild(analysisDiv);
                    }
                    analysisDiv.textContent = result.analysis;
                    button.textContent = '重新分析';
                } catch (error) {
                    alert(`分析時發生錯誤: ${error.message}`);
                    button.textContent = '使用 AI 分析';
                } finally { button.disabled = false; }
            }
        });

        reportBtn.addEventListener('click', async () => {
            spinner.style.display = 'block'; statusEl.textContent = '正在生成 PDF 報告...'; reportBtn.disabled = true;
            try {
                const response = await fetch('/create_report', { method: 'POST' });
                const result = await response.json();
                if (!response.ok) throw new Error(result.error || '報告生成失敗');
                
                statusEl.textContent = 'PDF 報告生成完畢，即將下載。';
                const a = document.createElement('a'); a.href = result.report_url; a.download = result.report_url.split('/').pop();
                document.body.appendChild(a); a.click(); document.body.removeChild(a);
            } catch (error) {
                statusEl.textContent = `❌ 錯誤: ${error.message}`;
            } finally {
                spinner.style.display = 'none';
                reportBtn.disabled = false;
            }
        });
    </script>
</body>
</html>
