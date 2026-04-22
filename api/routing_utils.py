import json
import heapq
import math
from django.db import connection
from rtree import index
# --- 1. CÁC HÀM TOÁN HỌC & HEURISTIC ---

def dist_sq(p1, p2):
    return (p1[0] - p2[0])**2 + (p1[1] - p2[1])**2

def get_projection_point(p, a, b):
    # Hình chiếu vuông góc của một điểm lên đường thẳng
    px, py = p
    ax, ay = a
    bx, by = b
    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0: return a, 0
    t = ((px - ax) * dx + (py - ay) * dy) / (dx*dx + dy*dy)
    t = max(0, min(1, t))
    mx = ax + t * dx
    my = ay + t * dy
    return (mx, my), t

def haversine(coord1, coord2):
    """
    Tính khoảng cách chim bay (Heuristic) giữa 2 tọa độ (lon, lat) theo mét.
    A* cần hàm này để ước lượng chi phí còn lại.
    """
    lon1, lat1 = coord1
    lon2, lat2 = coord2
    R = 6371000  # Bán kính trái đất (mét)

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2)**2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c

# --- 2. TƯƠNG TÁC DATABASE ---

def fetch_graph_data(bbox):
    sql = """
        SELECT gid, source, target, cost, reverse_cost, length_m, name, ST_AsGeoJSON(the_geom)
        FROM ways
        WHERE the_geom && ST_MakeEnvelope(%s, %s, %s, %s, 4326)
          AND tag_id NOT IN (114, 117, 118, 119, 122)
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, bbox)
        rows = cursor.fetchall()
    return rows

def build_graph(rows):
    graph = {}
    edges_info = {}
    nodes_coords = {} # <--- MỚI: Cần lưu tọa độ Node để chạy A*

    for row in rows:
        edge_id, u, v, db_cost, db_rev_cost, length_m, name, geom_json = row
        geom = json.loads(geom_json)

        # Lưu thông tin cạnh
        actual_cost = length_m if db_cost >= 0 else -1
        actual_rev_cost = length_m if db_rev_cost >= 0 else -1

        edges_info[edge_id] = {
            'geom': geom,
            'source': u,
            'target': v,
            'cost': actual_cost,
            'reverse_cost': actual_rev_cost,
            'name': name,
            'length_m': length_m
        }

        # --- MỚI: Lưu tọa độ Node (Lấy điểm đầu và cuối của Geometry) ---
        # GeoJSON coordinates: [[lon, lat], ...]
        coords = geom['coordinates']
        nodes_coords[u] = tuple(coords[0])  # Tọa độ Source Node
        nodes_coords[v] = tuple(coords[-1]) # Tọa độ Target Node

        # Xây dựng Graph
        if actual_cost >= 0:
            if u not in graph: graph[u] = []
            graph[u].append((v, actual_cost, edge_id))
        
        if actual_rev_cost >= 0:
            if v not in graph: graph[v] = []
            graph[v].append((u, actual_rev_cost, edge_id))
        
    return graph, edges_info, nodes_coords # <--- Trả về thêm nodes_coords

def build_graph_with_index(rows):
    """
    Xây dựng Graph, lưu tọa độ Node và khởi tạo R-tree index cho các cạnh.
    Trả về: graph, edges_info, nodes_coords, idx
    """
    graph = {}
    edges_info = {}
    nodes_coords = {}
    
    # Khởi tạo R-tree index
    idx = index.Index()

    for row in rows:
        # Unpack dữ liệu từ SQL (gid, source, target, cost, reverse_cost, length, name, geom)
        edge_id, u, v, db_cost, db_rev_cost, length_m, name, geom_json = row
        geom = json.loads(geom_json)
        coords = geom['coordinates']

        # 1. Xác định chi phí di chuyển (hỗ trợ đường một chiều)
        # Nếu cost < 0 nghĩa là không thể đi theo hướng đó
        actual_cost = length_m if db_cost >= 0 else -1
        actual_rev_cost = length_m if db_rev_cost >= 0 else -1

        # 2. Lưu thông tin cạnh để tra cứu sau này
        edges_info[edge_id] = {
            'geom': geom,
            'source': u,
            'target': v,
            'cost': actual_cost,
            'reverse_cost': actual_rev_cost
        }

        # 3. Lưu tọa độ Node thực (Lấy điểm đầu và cuối của LineString)
        # Cần thiết cho hàm Heuristic (Haversine) của A*
        nodes_coords[u] = tuple(coords[0])
        nodes_coords[v] = tuple(coords[-1])

        # 4. Xây dựng Danh sách kề (Adjacency List) cho đồ thị
        if actual_cost >= 0:
            if u not in graph: graph[u] = []
            graph[u].append((v, actual_cost, edge_id))
        
        if actual_rev_cost >= 0:
            if v not in graph: graph[v] = []
            graph[v].append((u, actual_rev_cost, edge_id))

        # 5. Đưa cạnh vào R-tree Index
        # Tính toán Bounding Box (khung bao) của con đường
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        edge_bbox = (min(lons), min(lats), max(lons), max(lats))
        
        # Insert vào cây: (ID của cạnh, tọa độ khung bao, object đính kèm)
        idx.insert(edge_id, edge_bbox)
        
    return graph, edges_info, nodes_coords, idx

def find_nearest_edge_rtree(click_lon, click_lat, edges_info, idx):
    """
    Sử dụng R-tree để tìm cạnh gần nhất với điểm click.
    Trả về 1 dictionary duy nhất hoặc None.
    """
    p = (click_lon, click_lat)
    
    # 1. Tạo một vùng tìm kiếm nhỏ (Bounding Box) xung quanh điểm click
    # 0.001 độ tương đương khoảng 111m ở xích đạo
    tolerance = 0.001 
    search_bbox = (
        click_lon - tolerance, click_lat - tolerance,
        click_lon + tolerance, click_lat + tolerance
    )

    # 2. Lấy danh sách ID các cạnh nằm trong vùng tìm kiếm
    candidate_ids = list(idx.intersection(search_bbox))

    # 3. Nếu không có cạnh nào trong vùng tolerance, lấy 3 cạnh gần nhất tuyệt đối
    # Điều này quan trọng khi người dùng click ở vùng thưa thớt đường xá
    if not candidate_ids:
        candidate_ids = list(idx.nearest(p, 3))

    best_edge_id = None
    min_dist_sq = float('inf')
    best_ratio = 0.5
    best_proj_point = None

    # 4. Duyệt qua các ứng viên để tìm điểm chiếu chính xác nhất
    for edge_id in candidate_ids:
        # Lấy thông tin hình học của cạnh từ edges_info
        info = edges_info.get(edge_id)
        if not info:
            continue
            
        coords = info['geom']['coordinates']
        
        # Duyệt từng phân đoạn (segment) của sợi dây LineString
        for i in range(len(coords) - 1):
            p1 = tuple(coords[i])
            p2 = tuple(coords[i+1])
            
            # Hàm get_projection_point đã định nghĩa ở phần trước của bạn
            proj, t = get_projection_point(p, p1, p2)
            
            # Tính bình phương khoảng cách (tối ưu hơn khai căn)
            d = dist_sq(p, proj)
            
            if d < min_dist_sq:
                min_dist_sq = d
                best_edge_id = edge_id
                best_ratio = t 
                best_proj_point = proj

    # 5. Trả về kết quả duy nhất
    if best_edge_id is not None:
        return {
            "edge_id": best_edge_id,
            "ratio": best_ratio,
            "proj_point": best_proj_point
        }
        
    return None

# --- 3. TÌM CẠNH GẦN NHẤT (Giữ nguyên hàm find_nearest_edge_in_ram) ---
def find_nearest_edge_in_ram(click_lon, click_lat, edges_info):
    p = (click_lon, click_lat)
    best_edge_id = None
    min_dist_sq = float('inf')
    best_ratio = 0.5
    best_proj_point = None

    for edge_id, info in edges_info.items():
        coords = info['geom']['coordinates']
        for i in range(len(coords) - 1):
            p1 = tuple(coords[i])
            p2 = tuple(coords[i+1])
            proj, t = get_projection_point(p, p1, p2)
            d = dist_sq(p, proj)
            if d < min_dist_sq:
                min_dist_sq = d
                best_edge_id = edge_id
                best_ratio = t 
                best_proj_point = proj

    if best_edge_id:
        return {
            "edge_id": best_edge_id,
            "ratio": best_ratio,
            "proj_point": best_proj_point
        }
    return None

# --- 4. XỬ LÝ NODE ẢO (Cập nhật cho A*) ---

def add_virtual_node(graph, edges_info, nodes_coords, edge_id, proj_point, role='start', vn_id=-1, ratio=0.5):
    """
    Cần truyền thêm nodes_coords và proj_point để lưu tọa độ node ảo cho A* dùng
    """
    edge_data = edges_info[edge_id]
    u = edge_data['source']
    v = edge_data['target']
    
    cost_uv = edge_data['cost'] 
    cost_vu = edge_data['reverse_cost']

    cost_u_vn = cost_uv * ratio if cost_uv >= 0 else -1
    cost_vn_v = cost_uv * (1 - ratio) if cost_uv >= 0 else -1
    cost_v_vn = cost_vu * (1 - ratio) if cost_vu >= 0 else -1
    cost_vn_u = cost_vu * ratio if cost_vu >= 0 else -1

    # --- MỚI: Lưu tọa độ Node ảo để A* tính Heuristic ---
    nodes_coords[vn_id] = proj_point 
    # ---------------------------------------------------

    if vn_id not in graph: graph[vn_id] = []
    
    if role == 'start':
        if cost_uv >= 0: graph[vn_id].append((v, cost_vn_v, edge_id))
        if cost_vu >= 0: graph[vn_id].append((u, cost_vn_u, edge_id))
    elif role == 'end':
        if cost_uv >= 0: 
            if u not in graph: graph[u] = []
            graph[u].append((vn_id, cost_u_vn, edge_id))
        if cost_vu >= 0:
            if v not in graph: graph[v] = []
            graph[v].append((vn_id, cost_v_vn, edge_id))
            
    return u, v 

def cleanup_graph(graph, nodes_coords, start_vn, end_vn, end_neighbors):
    """Cần xóa cả trong nodes_coords nữa"""
    if start_vn in graph: del graph[start_vn]
    if end_vn in graph: del graph[end_vn]
    
    # Xóa tọa độ ảo khỏi danh sách tọa độ
    if start_vn in nodes_coords: del nodes_coords[start_vn]
    if end_vn in nodes_coords: del nodes_coords[end_vn]

    for node in end_neighbors:
        if node in graph:
            graph[node] = [e for e in graph[node] if e[0] != end_vn]

# --- 5. THUẬT TOÁN ---

# Dijkstra (Giữ nguyên logic cũ)
def dijkstra_solver(graph, start, end):
    pq = [(0, start)]
    came_from = {start: None}
    cost_so_far = {start: 0}
    
    while pq:
        curr_cost, curr = heapq.heappop(pq)
        if curr == end:
            path_details = [] 
            temp = curr
            while temp != start:
                prev, eid = came_from[temp]
                path_details.append((eid, temp)) 
                temp = prev
            return path_details[::-1]
        
        if curr_cost > cost_so_far.get(curr, float('inf')): continue

        for neighbor, weight, edge_id in graph.get(curr, []):
            new_cost = curr_cost + weight
            if new_cost < cost_so_far.get(neighbor, float('inf')):
                cost_so_far[neighbor] = new_cost
                heapq.heappush(pq, (new_cost, neighbor))
                came_from[neighbor] = (curr, edge_id)
    return None

# A* (A-STAR) MỚI
def a_star_solver(graph, start, end, nodes_coords):
    """
    Tìm đường dùng A* (f = g + h)
    """
    # Heuristic ban đầu từ Start -> End
    start_h = haversine(nodes_coords[start], nodes_coords[end])
    
    # Priority Queue lưu: (f_score, current_node)
    pq = [(start_h, start)]
    
    came_from = {start: None}
    g_score = {start: 0} # Chi phí thực tế đã đi
    
    while pq:
        curr_f, curr = heapq.heappop(pq)
        
        if curr == end:
            # Truy vết (Giống hệt Dijkstra)
            path_details = [] 
            temp = curr
            while temp != start:
                prev, eid = came_from[temp]
                path_details.append((eid, temp)) 
                temp = prev
            return path_details[::-1]
        
        # Lấy g_score hiện tại của node đang xét
        curr_g = g_score.get(curr, float('inf'))

        for neighbor, weight, edge_id in graph.get(curr, []):
            new_g = curr_g + weight
            
            if new_g < g_score.get(neighbor, float('inf')):
                # Tìm thấy đường ngon hơn tới neighbor
                g_score[neighbor] = new_g
                
                # Tính Heuristic: Khoảng cách chim bay từ neighbor -> ĐÍCH
                h = haversine(nodes_coords[neighbor], nodes_coords[end])
                new_f = new_g + h
                
                heapq.heappush(pq, (new_f, neighbor))
                came_from[neighbor] = (curr, edge_id)
                
    return None

def slice_geometry(full_geom, split_point, target_node_coords):
    coords = full_geom['coordinates']
    px, py = split_point
    
    # 1. Tìm segment chứa split_point
    segment_idx = 0
    min_dist = float('inf')
    
    for i in range(len(coords) - 1):
        p1 = coords[i]
        p2 = coords[i+1]
        
        # Khoảng cách từ split_point tới segment p1-p2
        proj, r = get_projection_point((px, py), p1, p2)
        d = (px - proj[0])**2 + (py - proj[1])**2
        if d < min_dist:
            min_dist = d
            segment_idx = i

    start_dist = (coords[0][0] - target_node_coords[0])**2 + (coords[0][1] - target_node_coords[1])**2
    end_dist = (coords[-1][0] - target_node_coords[0])**2 + (coords[-1][1] - target_node_coords[1])**2
    
    sliced_coords = []
    
    if start_dist < end_dist:
        # Hướng về node đầu (coords[0])
        sliced_coords = [(px, py)]
        for i in range(segment_idx, -1, -1):
            sliced_coords.append(coords[i])
    else:
        # Hướng về node cuối (coords[-1])
        sliced_coords = [(px, py)]
        for i in range(segment_idx + 1, len(coords)):
            sliced_coords.append(coords[i])
            
    return {
        "type": "LineString",
        "coordinates": sliced_coords
    }