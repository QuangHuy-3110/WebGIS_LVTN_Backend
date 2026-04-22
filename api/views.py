from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from . import routing_utils  # Import file utils vừa tạo
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

class RoutingView(APIView):
    """
    API tìm đường dùng Python thuần (In-Memory + Virtual Nodes)
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        try:
            # 1. Lấy tọa độ và thuật toán
            start_lat = request.query_params.get('start_lat')
            start_lng = request.query_params.get('start_lng')
            end_lat = request.query_params.get('end_lat')
            end_lng = request.query_params.get('end_lng')
            
            # Lấy tham số thuật toán: 'dijkstra' (default) hoặc 'astar'
            algo_type = request.query_params.get('algo', 'dijkstra') 

            if not all([start_lat, start_lng, end_lat, end_lng]):
                return Response({"error": "Thiếu tọa độ"}, status=status.HTTP_400_BAD_REQUEST)

            start_coords = (float(start_lng), float(start_lat))
            end_coords = (float(end_lng), float(end_lat))

            bbox = (105.6717, 9.9679, 105.8697, 10.0708) 
            
            rows = routing_utils.fetch_graph_data(bbox)
            
            # --- UPDATE: Hứng thêm nodes_coords ---
            graph, edges_info, nodes_coords = routing_utils.build_graph(rows)

            # graph, edges_info, nodes_coords, idx = routing_utils.build_graph_with_index(rows)

            if not graph: return Response({"error": "Lỗi dữ liệu"}, status=500)

            start_res = routing_utils.find_nearest_edge_in_ram(start_coords[0], start_coords[1], edges_info)
            end_res = routing_utils.find_nearest_edge_in_ram(end_coords[0], end_coords[1], edges_info)

            # start_res = routing_utils.find_nearest_edge_rtree(start_coords[0], start_coords[1], edges_info, idx)
            # end_res = routing_utils.find_nearest_edge_rtree(end_coords[0], end_coords[1], edges_info, idx)

            if not start_res or not end_res:
                return Response({"error": "Ngoài vùng bản đồ"}, status=400)

            # --- Xử lý trùng cạnh (giữ nguyên logic cũ) ---
            if start_res['edge_id'] == end_res['edge_id']:
                # ... (Giữ nguyên đoạn code trả về đường thẳng nếu trùng cạnh) ...
                # (Copy lại đoạn code xử lý trùng cạnh từ câu trả lời trước vào đây)
                eid = start_res['edge_id']
                geojson = {
                    "type": "FeatureCollection",
                    "features": [
                        { "type": "Feature", "geometry": {"type": "LineString", "coordinates": [[start_coords[0], start_coords[1]], start_res['proj_point']]}, "properties": {"type": "virtual"} },
                        { "type": "Feature", "geometry": {"type": "LineString", "coordinates": [start_res['proj_point'], end_res['proj_point']]}, "properties": {"edge_id": eid, "type": "road"} },
                        { "type": "Feature", "geometry": {"type": "LineString", "coordinates": [end_res['proj_point'], [end_coords[0], end_coords[1]]]}, "properties": {"type": "virtual"} }
                    ]
                }
                return Response(geojson, status=status.HTTP_200_OK)

            # --- Thêm Node ảo (Truyền thêm nodes_coords) ---
            START_ID = -1
            END_ID = -2
            
            routing_utils.add_virtual_node(
                graph, edges_info, nodes_coords, 
                start_res['edge_id'], start_res['proj_point'], 
                'start', START_ID, start_res['ratio']
            )
            
            u_end, v_end = routing_utils.add_virtual_node(
                graph, edges_info, nodes_coords, 
                end_res['edge_id'], end_res['proj_point'],
                'end', END_ID, end_res['ratio']
            )

            # --- LỰA CHỌN THUẬT TOÁN ---
            print(f"Đang chạy thuật toán: {algo_type.upper()}")
            
            import time
            start_algo_time = time.time()
            
            path_details = None
            if algo_type == 'astar':
                # A* cần thêm nodes_coords để tính khoảng cách
                path_details = routing_utils.a_star_solver(graph, START_ID, END_ID, nodes_coords)
            else:
                # Dijkstra truyền thống
                path_details = routing_utils.dijkstra_solver(graph, START_ID, END_ID)

            end_algo_time = time.time()
            print(f"⏱️ [MEASURE] Đo lường tốc độ thuật toán ({algo_type.upper()}): {(end_algo_time - start_algo_time)*1000:.2f} ms")

            # Snap-to-edge accuracy:
            start_dist_to_proj = routing_utils.haversine(start_coords, start_res['proj_point'])
            end_dist_to_proj = routing_utils.haversine(end_coords, end_res['proj_point'])
            print(f"🎯 [MEASURE] Đo lường độ chính xác của Snap-to-Edge: StartPoint sai số {start_dist_to_proj:.2f}m, EndPoint sai số {end_dist_to_proj:.2f}m")

            # --- Tạo GeoJSON (Giữ nguyên logic cũ) ---
            if path_details:
                geojson = { "type": "FeatureCollection", "features": [] }
                
                # Connector đầu
                geojson["features"].append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": [[start_coords[0], start_coords[1]], start_res['proj_point']]},
                    "properties": {"type": "virtual"}
                })

                # Đường chính
                for i, (eid, target_node_id) in enumerate(path_details):
                    original_geom = edges_info[eid]['geom']
                    final_geom = original_geom 
                    
                    if i == 0: 
                        u = edges_info[eid]['source']
                        target_coords = original_geom['coordinates'][0] if u == target_node_id else original_geom['coordinates'][-1]
                        final_geom = routing_utils.slice_geometry(original_geom, start_res['proj_point'], target_coords)

                    elif i == len(path_details) - 1:
                        _, prev_node_id = path_details[i-1]
                        u_curr = edges_info[eid]['source']
                        prev_node_coords = original_geom['coordinates'][0] if u_curr == prev_node_id else original_geom['coordinates'][-1]
                        final_geom = routing_utils.slice_geometry(original_geom, end_res['proj_point'], prev_node_coords)

                    geojson["features"].append({
                        "type": "Feature",
                        "geometry": final_geom,
                        "properties": {
                            "edge_id": eid, 
                            "type": "road",
                            "name": edges_info[eid].get('name', 'Không tên'),
                            "length_m": edges_info[eid].get('length_m', 0)
                        }
                    })

                # Connector cuối
                geojson["features"].append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": [end_res['proj_point'], [end_coords[0], end_coords[1]]]},
                    "properties": {"type": "virtual"}
                })
                
                # Cleanup (Thêm nodes_coords vào hàm cleanup)
                routing_utils.cleanup_graph(graph, nodes_coords, START_ID, END_ID, [u_end, v_end])
                
                return Response(geojson, status=status.HTTP_200_OK)
            
            else:
                routing_utils.cleanup_graph(graph, nodes_coords, START_ID, END_ID, [u_end, v_end])
                return Response({"type": "FeatureCollection", "features": []}, status=200)

        except Exception as e:
            print("Error:", e)
            return Response({"error": str(e)}, status=500)


def _dms_to_decimal(dms, ref):
    """
    Chuyển tọa độ DMS (Degrees, Minutes, Seconds) từ EXIF sang decimal degrees.
    dms: tuple of 3 IFDRational values (degrees, minutes, seconds)
    ref: 'N', 'S', 'E', 'W'
    """
    degrees = float(dms[0])
    minutes = float(dms[1])
    seconds = float(dms[2])
    decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
    if ref in ['S', 'W']:
        decimal = -decimal
    return decimal


class ExtractGPSView(APIView):
    """
    API trích xuất tọa độ GPS từ EXIF của ảnh JPG/JPEG/PNG.
    POST /api/extract-gps/
    Body: multipart/form-data với field 'image'
    Response: {"lat": float, "lng": float} hoặc {"error": "..."}
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        image_file = request.FILES.get('image')
        if not image_file:
            return Response({"error": "Vui lòng tải lên một file ảnh."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            img = Image.open(image_file)
            exif_data = img._getexif()

        except Exception:
            return Response({"error": "Không thể đọc file ảnh. Hãy thử với file JPG/JPEG."}, status=status.HTTP_400_BAD_REQUEST)

        if not exif_data:
            return Response({"error": "Ảnh không có thông tin EXIF."}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        # Tìm tag GPS IFD
        gps_ifd = None
        for tag_id, value in exif_data.items():
            tag_name = TAGS.get(tag_id, tag_id)
            if tag_name == 'GPSInfo':
                gps_ifd = value
                break

        if not gps_ifd:
            return Response({"error": "Ảnh không có thông tin GPS. Hãy chụp bằng điện thoại với định vị được bật."}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        # Decode GPS tags
        gps_info = {}
        for key, val in gps_ifd.items():
            decoded_key = GPSTAGS.get(key, key)
            gps_info[decoded_key] = val

        lat_dms  = gps_info.get('GPSLatitude')
        lat_ref  = gps_info.get('GPSLatitudeRef')
        lng_dms  = gps_info.get('GPSLongitude')
        lng_ref  = gps_info.get('GPSLongitudeRef')
        
        if not all([lat_dms, lat_ref, lng_dms, lng_ref]):
            return Response({"error": "Dữ liệu GPS không đầy đủ trong ảnh."}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        try:
            lat = _dms_to_decimal(lat_dms, lat_ref)
            lng = _dms_to_decimal(lng_dms, lng_ref)
        except Exception:
            return Response({"error": "Không thể phân tích tọa độ GPS từ ảnh."}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        return Response({"lat": round(lat, 7), "lng": round(lng, 7)}, status=status.HTTP_200_OK)