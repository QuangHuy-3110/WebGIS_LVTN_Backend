import os
import time
import random

# Thiết lập môi trường Django để gọi CSDL
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
import django
django.setup()

from api import routing_utils

def run_benchmarks():
    bbox = (105.6717, 9.9679, 105.8697, 10.0708)
    print("="*50)
    print("DỮ LIỆU KIỂM THỬ BÁO CÁO LUẬN VĂN WEB GIS")
    print("="*50)
    
    print("\n1. Đang nạp đồ thị từ CSDL vào RAM ...")
    t_start = time.time()
    rows = routing_utils.fetch_graph_data(bbox)
    graph, edges_info, nodes_coords, idx = routing_utils.build_graph_with_index(rows)
    print(f"[OK] Nạp xong {len(edges_info)} cạnh đường. Thời gian: {(time.time() - t_start)*1000:.2f} ms")

    print("\n2. [TEST CHUYÊN SÂU] SNAP-TO-EDGE (100 lần click ngẫu nhiên)")
    snap_times = []
    for _ in range(100):
        # Giả lập người dùng click bậy bạ quanh Cần Thơ
        lng = random.uniform(bbox[0], bbox[2])
        lat = random.uniform(bbox[1], bbox[3])
        
        t0 = time.time()
        res = routing_utils.find_nearest_edge_rtree(lng, lat, edges_info, idx)
        t1 = time.time()
        snap_times.append((t1 - t0) * 1000)
    
    print(f"-> R-Tree Snap trung bình     : {sum(snap_times)/len(snap_times):.2f} ms (Yêu cầu báo cáo: < 50ms)")
    print(f"-> Tốc độ chậm nhất (Max)     : {max(snap_times):.2f} ms")

    print("\n3. [TEST CHUYÊN SÂU] BÀI TOÁN TÌM ĐƯỜNG (100 cặp tọa độ ngẫu nhiên)")
    node_ids = list(nodes_coords.keys())
    routing_times = []
    
    for _ in range(100):
        start_node = random.choice(node_ids)
        end_node = random.choice(node_ids)
        
        t0 = time.time()
        # Chạy thuật toán A* đã cài đặt
        path = routing_utils.a_star_solver(graph, start_node, end_node, nodes_coords)
        t1 = time.time()
        routing_times.append((t1 - t0) * 1000)
        
    print(f"-> Tính toán A* trung bình  : {sum(routing_times)/len(routing_times):.2f} ms (Yêu cầu báo cáo: 150-200ms)")
    valid_paths = [p for p in routing_times if p > 0] # Lọc các node trùng
    if valid_paths:
        print(f"-> Thời gian Max (Tìm rất xa) : {max(valid_paths):.2f} ms")
        
run_benchmarks()
