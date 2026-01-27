/* static/js/admin_auto_gps.js */

var globalLeafletMap = null;
var currentMarker = null; // Biến lưu marker hiện tại để quản lý kéo thả

// 1. Bắt sự kiện map:init (Khắc phục lỗi không tìm thấy bản đồ)
window.addEventListener("map:init", function (e) {
    var detail = e.detail;
    if (detail.id.indexOf('location') !== -1) {
        console.log("🗺️ Đã bắt được bản đồ Leaflet:", detail.id);
        globalLeafletMap = detail.map;
        
        // Nếu bản đồ đã có sẵn điểm (khi sửa bài), ta làm cho nó draggable
        setupExistingMarker();
    }
});

document.addEventListener("DOMContentLoaded", function () {
    const imageInput = document.querySelector('input[name="quick_image"]');
    const addressInput = document.querySelector('#id_address');
    const locationInput = document.querySelector('#id_location');

    if (imageInput) {
        imageInput.addEventListener('change', function (e) {
            // 2. Chỉ lấy file đầu tiên để phân tích GPS
            const files = e.target.files;
            if (!files || files.length === 0) return;
            
            const firstFile = files[0]; // <--- CHỈ LẤY FILE ĐẦU TIÊN

            // Kiểm tra map
            if (!globalLeafletMap && window.id_location_map) {
                 globalLeafletMap = window.id_location_map;
            }

            alert(`⏳ Đang lấy tọa độ từ ảnh đầu tiên: ${firstFile.name}...`);

            const formData = new FormData();
            formData.append('image', firstFile);

            fetch('/api/utils/analyze-image/', {
                method: 'POST',
                body: formData,
                headers: { 'X-CSRFToken': getCookie('csrftoken') }
            })
            .then(res => res.json())
            .then(data => {
                if (data.latitude && data.longitude) {
                    
                    // Điền Text
                    if (addressInput) addressInput.value = data.address || "";
                    
                    // Cập nhật ô ẩn (Database)
                    updateLocationInput(data.latitude, data.longitude);

                    // Vẽ và bay tới điểm (Có tính năng kéo thả)
                    updateMapMarker(data.latitude, data.longitude);

                    alert(`✅ Đã cập nhật vị trí!\nBạn có thể KÉO THẢ chấm đỏ để chỉnh lại cho chính xác.`);
                } else {
                    alert("⚠️ Ảnh đầu tiên không có GPS. Hãy nhập tay hoặc chọn ảnh khác.");
                }
            })
            .catch(err => console.error(err));
        });
    }

    // --- HÀM VẼ MARKER CÓ TÍNH NĂNG DRAGGABLE ---
    function updateMapMarker(lat, lng) {
        if (!globalLeafletMap) return;

        const latlng = [lat, lng];

        // Xóa marker cũ nếu có
        if (currentMarker) {
            globalLeafletMap.removeLayer(currentMarker);
        }
        
        // Xóa các marker mặc định của widget nếu có
        globalLeafletMap.eachLayer(layer => {
            if (layer instanceof L.Marker) globalLeafletMap.removeLayer(layer);
        });

        // 3. TẠO MARKER MỚI VỚI DRAGGABLE: TRUE
        currentMarker = L.marker(latlng, {
            draggable: true // <--- QUAN TRỌNG: Cho phép kéo
        }).addTo(globalLeafletMap);

        // 4. LẮNG NGHE SỰ KIỆN KÉO THẢ (DRAGEND)
        currentMarker.on('dragend', function(event) {
            var marker = event.target;
            var position = marker.getLatLng();
            
            console.log("📍 Đã di chuyển marker tới:", position);
            
            // Cập nhật lại ô input ẩn để khi Save sẽ lấy tọa độ mới
            updateLocationInput(position.lat, position.lng);
        });

        globalLeafletMap.flyTo(latlng, 16);
    }

    // Hàm cập nhật chuỗi WKT vào ô input ẩn của Django
    function updateLocationInput(lat, lng) {
        if (locationInput) {
            // GeoDjango format: POINT(Longitude Latitude)
            locationInput.value = `SRID=4326;POINT(${lng} ${lat})`;
        }
    }

    // Hàm hỗ trợ setup marker cho bài viết đã có sẵn (Edit mode)
    function setupExistingMarker() {
        if (!globalLeafletMap) return;
        // Tìm marker có sẵn
        globalLeafletMap.eachLayer(layer => {
            if (layer instanceof L.Marker) {
                currentMarker = layer;
                // Bật tính năng kéo thả cho marker cũ
                if (currentMarker.dragging) {
                    currentMarker.dragging.enable();
                    currentMarker.on('dragend', function(e) {
                         var pos = e.target.getLatLng();
                         updateLocationInput(pos.lat, pos.lng);
                    });
                }
            }
        });
    }

    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
});