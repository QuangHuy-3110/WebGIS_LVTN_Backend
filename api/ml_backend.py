"""
ML Backend Server - Flask server cung cấp API cho hệ thống OCR biển hiệu
 - /detect-signs : Phát hiện các biển hiệu trong ảnh (YOLO), trả về danh sách boxes
 - /analyze      : OCR + LLM + Classifier trên một box đã chọn
"""

import os
import re
import sys
import base64
import json
import time
import concurrent.futures

# --- FIX LỖI PILLOW 10.0+ ---
import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from PIL import Image, ImageOps
import cv2
import numpy as np
import joblib
import torch
from flask import Flask, request, jsonify

from ultralytics import YOLO
from paddleocr import PaddleOCR
from vietocr.tool.predictor import Predictor
from vietocr.tool.config import Cfg
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
from underthesea import word_tokenize

# ==============================================================================
# HÀM LƯU LOG
# ==============================================================================
def write_log(text):
    print(text, flush=True)
    try:
        with open("log_ml_server.txt", "a", encoding="utf-8") as f:
            f.write(str(text) + "\n")
    except Exception:
        pass

# ==============================================================================
# CẤU HÌNH ĐƯỜNG DẪN
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
YOLO_MODEL_PATH = os.path.join(BASE_DIR, 'models', 'Best_Medium_640_50e_10p_auto_20260119_1637.pt')
MODEL_DIR = os.path.join(BASE_DIR, 'models')
DET_PATH  = os.path.join(MODEL_DIR, 'ch_PP-OCRv3_det_infer')
REC_PATH  = os.path.join(MODEL_DIR, 'en_PP-OCRv4_rec_infer')
CLS_PATH  = os.path.join(MODEL_DIR, 'ch_ppocr_mobile_v2.0_cls_infer')
VIETOCR_WEIGHT_PATH = os.path.join(MODEL_DIR, 'vietocr_v2_stage1_3103_0917.pth')
CLASSIFIER_PATH     = os.path.join(BASE_DIR, "model_phanloai_danhmuc_v7", "Linear_SVC_model.pkl")

# [MODEL LORA]
BASE_MODEL_ID   = "Qwen/Qwen2.5-0.5B-Instruct"
QWEN_ADAPTER_PATH = os.path.join(MODEL_DIR, 'qwen_0.5b_adapter_final_Step1_v6_hybrid')


# ==============================================================================
# CORE OCR BACKEND CLASS
# ==============================================================================
class OCRBackend:
    def __init__(self):
        write_log("=== Đang tải tất cả models (YOLO, PaddleOCR, VietOCR, Qwen, Classifier)... ===")

        # 1. YOLO
        self.yolo = YOLO(YOLO_MODEL_PATH)
        write_log("✅ YOLO loaded.")

        # 2. PaddleOCR (chỉ detection, không recognition)
        self.paddle = PaddleOCR(
            det_model_dir=DET_PATH, rec_model_dir=REC_PATH, cls_model_dir=CLS_PATH,
            det_limit_side_len=1028, det_db_unclip_ratio=1.1, det_db_thresh=0.35,
            det_db_box_thresh=0.5, use_angle_cls=True, lang='en',
            show_log=False, rec=False, use_gpu=True
        )
        write_log("✅ PaddleOCR loaded.")

        # 3. VietOCR
        config = Cfg.load_config_from_name('vgg_transformer')
        config['weights'] = VIETOCR_WEIGHT_PATH
        config['cnn']['pretrained'] = False
        config['device'] = 'cuda:0' if torch.cuda.is_available() else 'cpu'
        self.vietocr = Predictor(config)
        write_log("✅ VietOCR loaded.")

        # 4. Category Classifier
        self.classifier = joblib.load(CLASSIFIER_PATH) if os.path.exists(CLASSIFIER_PATH) else None
        write_log(f"✅ Classifier loaded: {self.classifier is not None}")

        # 5. Qwen LLM (LoRA)
        try:
            self.qwen_tokenizer = AutoTokenizer.from_pretrained(QWEN_ADAPTER_PATH)
            has_gpu = torch.cuda.is_available()
            base_model = AutoModelForCausalLM.from_pretrained(
                BASE_MODEL_ID,
                torch_dtype=torch.float16 if has_gpu else torch.float32,
                device_map="auto" if has_gpu else None,
                offload_folder="offload_qwen"
            )
            if not has_gpu:
                base_model = base_model.to("cpu")
            self.qwen_llm = PeftModel.from_pretrained(base_model, QWEN_ADAPTER_PATH)
            write_log("✅ Qwen LLM (LoRA) loaded.")
        except Exception as e:
            write_log(f"⚠️ Không thể tải Qwen LLM: {e}")
            self.qwen_llm = None

        write_log("=== Tất cả models đã sẵn sàng! ===\n")

    # ------------------------------------------------------------------
    # IMAGE PREPROCESSING HELPERS
    # ------------------------------------------------------------------
    def enhance_contrast(self, img):
        img_yuv = cv2.cvtColor(img, cv2.COLOR_BGR2YUV)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        img_yuv[:, :, 0] = clahe.apply(img_yuv[:, :, 0])
        return cv2.cvtColor(img_yuv, cv2.COLOR_YUV2BGR)

    def balance_local_illumination(self, img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        bg = cv2.GaussianBlur(gray, (81, 81), 0)
        balanced = cv2.divide(gray, bg, scale=255)
        balanced = cv2.normalize(balanced, None, 0, 255, cv2.NORM_MINMAX)
        return cv2.cvtColor(balanced, cv2.COLOR_GRAY2BGR)

    def sharpen_image(self, img):
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        return cv2.filter2D(img, -1, kernel)

    def grayscale_eq(self, img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return cv2.cvtColor(cv2.equalizeHist(gray), cv2.COLOR_GRAY2BGR)

    def binary_threshold(self, img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 41, 15
        )
        return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)

    def is_valid_text(self, text):
        return len(text.strip()) >= 2 and bool(re.search(r'[a-zA-Z0-9]', text))

    # ------------------------------------------------------------------
    # 3D RECTIFICATION
    # ------------------------------------------------------------------
    def rectify_whole_sign(self, img):
        ocr_res = self.paddle.ocr(img, cls=False, det=True, rec=False)
        if not ocr_res or ocr_res[0] is None or len(ocr_res[0]) < 1:
            return img

        def order_points(pts):
            rect = np.zeros((4, 2), dtype="float32")
            s = pts.sum(axis=1)
            rect[0] = pts[np.argmin(s)]
            rect[2] = pts[np.argmax(s)]
            diff = np.diff(pts, axis=1)
            rect[1] = pts[np.argmin(diff)]
            rect[3] = pts[np.argmax(diff)]
            return rect

        boxes = [order_points(np.array(b)) for b in ocr_res[0]]
        top_slopes, bot_slopes = [], []
        for b in boxes:
            if b[1][0] != b[0][0]:
                top_slopes.append((b[1][1] - b[0][1]) / (b[1][0] - b[0][0]))
            if b[2][0] != b[3][0]:
                bot_slopes.append((b[2][1] - b[3][1]) / (b[2][0] - b[3][0]))

        m_top = np.median(top_slopes) if top_slopes else 0
        m_bot = np.median(bot_slopes) if bot_slopes else 0
        all_pts = np.concatenate(boxes)

        width_text  = np.max(all_pts[:, 0]) - np.min(all_pts[:, 0])
        height_text = np.max(all_pts[:, 1]) - np.min(all_pts[:, 1])

        pad_x      = int(width_text  * 0.05)
        pad_y_bot  = int(height_text * 0.10)
        pad_y_top  = int(height_text * 0.10)

        min_x = np.min(all_pts[:, 0]) - pad_x
        max_x = np.max(all_pts[:, 0]) + pad_x
        c_top = np.min(all_pts[:, 1] - m_top * all_pts[:, 0]) - pad_y_top
        c_bot = np.max(all_pts[:, 1] - m_bot * all_pts[:, 0]) + pad_y_bot

        tl = [min_x, min_x * m_top + c_top]
        tr = [max_x, max_x * m_top + c_top]
        br = [max_x, max_x * m_bot + c_bot]
        bl = [min_x, min_x * m_bot + c_bot]

        if tl[1] >= bl[1] or tr[1] >= br[1]:
            return img

        src_pts = np.array([tl, tr, br, bl], dtype="float32")
        h_left  = bl[1] - tl[1]
        h_right = br[1] - tr[1]
        h_new   = int(max(h_left, h_right))
        w_new   = int(max_x - min_x)
        ratio   = max(h_left, h_right) / (min(h_left, h_right) + 1e-5)
        if 1.1 < ratio < 3.0:
            w_new = int(w_new * (1.0 + (ratio - 1.0) * 0.55))

        if w_new <= 0 or h_new <= 0:
            return img

        dst_pts = np.array([[0, 0], [w_new, 0], [w_new, h_new], [0, h_new]], dtype="float32")
        try:
            return cv2.warpPerspective(
                img, cv2.getPerspectiveTransform(src_pts, dst_pts),
                (w_new, h_new), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
            )
        except Exception:
            return img

    # ------------------------------------------------------------------
    # PADDLE DETECTION WITH COLLISION-AWARE PADDING
    # ------------------------------------------------------------------
    def detect_robust(self, img):
        h, w = img.shape[:2]
        sf = min(1.0, 1028 / max(h, w))
        img_s = cv2.resize(img, (int(w * sf), int(h * sf))) if sf < 1.0 else img
        res = self.paddle.ocr(img_s, cls=True, det=True, rec=False)

        if not res or not res[0]:
            return []

        raw_boxes  = [np.array(b, dtype="float32") / sf for b in res[0]]
        final_boxes = []

        for i, box in enumerate(raw_boxes):
            box_h         = max(np.linalg.norm(box[0] - box[3]), np.linalg.norm(box[1] - box[2]))
            desired_pad_top = box_h * 0.20
            desired_pad_bot = box_h * 0.20

            top_y   = min(box[0][1], box[1][1])
            bot_y   = max(box[2][1], box[3][1])
            left_x  = min(box[0][0], box[3][0])
            right_x = max(box[1][0], box[2][0])

            for j, other_box in enumerate(raw_boxes):
                if i == j:
                    continue
                o_top_y  = min(other_box[0][1], other_box[1][1])
                o_bot_y  = max(other_box[2][1], other_box[3][1])
                o_left_x = min(other_box[0][0], other_box[3][0])
                o_right_x= max(other_box[1][0], other_box[2][0])

                if not (right_x < o_left_x or left_x > o_right_x):
                    if o_bot_y <= top_y:
                        dist = top_y - o_bot_y
                        desired_pad_top = min(desired_pad_top, max(0, dist - 1.0))
                    elif o_top_y >= bot_y:
                        dist = o_top_y - bot_y
                        desired_pad_bot = min(desired_pad_bot, max(0, dist - 1.0))

            new_box = box.copy()
            new_box[0][1] -= desired_pad_top
            new_box[1][1] -= desired_pad_top
            new_box[2][1] += desired_pad_bot
            new_box[3][1] += desired_pad_bot
            final_boxes.append(new_box)

        return final_boxes

    # ------------------------------------------------------------------
    # LINE GROUPING
    # ------------------------------------------------------------------
    def fit_line_and_group(self, boxes):
        if not boxes:
            return []
        infos = [
            {
                'c': np.mean(b, axis=0),
                'h': max(np.linalg.norm(b[0] - b[3]), np.linalg.norm(b[1] - b[2])),
                'b': b
            }
            for b in boxes
        ]
        infos.sort(key=lambda x: x['c'][0])

        used = set()
        lines = []
        for i, s in enumerate(infos):
            if i in used:
                continue
            line = [s['b']]
            used.add(i)
            last = s
            for j in range(i + 1, len(infos)):
                if j in used:
                    continue
                c = infos[j]
                if (min(c['h'], last['h']) / max(c['h'], last['h'])) < 0.5:
                    continue
                if abs(c['c'][1] - last['c'][1]) > max(c['h'], last['h']) * 0.9:
                    continue
                if (c['c'][0] - last['c'][0]) > last['h'] * 5.0:
                    continue
                line.append(c['b'])
                used.add(j)
                last = c
            lines.append(line)

        line_stats = []
        for ln in lines:
            avg_y = sum([np.mean(b, axis=0)[1] for b in ln]) / len(ln)
            min_x = min([np.min(b[:, 0]) for b in ln])
            avg_h = sum([max(np.linalg.norm(b[0] - b[3]), np.linalg.norm(b[1] - b[2])) for b in ln]) / len(ln)
            line_stats.append({'line': ln, 'y': avg_y, 'x': min_x, 'h': avg_h})

        line_stats.sort(key=lambda item: item['y'])

        rows = []
        current_row = []
        for item in line_stats:
            if not current_row:
                current_row.append(item)
            else:
                row_y = sum([i2['y'] for i2 in current_row]) / len(current_row)
                row_h = sum([i2['h'] for i2 in current_row]) / len(current_row)
                if abs(item['y'] - row_y) < row_h * 0.5:
                    current_row.append(item)
                else:
                    rows.append(current_row)
                    current_row = [item]
        if current_row:
            rows.append(current_row)

        sorted_lines = []
        for row in rows:
            row.sort(key=lambda item: item['x'])
            for item in row:
                sorted_lines.append(item['line'])
        return sorted_lines

    # ------------------------------------------------------------------
    # PERSPECTIVE CROP PER LINE
    # ------------------------------------------------------------------
    def get_regression_rectified_crop(self, image, line_boxes):
        if not line_boxes:
            return None, None
        pts  = np.concatenate(line_boxes, axis=0)
        tops = np.array([b[0] for b in line_boxes] + [b[1] for b in line_boxes], dtype=np.float32)
        bots = np.array([b[3] for b in line_boxes] + [b[2] for b in line_boxes], dtype=np.float32)
        [vxt, vyt, x0t, y0t] = cv2.fitLine(tops, cv2.DIST_L2, 0, 0.01, 0.01).flatten()
        [vxb, vyb, x0b, y0b] = cv2.fitLine(bots, cv2.DIST_L2, 0, 0.01, 0.01).flatten()
        minx, maxx = np.min(pts[:, 0]), np.max(pts[:, 0])

        def gy(x, vx, vy, x0, y0):
            return y0 if abs(vx) < 1e-2 else y0 + (vy / vx) * (x - x0)

        src = np.array([
            [minx, gy(minx, vxt, vyt, x0t, y0t)],
            [maxx, gy(maxx, vxt, vyt, x0t, y0t)],
            [maxx, gy(maxx, vxb, vyb, x0b, y0b)],
            [minx, gy(minx, vxb, vyb, x0b, y0b)],
        ], dtype="float32")

        wn = np.linalg.norm(src[1] - src[0])
        hn = max(np.linalg.norm(src[3] - src[0]), np.linalg.norm(src[2] - src[1]))
        if hn > 5000 or wn > 5000 or hn <= 0 or wn <= 0:
            return None, None

        pw, ph = int(wn * 0.05), int(hn * 0.2)
        dst = np.array([[pw, ph], [wn + pw, ph], [wn + pw, hn + ph], [pw, hn + ph]], dtype="float32")
        try:
            return (
                src.astype(int),
                cv2.warpPerspective(
                    image, cv2.getPerspectiveTransform(src, dst),
                    (int(wn + pw * 2), int(hn + ph * 2)),
                    flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255)
                )
            )
        except Exception:
            return None, None

    # ------------------------------------------------------------------
    # REGEX PRE-EXTRACTION (ADDRESS + PHONE)
    # ------------------------------------------------------------------
    def regex_pre_extract(self, texts):
        extracted = {"ADDRESS": [], "PHONE": []}
        remaining_texts = []

        if not texts:
            return extracted, remaining_texts

        all_y = [np.max(t['box_points'].reshape(-1, 2)[:, 1]) for t in texts]
        all_h = [
            np.max(t['box_points'].reshape(-1, 2)[:, 1]) - np.min(t['box_points'].reshape(-1, 2)[:, 1])
            for t in texts
        ]
        global_max_y = max(all_y) if all_y else 1
        global_max_h = max(all_h) if all_h else 1
        first_addr_h = None

        phone_prefixes  = r'(?:điện thoại(?: liên hệ| di động)?|di động|dđ|tổng đài|cskh|chăm sóc khách hàng|tel|hotline|sđt|sdt|đt|phone|zalo|call|liên hệ|mobi|fax)'
        addr_prefixes   = r'(?:đ[iị]a ch[iỉ](?:\s*(?:đkkd|đăng ký kinh doanh|liên hệ|giao dịch))?|đ/c|đc|add(?:ress)?|trụ sở(?: chính)?|cơ sở\s*\d+|chi nhánh\s*\d+|cn\s*\d+)'
        phone_pattern   = re.compile(
            rf'(?i)(?:{phone_prefixes}\s*[:\-\.]?\s*)?((?:\+84|0|1800|1900|\(\s*\d{{2,5}}\s*\))(?:(?!\s*[-\.]\s*(?:\+84|0|1800|1900))[ \-\.\d]){{4,15}})(?=\b|[^\d])'
        )
        addr_admin_kw   = re.compile(
            r'\b(phường|quận|huyện|tỉnh|thành phố|thị xã|thị trấn|tp\.|q\.|p\.|tx\.|h\.|khu phố|kp\.|thôn|ấp|đường|quốc lộ|ql\d*|đại lộ|khu vực|kv|ninh kiều|bình thủy|cái răng|ô môn|thốt nốt|phong điền|cờ đỏ|thới lai|vĩnh thạnh)\b',
            re.IGNORECASE
        )
        short_addr_pat  = re.compile(
            r'^\s*(?:số|lô|kiot|ki-ốt|quầy|tầng|lầu\s+)?(?:[a-zA-Z]+\d+|\d+[a-zA-Z]*)(?:/\d{1,4}[a-zA-Z]?)?\s+[^\W\d_]+\s+[^\W\d_]+',
            re.IGNORECASE
        )
        addr_prefix_pat = re.compile(rf'(?i)^{addr_prefixes}\s*[:\-]*\s*')
        exclude_pat     = re.compile(
            r'^(?:công ty|cty|dntn|doanh nghiệp|nhà thuốc|siêu thị|tạp hóa|trái cây|cửa hàng|đại lý|quán|nhà hàng|trung tâm|bệnh viện|trường|salon|spa|chuyên|phòng khám|shop|store|gara|garage|hotel|khách sạn|nhà nghỉ|văn phòng|vpgd|showroom|kho|xưởng|ủy ban|ubnd|sở|ban|bộ|ngân hàng|doanh trại|tiệm|htx|nha khoa|răng hàm mặt|thẩm mỹ|viện|trạm|chợ|bánh mì|bánh tráng|cơ sở|tòa án|công an|chi cục|tổng cục|đài|nhà văn hóa|đảng bộ|chi bộ|hội đồng|đoàn)\b',
            re.IGNORECASE
        )

        for text_info in texts:
            current_text = text_info['text'].strip()
            box_coords   = text_info['box_points']
            pts          = box_coords.reshape(-1, 2)
            box_h        = np.max(pts[:, 1]) - np.min(pts[:, 1])
            box_y_center = (np.min(pts[:, 1]) + np.max(pts[:, 1])) / 2

            for match in list(phone_pattern.finditer(current_text)):
                full_match_str = match.group(0)
                raw_phone      = match.group(1)
                has_prefix     = bool(re.search(rf'(?i){phone_prefixes}', full_match_str))
                clean_digits   = re.sub(r'[^\d+]', '', raw_phone)
                if len(clean_digits) < 8 and not has_prefix:
                    continue
                extracted["PHONE"].append(clean_digits)
                current_text = current_text.replace(full_match_str, '').strip()

            current_text = re.sub(rf'(?i)^{phone_prefixes}?\s*[:\-\.]*\s*$', '', current_text).strip()
            if not current_text:
                continue

            is_addr       = False
            has_addr_pre  = bool(addr_prefix_pat.search(current_text))
            if has_addr_pre:
                is_addr = True
            elif short_addr_pat.search(current_text):
                is_addr = True
            elif addr_admin_kw.search(current_text):
                has_number      = bool(re.search(r'\d', current_text))
                has_comma       = ',' in current_text
                admin_matches   = len(addr_admin_kw.findall(current_text))
                is_small_text   = box_h <= global_max_h * 0.6
                is_bottom_half  = box_y_center >= global_max_y * 0.5
                if (has_number or has_comma or admin_matches >= 2) and (is_small_text or is_bottom_half):
                    is_addr = True

            if is_addr and not has_addr_pre and first_addr_h is not None:
                if box_h > first_addr_h * 1.8 or box_h < first_addr_h * 0.5:
                    is_addr = False

            if exclude_pat.search(current_text) and not has_addr_pre:
                is_addr = False

            if is_addr:
                if first_addr_h is None:
                    first_addr_h = box_h
                clean_addr = addr_prefix_pat.sub('', current_text).strip()
                clean_addr = re.sub(rf'(?i)(?:{phone_prefixes}).*$', '', clean_addr).strip(' ,.-')
                if clean_addr:
                    extracted["ADDRESS"].append(clean_addr)
            else:
                remaining_texts.append({'text': current_text, 'box_points': box_coords})

        if extracted["ADDRESS"]:
            final_addrs = []
            for addr in extracted["ADDRESS"]:
                is_dup = False
                for i, existing in enumerate(final_addrs):
                    if addr.lower() in existing.lower():
                        is_dup = True
                        break
                    elif existing.lower() in addr.lower():
                        final_addrs[i] = addr
                        is_dup = True
                        break
                if not is_dup:
                    final_addrs.append(addr)
            extracted["ADDRESS"] = [", ".join(final_addrs)]

        extracted["PHONE"] = list(dict.fromkeys(extracted["PHONE"]))
        return extracted, remaining_texts

    # ------------------------------------------------------------------
    # POST-PROCESS LLM OUTPUT
    # ------------------------------------------------------------------
    def post_process_llm_data(self, ext_json):
        for k in ["BRAND", "SERVICE", "ADDRESS", "PHONE", "O"]:
            if k not in ext_json or not isinstance(ext_json[k], list):
                ext_json[k] = [ext_json.get(k)] if ext_json.get(k) else []
            ext_json[k] = [str(x).strip() for x in ext_json[k] if str(x).strip()]
            ext_json[k] = list(dict.fromkeys(ext_json[k]))
        return ext_json

    # ------------------------------------------------------------------
    # EXTRACT EMAIL / WEBSITE FROM raw text
    # ------------------------------------------------------------------
    def extract_info_and_clean_text(self, texts):
        combined = " ".join(texts)
        emails   = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', combined)
        emails   = list(dict.fromkeys(emails))

        raw_webs = re.findall(
            r'\b(?:www\.[a-zA-Z0-9-]+\.[a-zA-Z]{2,}|[a-zA-Z0-9-]+\.(?:com|vn|net|org)(?:\.[a-zA-Z]{2,})?)\b',
            combined
        )
        exclude_domains = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'icloud.com']
        webs = [w for w in raw_webs if '@' not in w and not any(w.lower() == d for d in exclude_domains)]
        webs = list(dict.fromkeys(webs))
        return {"email": emails, "website": webs}

    # ------------------------------------------------------------------
    # DETECT YOLO SIGNS (PUBLIC)
    # Returns: (frame, boxes_list)
    #   boxes_list = [{"coords": (x1,y1,x2,y2), "conf": float}, ...]  sorted desc by conf
    # ------------------------------------------------------------------
    def detect_yolo_signs(self, img_path):
        try:
            pil_image = ImageOps.exif_transpose(Image.open(img_path))
            frame = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        except Exception:
            frame = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)

        t0 = time.time()
        yolo_res = self.yolo(frame, conf=0.6, verbose=False)
        t_yolo   = time.time() - t0

        boxes = []
        if yolo_res[0].boxes:
            for box in yolo_res[0].boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                if conf > 0.6:
                    boxes.append({"coords": [x1, y1, x2, y2], "conf": round(conf, 4)})

        boxes.sort(key=lambda x: x['conf'], reverse=True)
        write_log(f"[YOLO] Phát hiện {len(boxes)} biển hiệu trong {t_yolo:.3f}s")
        return frame, boxes, t_yolo

    # ------------------------------------------------------------------
    # FULL OCR PIPELINE (given a specific box)
    # Returns a result dict (not a generator, for server use)
    # ------------------------------------------------------------------
    def run_ocr_pipeline(self, frame, selected_box):
        x1, y1, x2, y2 = selected_box

        # Step 1 – Crop & enhance
        sign_crop     = frame[y1:y2, x1:x2]
        sign_enhanced = self.enhance_contrast(sign_crop)

        # Step 2 – Rectify 3D
        flat_sign = self.rectify_whole_sign(sign_enhanced)

        # Step 3 – PaddleOCR detection
        det_input = self.balance_local_illumination(flat_sign)
        valid_boxes = [
            b for b in self.detect_robust(det_input)
            if (np.max(b[:, 1]) - np.min(b[:, 1])) > max(12, int(flat_sign.shape[0] * 0.04))
        ]
        lines = self.fit_line_and_group(valid_boxes)

        # Step 4 – VietOCR recognition
        results_data = []
        for idx, line_boxes in enumerate(lines):
            box_visual, crop_img = self.get_regression_rectified_crop(flat_sign, line_boxes)
            if crop_img is None or crop_img.size == 0:
                continue

            h, w      = crop_img.shape[:2]
            target_w  = max(32, int(w * (64 / h)))
            crop_img  = cv2.resize(crop_img, (target_w, 64), interpolation=cv2.INTER_CUBIC)

            best = {'prob': 0.0, 'text': '', 'name': '', 'img': crop_img}
            filters = [
                ("Original", lambda x: x),
                ("Sharpen",  self.sharpen_image),
                ("Gray_Eq",  self.grayscale_eq),
                ("Binary",   self.binary_threshold),
            ]
            for fname, func in filters:
                proc      = func(crop_img)
                pil_input = Image.fromarray(cv2.cvtColor(proc, cv2.COLOR_BGR2RGB))
                text, prob = self.vietocr.predict(pil_input, return_prob=True)
                if prob > best['prob']:
                    best = {'name': fname, 'text': text, 'prob': prob, 'img': proc}
                if prob > 0.88:
                    break

            if best['prob'] > 0.8 and self.is_valid_text(best['text']):
                results_data.append({
                    'id': idx + 1,
                    'box_points': box_visual.reshape((-1, 1, 2)),
                    'text': best['text'],
                    'conf': round(best['prob'], 4),
                })

        write_log(f"[VietOCR] Đọc được {len(results_data)} dòng chữ.")

        # Step 5 – Regex + Qwen LLM extraction
        ext_json = {"BRAND": [], "SERVICE": [], "ADDRESS": [], "PHONE": [], "O": []}
        remaining_for_llm = []

        if results_data and self.qwen_llm:
            regex_extracted, remaining_for_llm = self.regex_pre_extract(results_data)
            ext_json["ADDRESS"].extend(regex_extracted["ADDRESS"])
            ext_json["PHONE"].extend(regex_extracted["PHONE"])

            if remaining_for_llm:
                ctx = "\n".join([
                    f"[{int(np.min(r['box_points'][:,0,0]))}, {int(np.min(r['box_points'][:,0,1]))}, "
                    f"{int(np.max(r['box_points'][:,0,0]))}, {int(np.max(r['box_points'][:,0,1]))}] {r['text']}"
                    for r in remaining_for_llm
                ])
                prompt = f"""Nhiệm vụ: Phân tích các dòng chữ OCR từ biển hiệu và trích xuất vào định dạng JSON.
Chỉ xuất JSON hợp lệ, các giá trị phải là mảng (Array). Không giải thích.

Các trường cần trích xuất:
- "BRAND": Tên thương hiệu, công ty, cửa hàng.
- "SERVICE": Các loại hình dịch vụ, ngành nghề, sản phẩm kinh doanh.
- "O": Thông tin phụ, nhiễu: câu slogan, bằng cấp, nhãn hiệu quảng cáo.

--- VÍ DỤ ---
Đầu vào OCR:
[50, 20, 800, 60] CÔNG TY TNHH DƯỢC PHẨM TÂY ĐÔ
[100, 80, 750, 150] NHÀ THUỐC HUỲNH LỘC
[200, 160, 600, 200] CHUYÊN BÁN SỈ VÀ LẺ THUỐC TÂY

Đầu ra JSON:
{{"BRAND": ["CÔNG TY TNHH DƯỢC PHẨM TÂY ĐÔ NHÀ THUỐC HUỲNH LỘC"], "SERVICE": ["CHUYÊN BÁN SỈ VÀ LẺ THUỐC TÂY"], "O": []}}
-------------

Đầu vào OCR:
{ctx}

Đầu ra JSON:"""
                inputs = {
                    k: v.to(self.qwen_llm.device)
                    for k, v in self.qwen_tokenizer(
                        [self.qwen_tokenizer.apply_chat_template(
                            [{"role": "user", "content": prompt}],
                            tokenize=False, add_generation_prompt=True
                        )],
                        return_tensors="pt"
                    ).items()
                }
                with torch.no_grad():
                    g_ids = self.qwen_llm.generate(
                        **inputs, max_new_tokens=1024, do_sample=False,
                        pad_token_id=self.qwen_tokenizer.eos_token_id
                    )
                res_text = self.qwen_tokenizer.batch_decode(
                    [g[len(i):] for i, g in zip(inputs["input_ids"], g_ids)],
                    skip_special_tokens=True
                )[0]
                write_log(f"[Qwen LLM] Raw output: {res_text[:300]}")

                try:
                    start_i = res_text.find('{')
                    end_i   = res_text.rfind('}')
                    if start_i != -1 and end_i != -1:
                        llm_json = json.loads(res_text[start_i:end_i + 1])
                        for k in ["BRAND", "SERVICE", "O"]:
                            if k in llm_json:
                                val = llm_json[k]
                                if isinstance(val, list):
                                    ext_json[k].extend(val)
                                elif isinstance(val, str):
                                    ext_json[k].append(val)
                except Exception:
                    pass

        ext_json = self.post_process_llm_data(ext_json)

        # Fallback: nếu LLM không cho brand/service, dùng raw text
        if not ext_json.get("BRAND") and not ext_json.get("SERVICE"):
            if remaining_for_llm:
                fallback = " ".join([r['text'] for r in remaining_for_llm]).strip()
                if fallback:
                    ext_json["SERVICE"] = [fallback]

        # Step 6 – Linear SVC Classifier
        category = "Chưa xác định"
        if results_data and self.classifier:
            br = " ".join(ext_json.get("BRAND", [])).lower()
            sr = " ".join(ext_json.get("SERVICE", [])).lower()
            if br or sr:
                text_input = f"{br} {sr}".strip()
                try:
                    text_seg = word_tokenize(text_input, format="text")
                    category = str(self.classifier.predict([text_seg])[0])
                except Exception as e:
                    write_log(f"[Classifier] Error: {e}")
            else:
                category = "Thiếu dữ liệu"

        write_log(f"[Classifier] Category = {category}")

        # Build contact info
        all_raw_texts = [r['text'] for r in results_data]
        contact_info  = self.extract_info_and_clean_text(all_raw_texts)

        return {
            "category":     category,
            "extracted":    ext_json,
            "texts":        all_raw_texts,
            "contact_info": contact_info,
            "info": {
                "brand":    ext_json.get("BRAND", []),
                "service":  ext_json.get("SERVICE", []),
                "address":  ext_json.get("ADDRESS", []),
                "phone":    ext_json.get("PHONE", []),
                "email":    contact_info.get("email", []),
                "website":  contact_info.get("website", []),
            }
        }


# ==============================================================================
# FLASK SERVER
# ==============================================================================
app = Flask(__name__)

# Lazy initialization of backend
_backend = None

def get_backend():
    global _backend
    if _backend is None:
        _backend = OCRBackend()
    return _backend


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})


@app.route('/detect-signs', methods=['POST'])
def detect_signs():
    """
    Phát hiện tất cả biển hiệu trong ảnh bằng YOLO.
    Request JSON: { "image_path": "/path/to/image.jpg" }
    Response JSON:
    {
        "signs_count": int,
        "signs": [
            {"index": 0, "conf": 0.95, "coords": [x1, y1, x2, y2], "conf_pct": "95.0%"},
            ...
        ],
        "multiple": true/false   // true nếu > 1 biển hiệu > 70% conf
    }
    """
    try:
        data = request.get_json(force=True)
        img_path = data.get('image_path')
        if not img_path or not os.path.exists(img_path):
            return jsonify({"error": "image_path không hợp lệ hoặc không tồn tại"}), 400

        backend = get_backend()
        frame, boxes, t_yolo = backend.detect_yolo_signs(img_path)

        signs = []
        for i, b in enumerate(boxes):
            signs.append({
                "index":    i,
                "conf":     b["conf"],
                "conf_pct": f"{b['conf'] * 100:.1f}%",
                "coords":   b["coords"],
            })

        return jsonify({
            "signs_count": len(signs),
            "signs":       signs,
            "multiple":    len(signs) > 1,
        })

    except Exception as e:
        write_log(f"[/detect-signs] Exception: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/analyze', methods=['POST'])
def analyze():
    """
    Phân tích OCR + LLM trên một box biển hiệu đã chọn.
    Request JSON:
    {
        "image_path": "/path/to/image.jpg",
        "box_index": 0           // index trong danh sách boxes từ /detect-signs (default: 0)
        // hoặc truyền thẳng:
        "box": [x1, y1, x2, y2]  // nếu muốn bypass detect
    }
    Response JSON: { "category": ..., "info": {...}, "texts": [...], "contact_info": {...} }
    """
    try:
        data     = request.get_json(force=True)
        img_path = data.get('image_path')
        if not img_path or not os.path.exists(img_path):
            return jsonify({"error": "image_path không hợp lệ"}), 400

        backend = get_backend()

        # Nếu có truyền box trực tiếp
        if 'box' in data:
            box = data['box']
            frame, _, _ = backend.detect_yolo_signs(img_path)
        else:
            frame, boxes, _ = backend.detect_yolo_signs(img_path)
            if not boxes:
                return jsonify({"error": "Không phát hiện biển hiệu nào"}), 404
            idx = int(data.get('box_index', 0))
            if idx >= len(boxes):
                idx = 0
            box = boxes[idx]['coords']

        result = backend.run_ocr_pipeline(frame, box)
        return jsonify(result)

    except Exception as e:
        write_log(f"[/analyze] Exception: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    write_log("🚀 Khởi động ML Server trên cổng 5050...")
    # Pre-load backend on startup
    get_backend()
    app.run(host='0.0.0.0', port=5050, debug=False, threaded=False)