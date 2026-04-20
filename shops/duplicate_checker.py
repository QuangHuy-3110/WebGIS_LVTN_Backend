# shops/duplicate_checker.py
"""
Pipeline kiểm tra trùng cửa hàng (5 bước):
1. Normalize text  (lowercase, remove accent, regex clean)
2. Retrieve candidates  (PostGIS ST_DWithin 15m)
3. Compute similarity  (partial_ratio, token_set_ratio, levenshtein)
4. Aggregate score  (weighted scoring)
5. Decision  (auto_reject / warning / accept)

Chỉ so sánh với các cửa hàng trong bán kính 15 mét.
"""

import re
import unicodedata

# ---------------------------------------------------------------------------
# STEP 1: TEXT NORMALIZATION
# ---------------------------------------------------------------------------

# Bảng chuyển đổi ký tự Việt đặc biệt không thuộc NFD unicode
_VIET_EXTRA = str.maketrans({
    'đ': 'd', 'Đ': 'D',
})


def normalize_text(s: str) -> str:
    """
    Chuẩn hóa văn bản:
    - lowercase
    - remove accent (NFD decomposition + strip combining marks)
    - replace Vietnamese 'đ'
    - regex clean (giữ lại chữ-số, bỏ ký tự đặc biệt)
    - collapse whitespace
    """
    if not s:
        return ''
    s = s.lower()
    s = s.translate(_VIET_EXTRA)
    # NFD decompose → strip combining diacritical marks (U+0300–U+036F)
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    # Recompose (NFC) then keep only alphanumeric + space
    s = unicodedata.normalize('NFC', s)
    s = re.sub(r'[^a-z0-9\s]', ' ', s)      # special chars → space
    s = re.sub(r'\s+', ' ', s).strip()
    return s


# ---------------------------------------------------------------------------
# STEP 2: RETRIEVE CANDIDATES via PostGIS ST_DWithin
# ---------------------------------------------------------------------------

def get_candidates(lat: float, lng: float, radius_m: float = 15.0):
    """
    Truy vấn các cửa hàng trong bán kính `radius_m` mét xung quanh (lat, lng).
    Sử dụng PostGIS geography type để tính khoảng cách chính xác theo mét.
    Trả về QuerySet của Store.
    """
    from django.contrib.gis.geos import Point
    from django.contrib.gis.db.models.functions import Distance
    from django.contrib.gis.measure import D
    from .models import Store

    point = Point(lng, lat, srid=4326)
    qs = (
        Store.objects
        .filter(location__distance_lte=(point, D(m=radius_m)))
        .annotate(distance=Distance('location', point))
        .order_by('distance')
    )
    return qs


# ---------------------------------------------------------------------------
# STEP 3: COMPUTE SIMILARITY METRICS
# ---------------------------------------------------------------------------

def _levenshtein(a: str, b: str) -> int:
    """Levenshtein edit distance."""
    if not a:
        return len(b)
    if not b:
        return len(a)
    m, n = len(a), len(b)
    # Use two-row rolling approach for memory efficiency
    prev = list(range(n + 1))
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        curr[0] = i
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(
                curr[j - 1] + 1,          # insert
                prev[j] + 1,              # delete
                prev[j - 1] + cost,       # substitute
            )
        prev, curr = curr, [0] * (n + 1)
    return prev[n]


def _ratio(a: str, b: str) -> float:
    """Simple ratio: 1 - normalized levenshtein distance."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    dist = _levenshtein(a, b)
    max_len = max(len(a), len(b))
    return 1.0 - dist / max_len


def _partial_ratio(a: str, b: str) -> float:
    """
    Partial ratio: tìm substring ngắn hơn trong chuỗi dài hơn,
    trả về ratio tốt nhất (giống partial_ratio của rapidfuzz).
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    # Đảm bảo a <= b
    if len(a) > len(b):
        a, b = b, a
    best = 0.0
    la, lb = len(a), len(b)
    for start in range(lb - la + 1):
        sub = b[start:start + la]
        score = _ratio(a, sub)
        if score > best:
            best = score
        if best == 1.0:
            break
    return best


def _token_set_ratio(a: str, b: str) -> float:
    """
    Token set ratio: so sánh các token bất kể thứ tự (giống token_set_ratio của rapidfuzz).
    intersection + sorted_intersection vs each string.
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    inter = tokens_a & tokens_b
    sorted_inter = ' '.join(sorted(inter))
    rest_a = ' '.join(sorted(tokens_a - inter))
    rest_b = ' '.join(sorted(tokens_b - inter))

    s1 = (sorted_inter + ' ' + rest_a).strip()
    s2 = (sorted_inter + ' ' + rest_b).strip()
    s3 = sorted_inter

    scores = [
        _ratio(s1, s2),
        _ratio(s1, s3),
        _ratio(s2, s3),
    ]
    return max(scores)


def compute_similarity(name_input: str, name_candidate: str):
    """
    Tính 3 metrics cho cặp tên (đã normalize) và trả về dict.
    """
    n1 = normalize_text(name_input)
    n2 = normalize_text(name_candidate)

    if not n1 or not n2:
        return {'partial_ratio': 0.0, 'token_set_ratio': 0.0, 'levenshtein_ratio': 0.0}

    return {
        'partial_ratio': _partial_ratio(n1, n2),
        'token_set_ratio': _token_set_ratio(n1, n2),
        'levenshtein_ratio': _ratio(n1, n2),
    }


# ---------------------------------------------------------------------------
# STEP 4: AGGREGATE SCORE (weighted)
# ---------------------------------------------------------------------------

# Weights (phải cộng lại = 1.0)
_WEIGHTS = {
    'partial_ratio':      0.40,   # quan trọng nhất: bắt được tên ngắn trong tên dài
    'token_set_ratio':    0.35,   # bắt được thứ tự từ khác nhau
    'levenshtein_ratio':  0.25,   # độ chính xác ký tự
}


def aggregate_score(metrics: dict) -> float:
    """Tính điểm tổng hợp có trọng số."""
    return sum(_WEIGHTS[k] * metrics.get(k, 0.0) for k in _WEIGHTS)


# ---------------------------------------------------------------------------
# STEP 5: DECISION THRESHOLDS
# ---------------------------------------------------------------------------

# Ngưỡng quyết định
_THRESHOLD_WARNING = 0.70   # >= thì WARNING
_THRESHOLD_REJECT  = 0.88   # >= thì AUTO_REJECT (rất giống)


def decide(score: float) -> str:
    """
    Dựa trên điểm tổng hợp:
    - score >= 0.88 → 'reject'   (cực kỳ giống, gần như trùng hoàn toàn)
    - score >= 0.70 → 'warning'  (nghi ngờ trùng, cần xem xét)
    - score <  0.70 → 'accept'   (không trùng)
    """
    if score >= _THRESHOLD_REJECT:
        return 'reject'
    elif score >= _THRESHOLD_WARNING:
        return 'warning'
    else:
        return 'accept'


# ---------------------------------------------------------------------------
# MAIN PIPELINE
# ---------------------------------------------------------------------------

def check_duplicate(name: str, lat: float, lng: float, radius_m: float = 15.0):
    """
    Chạy toàn bộ pipeline kiểm tra trùng.

    Returns:
        {
            "decision": "accept" | "warning" | "reject",
            "matches": [
                {
                    "id": int,
                    "name": str,
                    "address": str,
                    "distance_m": float,
                    "score": float,
                    "metrics": { partial_ratio, token_set_ratio, levenshtein_ratio },
                    "decision": str,
                },
                ...
            ]
        }
    """
    # ── Step 1: Normalize input ──────────────────────────────────────────
    name_norm = normalize_text(name)
    if not name_norm:
        return {'decision': 'accept', 'matches': []}

    # ── Step 2: Retrieve candidates (15m radius) ─────────────────────────
    try:
        candidates = get_candidates(lat, lng, radius_m)
    except Exception as e:
        # Nếu PostGIS lỗi (ví dụ tọa độ chưa có), trả về accept để không block
        return {'decision': 'accept', 'matches': [], 'error': str(e)}

    # ── Step 3 + 4: Score each candidate ────────────────────────────────
    results = []
    overall_decision = 'accept'

    for store in candidates:
        metrics   = compute_similarity(name, store.name)
        score     = aggregate_score(metrics)
        store_dec = decide(score)

        dist_m = round(store.distance.m, 2) if hasattr(store, 'distance') and store.distance else None

        results.append({
            'id':         store.id,
            'name':       store.name,
            'address':    store.address,
            'distance_m': dist_m,
            'score':      round(score, 4),
            'metrics': {
                'partial_ratio':     round(metrics['partial_ratio'],     4),
                'token_set_ratio':   round(metrics['token_set_ratio'],   4),
                'levenshtein_ratio': round(metrics['levenshtein_ratio'], 4),
            },
            'decision':   store_dec,
        })

        # Nâng overall_decision lên mức cao nhất gặp được
        if store_dec == 'reject':
            overall_decision = 'reject'
        elif store_dec == 'warning' and overall_decision == 'accept':
            overall_decision = 'warning'

    # Sắp xếp kết quả theo score giảm dần
    results.sort(key=lambda x: x['score'], reverse=True)

    return {
        'decision': overall_decision,
        'matches':  results,
    }
