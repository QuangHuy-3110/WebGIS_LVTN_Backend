from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from . import routing_utils  # Import file utils vừa tạo

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
            
            path_details = None
            if algo_type == 'astar':
                # A* cần thêm nodes_coords để tính khoảng cách
                path_details = routing_utils.a_star_solver(graph, START_ID, END_ID, nodes_coords)
            else:
                # Dijkstra truyền thống
                path_details = routing_utils.dijkstra_solver(graph, START_ID, END_ID)

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
                        "properties": {"edge_id": eid, "type": "road"}
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