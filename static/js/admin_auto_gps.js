/* static/js/admin_auto_gps.js */

// 1. BIẾN TOÀN CỤC (Để tránh lỗi ReferenceError)
window.globalLeafletMap = null;
window.currentMarker = null;

// Hàm cập nhật tọa độ vào ô input ẩn của GeoDjango
window.updateLocationInput = function(lat, lng) {
    var locationInput = document.querySelector('#id_location');
    if (locationInput) {
        // Định dạng WKT: SRID=4326;POINT(Longitude Latitude)
        locationInput.value = `SRID=4326;POINT(${lng} ${lat})`;
        console.log("📍 Đã cập nhật input tọa độ:", lat, lng);
    }
}

// Hàm setup marker (cho phép kéo thả)
window.setupExistingMarker = function(map) {
    if (!map) return;
    map.eachLayer(layer => {
        if (layer instanceof L.Marker) {
            window.currentMarker = layer;
            if (window.currentMarker.dragging) {
                window.currentMarker.dragging.enable();
                window.currentMarker.on('dragend', function(e) {
                     var pos = e.target.getLatLng();
                     window.updateLocationInput(pos.lat, pos.lng);
                });
            }
        }
    });
}

// Hàm vẽ marker mới khi có tọa độ từ ảnh
window.updateMapMarker = function(lat, lng) {
    if (!window.globalLeafletMap) return;
    const latlng = [lat, lng];

    if (window.currentMarker) window.globalLeafletMap.removeLayer(window.currentMarker);
    
    // Xóa marker cũ do widget tạo ra (nếu có)
    window.globalLeafletMap.eachLayer(layer => {
        if (layer instanceof L.Marker) window.globalLeafletMap.removeLayer(layer);
    });

    window.currentMarker = L.marker(latlng, { draggable: true }).addTo(window.globalLeafletMap);
    
    // Bắt sự kiện kéo thả marker để chỉnh lại vị trí
    window.currentMarker.on('dragend', function(event) {
        var position = event.target.getLatLng();
        window.updateLocationInput(position.lat, position.lng);
    });

    window.globalLeafletMap.flyTo(latlng, 16);
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

// 2. LẮNG NGHE SỰ KIỆN MAP (Bắt buộc để lấy đối tượng map)
window.addEventListener("map:init", function (e) {
    var detail = e.detail;
    // Kiểm tra xem đây có phải là map của field 'location' không
    if (detail.id.indexOf('location') !== -1) {
        console.log("🗺️ Map đã tải:", detail.id);
        window.globalLeafletMap = detail.map;
        window.setupExistingMarker(detail.map);
    }
});

// 3. XỬ LÝ UPLOAD ẢNH & ĐIỀN ID
document.addEventListener("DOMContentLoaded", function () {
    const imageInput = document.querySelector('input[name="quick_image"]');
    const idsInput = document.querySelector('input[name="uploaded_image_ids"]'); // Ô input ẩn chứa ID
    const addressInput = document.querySelector('#id_address');
    
    // Mảng chứa các ID ảnh đã upload thành công
    let uploadedIds = [];
    // Mảng chứa file chờ upload (để xử lý tuần tự nếu cần)
    
    if (imageInput) {
        imageInput.addEventListener('change', function (e) {
            const files = Array.from(e.target.files);
            if (files.length === 0) return;

            console.log(`🚀 Bắt đầu upload ${files.length} ảnh...`);

            // Upload từng file một
            files.forEach((file, index) => {
                uploadFileAndGetId(file, index === 0);
            });

            // QUAN TRỌNG: Xóa file khỏi input để khi bấm Save không gửi file nặng lên nữa
            // Chúng ta chỉ cần gửi ID của ảnh thôi
            imageInput.value = ''; 
        });
    }

    function uploadFileAndGetId(file, isFirst) {
        const formData = new FormData();
        formData.append('image', file);

        fetch('/api/utils/quick-upload/', {
            method: 'POST',
            body: formData,
            headers: { 'X-CSRFToken': getCookie('csrftoken') }
        })
        .then(res => res.json())
        .then(data => {
            if (data.id) {
                console.log(`✅ Upload thành công: ID=${data.id}`);
                
                // 1. Thêm ID vào mảng
                uploadedIds.push(data.id);
                
                // 2. Cập nhật chuỗi ID vào ô input ẩn (VD: "15,16,17")
                if (idsInput) {
                    idsInput.value = uploadedIds.join(',');
                    console.log("📝 Cập nhật form ids:", idsInput.value);
                }

                // 3. Nếu là ảnh đầu tiên, lấy GPS để điền vào form
                if (isFirst && data.latitude && data.longitude) {
                    // Điền địa chỉ text
                    if (addressInput && !addressInput.value) {
                        addressInput.value = data.address || "";
                    }
                    
                    // Fallback map
                    if (!window.globalLeafletMap && window.id_location_map) {
                        window.globalLeafletMap = window.id_location_map;
                    }

                    // Điền tọa độ
                    window.updateLocationInput(data.latitude, data.longitude);
                    window.updateMapMarker(data.latitude, data.longitude);
                    
                    alert("📍 Đã lấy được tọa độ từ ảnh! Bạn hãy điền nốt thông tin và bấm Save.");
                }
            }
        })
        .catch(err => console.error("❌ Lỗi upload:", err));
    }
});