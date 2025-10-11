# ====================================================================
# WesmartAI 可信智慧科技三方存證系統 (整合 GPT-4 mini 公證)
# 作者: Gemini & User
# 核心架構 (新版):
# 1. 使用者上傳圖像後，系統在本地計算其雜湊值與時間戳。
# 2. 系統立即呼叫 GPT-4 mini API，將雜湊值與時間戳傳送給 AI。
# 3. GPT-4 mini 作為「數位公證人」回覆確認訊息。
# 4. 此 AI 回覆將作為額外證據，與圖像原始資訊一同記錄在 PDF 報告中。
# ====================================================================

import json, hashlib, uuid, datetime, os, io, base64
from flask import Flask, render_template, request, jsonify, send_from_directory, url_for
from PIL import Image
from fpdf import FPDF
from fpdf.enums import XPos, YPos
import qrcode
from werkzeug.utils import secure_filename
import openai # <--- 新增 OpenAI 套件

# --- 環境變數與 API Key 設定 ---
# 請確保您已在環境中設定 OPENAI_API_KEY
# 也可以直接在此處賦值: openai.api_key = "sk-..."
try:
    openai.api_key = os.getenv("OPENAI_API_KEY")
    if not openai.api_key:
        print("警告：OPENAI_API_KEY 環境變數未設定。AI 公證功能將無法使用。")
except Exception as e:
    print(f"讀取 OpenAI API Key 時發生錯誤: {e}")


# --- Flask App 初始化 ---
app = Flask(__name__)
static_folder = 'static'
if not os.path.exists(static_folder): os.makedirs(static_folder)
app.config['UPLOAD_FOLDER'] = static_folder
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# --- Helper Functions ---
def sha256_bytes(b):
    """計算 bytes 的 SHA-256 雜湊值"""
    return hashlib.sha256(b).hexdigest()

def allowed_file(filename):
    """檢查檔案副檔名是否在允許範圍內"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# --- 新增：呼叫 GPT-4 mini 進行公證 ---
def get_gpt_notarization(image_hash, timestamp_utc):
    """
    呼叫 GPT-4 mini API，請求對給定的雜湊值和時間戳進行公證。
    """
    if not openai.api_key:
        return "錯誤：OpenAI API Key 未設定，無法進行 AI 公證。"
        
    prompt_content = f"""
    作為一名專業的數位內容公證人，請為以下數位資產的存證事件提供一份標準的公證確認聲明。
    請在您的回覆中明確包含以下兩項核心資訊：
    1.  **圖像雜湊值 (SHA-256)**: `{image_hash}`
    2.  **存證時間戳 (UTC)**: `{timestamp_utc}`
    請以簡潔、正式的格式回覆，確認您已記錄此事件。
    """
    try:
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o-mini", # 使用最新的 gpt-4o-mini 模型
            messages=[
                {"role": "system", "content": "你是一名數位內容公證人，職責是為收到的資料提供正式的確認聲明。"},
                {"role": "user", "content": prompt_content}
            ],
            temperature=0.2, # 降低隨機性，使回覆更穩定
            max_tokens=200
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"呼叫 GPT-4 mini API 失敗: {e}")
        return f"AI 公證失敗：無法連接至 OpenAI 服務。錯誤: {str(e)}"

# --- PDF 報告生成類別 (已修改以包含 AI 公證資訊) ---
class WesmartPDFReport(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not os.path.exists("NotoSansTC.otf"):
            raise FileNotFoundError("錯誤：中文字型檔 'NotoSansTC.otf' 不存在。")
        self.add_font("NotoSansTC", "", "NotoSansTC.otf")
        self.set_auto_page_break(auto=True, margin=25)
        self.alias_nb_pages()
        self.logo_path = "LOGO.jpg" if os.path.exists("LOGO.jpg") else None

    # header, footer, chapter_title, chapter_body, create_cover (與前版相同) ...
    def header(self):
        if self.logo_path:
            with self.local_context(fill_opacity=0.08, stroke_opacity=0.08):
                img_w, center_x, center_y = 120, (self.w - 120) / 2, (self.h - 120) / 2
                self.image(self.logo_path, x=center_x, y=center_y, w=img_w)
        if self.page_no() > 1:
            self.set_font("NotoSansTC", "", 9)
            self.set_text_color(128)
            self.cell(0, 10, "WesmartAI 可信智慧科技三方存證報告", new_x=XPos.LMARGIN, new_y=YPos.TOP, align='L')
            self.cell(0, 10, "WesmartAI Inc.", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')

    def footer(self):
        self.set_y(-15)
        self.set_font("NotoSansTC", "", 8)
        self.set_text_color(128)
        self.cell(0, 10, f'第 {self.page_no()}/{{nb}} 頁', align='C')

    def chapter_title(self, title):
        self.set_font("NotoSansTC", "", 16)
        self.set_text_color(0)
        self.cell(0, 12, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
        self.ln(6)

    def chapter_body(self, content):
        self.set_font("NotoSansTC", "", 10)
        self.set_text_color(50)
        self.multi_cell(0, 7, content, align='L')
        self.ln()
    
    def create_cover(self, meta):
        self.add_page()
        if self.logo_path: self.image(self.logo_path, x=(self.w - 60) / 2, y=25, w=60)
        self.set_y(100)
        self.set_font("NotoSansTC", "", 28)
        self.cell(0, 20, "WesmartAI 存證報告", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.ln(20)
        self.set_font("NotoSansTC", "", 12)
        data = [("出證申請人:", meta.get('applicant', 'N/A')),("申請事項:", "WesmartAI 圖像上傳存證報告"),
                ("申請出證時間:", meta.get('issued_at', 'N/A')),("出證編號 (報告ID):", meta.get('report_id', 'N/A')),
                ("出證單位:", meta.get('issuer', 'N/A'))]
        for row in data:
            self.cell(20)
            self.cell(45, 10, row[0], align='L')
            self.multi_cell(0, 10, row[1], new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')


    def create_evidence_pages(self, proof_data):
        self.chapter_title("一、存證圖像詳情")
        # ... (此處與前版相同，顯示總覽資訊)
        experiment_meta = { "Trace Token": proof_data['event_proof']['trace_token'], "總共存證圖像數": len(proof_data['event_proof']['snapshots']) }
        for key, value in experiment_meta.items():
            self.set_font("NotoSansTC", "", 10)
            self.set_text_color(0)
            self.cell(40, 8, f"  {key}:", align='L')
            self.set_font("NotoSansTC", "", 9)
            self.set_text_color(80)
            self.multi_cell(0, 8, str(value), align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(10)

        for snapshot in proof_data['event_proof']['snapshots']:
            self.add_page()
            self.set_font("NotoSansTC", "", 12)
            self.set_text_color(0)
            self.cell(0, 10, f"圖像索引: {snapshot['version_index']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
            self.ln(4)
            
            # --- 顯示本地計算的資訊 ---
            details = [("時間戳記 (UTC)", snapshot['timestamp_utc']),("圖像雜湊 (SHA-256)", snapshot['snapshot_hash'])]
            for key, value in details:
                self.set_font("NotoSansTC", "", 10)
                self.set_text_color(0)
                self.cell(60, 7, f"  - {key}:", align='L')
                self.set_font("NotoSansTC", "", 9)
                self.set_text_color(80)
                self.multi_cell(0, 7, str(value), align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(5)

            # --- 新增：顯示 GPT-4 mini 的公證回覆 ---
            self.set_font("NotoSansTC", "", 10)
            self.set_text_color(0)
            self.cell(0, 7, "  - AI 公證記錄 (by GPT-4 mini):", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font("NotoSansTC", "", 9)
            self.set_text_color(80)
            with self.local_context(x=self.get_x() + 5): # 縮排
                 self.multi_cell(0, 6, snapshot.get('gpt_notarization', 'N/A'), border=1, padding=3)
            self.ln(10)

            # --- 顯示預覽圖 ---
            try:
                img_bytes = base64.b64decode(snapshot['content_base64'])
                with Image.open(io.BytesIO(img_bytes)) as img:
                    img_w, img_h = img.size
                    aspect = img_h / img_w
                    disp_w = 150
                    disp_h = disp_w * aspect
                    center_x = (self.w - disp_w) / 2
                    self.image(io.BytesIO(img_bytes), x=center_x, w=disp_w)
            except Exception as e:
                print(f"在PDF中顯示圖片失敗: {e}")
            self.ln(5)
    
    # create_conclusion_page (與前版相同) ...
    def create_conclusion_page(self, proof_data):
        self.add_page()
        self.chapter_title("二、報告驗證")
        self.chapter_body("本報告的真實性與完整性，取決於其對應的 `proof_event.json` 證據檔案。此 JSON 檔案的雜湊值（Final Event Hash）被記錄於下，可用於比對與驗證。")
        self.ln(10)
        self.set_font("NotoSansTC", "", 12)
        self.set_text_color(0)
        self.cell(0, 10, "最終事件雜湊值 (Final Event Hash):", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Courier", "B", 11)
        self.multi_cell(0, 8, proof_data['event_proof']['final_event_hash'], border=1, align='C', padding=5)
        
        qr_data = proof_data['verification']['verify_url']
        qr = qrcode.make(qr_data)
        qr_path = os.path.join(app.config['UPLOAD_FOLDER'], f"qr_{proof_data['report_id'][:10]}.png")
        qr.save(qr_path)
        
        self.ln(10)
        self.set_font("NotoSansTC", "", 10)
        self.cell(0, 10, "掃描 QR Code 前往驗證頁面", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.image(qr_path, w=50, x=(self.w - 50) / 2)


# --- 全域變數 ---
session_uploads = []
latest_proof_data = None

@app.route('/')
def index():
    global session_uploads, latest_proof_data
    session_uploads = []
    latest_proof_data = None
    return render_template('index.html')

# 步驟1: 上傳圖像檔案 (已修改)
@app.route('/upload', methods=['POST'])
def upload_image():
    if 'image' not in request.files: return jsonify({"error": "請求中未包含圖像檔案"}), 400
    file = request.files['image']
    if file.filename == '': return jsonify({"error": "未選擇任何檔案"}), 400
    
    if file and allowed_file(file.filename):
        try:
            # 儲存檔案
            original_filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4().hex}_{original_filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)

            # 計算本地雜湊與時間戳
            with open(filepath, "rb") as f: img_bytes = f.read()
            file_hash = sha256_bytes(img_bytes)
            timestamp_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

            # *** 核心修改：呼叫 GPT-4 mini 進行公證 ***
            print(f"正在為圖像 {file_hash[:10]}... 請求 AI 公證...")
            gpt_response = get_gpt_notarization(file_hash, timestamp_utc)
            print(f"AI 公證完成。")

            # 將所有資訊加入 session
            session_uploads.append({
                "filepath": filepath,
                "file_hash": file_hash,
                "timestamp_utc": timestamp_utc,
                "gpt_notarization": gpt_response # <-- 儲存 AI 回覆
            })
            
            return jsonify({
                "success": True,
                "preview_url": url_for('static_preview', filename=unique_filename),
                "version": len(session_uploads)
            })
        except Exception as e:
            return jsonify({"error": f"處理檔案時發生錯誤: {str(e)}"}), 500
    else:
        return jsonify({"error": "不支援的檔案類型"}), 400

# 步驟2: 結束任務 (已修改以包含 AI 公證資訊)
@app.route('/finalize_session', methods=['POST'])
def finalize_session():
    global latest_proof_data, session_uploads
    applicant_name = request.json.get('applicant_name')
    if not applicant_name: return jsonify({"error": "出證申請人名稱為必填項"}), 400
    if not session_uploads: return jsonify({"error": "沒有任何已上傳的圖像可供處理"}), 400

    try:
        snapshots = []
        for i, upload in enumerate(session_uploads):
            with open(upload['filepath'], "rb") as f: definitive_bytes = f.read()
            img_base64_str = base64.b64encode(definitive_bytes).decode('utf-8')
            
            snapshots.append({
                "version_index": i + 1,
                "timestamp_utc": upload['timestamp_utc'],
                "snapshot_hash": upload['file_hash'],
                "gpt_notarization": upload['gpt_notarization'], # <-- 將 AI 回覆加入證據
                "content_base64": img_base64_str
            })
        
        # ... (後續的雜湊計算與 JSON 生成邏輯與前版相同)
        report_id = str(uuid.uuid4())
        trace_token = str(uuid.uuid4())
        issued_at_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        temp_proof_for_hashing = {"report_id": report_id, "event_proof": {"trace_token": trace_token, "snapshots": snapshots}}
        proof_string_for_hashing = json.dumps(temp_proof_for_hashing, sort_keys=True, ensure_ascii=False).encode('utf-8')
        final_event_hash = sha256_bytes(proof_string_for_hashing)

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
        print(f"結束任務失敗: {e}")
        return jsonify({"error": f"結束任務失敗: {str(e)}"}), 500

# 步驟3: 產生 PDF 報告 (邏輯不變，但會使用更新後的 PDF 類別)
@app.route('/create_report', methods=['POST'])
def create_report():
    if not latest_proof_data:
        return jsonify({"error": "請先結束任務以生成證據資料"}), 400
    try:
        report_id = latest_proof_data['report_id']
        pdf = WesmartPDFReport()
        pdf.create_cover(latest_proof_data)
        pdf.create_evidence_pages(latest_proof_data)
        pdf.create_conclusion_page(latest_proof_data)
        report_filename = f"WesmartAI_Report_{report_id}.pdf"
        report_filepath = os.path.join(app.config['UPLOAD_FOLDER'], report_filename)
        pdf.output(report_filepath)
        return jsonify({"success": True, "report_url": url_for('static_download', filename=report_filename)})
    except Exception as e:
        print(f"報告生成失敗: {e}")
        return jsonify({"error": f"報告生成失敗: {str(e)}"}), 500

# --- 靜態檔案路由 (與前版相同) ---
@app.route('/static/preview/<path:filename>')
def static_preview(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/static/download/<path:filename>')
def static_download(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
