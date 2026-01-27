from django.db import connection
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
import json

class RoutingView(APIView):
    """
    API tìm đường nội bộ dùng PostGIS + pgRouting (Bảng đã Noding)
    Input: ?start_lat=...&start_lng=...&end_lat=...&end_lng=...
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        try:
            # 1. Lấy tọa độ từ URL
            start_lat = request.query_params.get('start_lat')
            start_lng = request.query_params.get('start_lng')
            end_lat = request.query_params.get('end_lat')
            end_lng = request.query_params.get('end_lng')

            if not all([start_lat, start_lng, end_lat, end_lng]):
                return Response({"error": "Thiếu tọa độ"}, status=status.HTTP_400_BAD_REQUEST)

            # 2. Câu Query SQL tìm đường (QUAN TRỌNG: Dùng bảng _noded)
            query = """
            WITH 
            start_node AS (
                SELECT id FROM planet_osm_line_noded_vertices_pgr
                ORDER BY the_geom <-> ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 3857) 
                LIMIT 1
            ),
            end_node AS (
                SELECT id FROM planet_osm_line_noded_vertices_pgr
                ORDER BY the_geom <-> ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 3857) 
                LIMIT 1
            )
            SELECT 
                json_build_object(
                    'type', 'FeatureCollection',
                    'features', json_agg(
                        json_build_object(
                            'type', 'Feature',
                            'geometry', ST_AsGeoJSON(ST_Transform(b.geom, 4326))::json,
                            'properties', json_build_object('name', c.name)
                        )
                    )
                ) as geojson
            FROM pgr_dijkstra(
                -- 1. THÊM reverse_cost VÀO CÂU SELECT
                'SELECT id, source, target, length as cost, reverse_cost FROM planet_osm_line_noded',
                (SELECT id FROM start_node),
                (SELECT id FROM end_node),
                directed := true  -- 2. BẬT CHẾ ĐỘ CÓ HƯỚNG (QUAN TRỌNG)
            ) a
            JOIN planet_osm_line_noded b ON a.edge = b.id
            LEFT JOIN planet_osm_line c ON b.old_id = c.osm_id;
            """

            # 3. Thực thi
            with connection.cursor() as cursor:
                # Lưu ý thứ tự: Lng trước, Lat sau
                cursor.execute(query, [start_lng, start_lat, end_lng, end_lat])
                row = cursor.fetchone()
                
                if row and row[0]:
                    return Response(row[0], status=status.HTTP_200_OK)
                else:
                    # Trường hợp không tìm thấy đường (ví dụ 2 điểm quá xa hoặc không kết nối)
                    return Response({"type": "FeatureCollection", "features": []}, status=status.HTTP_200_OK)

        except Exception as e:
            print("Routing Error:", e)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)