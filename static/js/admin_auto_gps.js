/* static/js/admin_auto_gps.js */

// 1. GLOBAL VARIABLES
window.globalLeafletMap = null;
window.currentMarker = null;
window.hasManuallyDraggedMarker = false;

// ── Lưu dữ liệu biển hiệu để cho phép đổi lựa chọn ──
window._signData = {
    signs:        null,   // danh sách biển hiệu từ bước 1
    tmpPath:      null,   // đường dẫn file tạm
    gps:          null,   // dữ liệu GPS gốc
    currentIdx:   null,   // index biển hiệu đang được dùng
    cardIndex:    null,   // card index trong preview
    isFirst:      true,
};


window.updateLocationInput = function (lat, lng) {
    var el = document.querySelector('#id_location');
    if (el) el.value = 'SRID=4326;POINT(' + lng + ' ' + lat + ')';
}

window.setupExistingMarker = function (map) {
    if (!map) return;
    map.eachLayer(function (layer) {
        if (layer instanceof L.Marker) {
            window.currentMarker = layer;
            if (window.currentMarker.dragging) {
                window.currentMarker.dragging.enable();
                window.currentMarker.on('dragend', function (e) {
                    var pos = e.target.getLatLng();
                    window.updateLocationInput(pos.lat, pos.lng);
                    window.hasManuallyDraggedMarker = true;
                    if (window.checkDuplicateStore) window.checkDuplicateStore();
                });
            }
        }
    });
}

window.updateMapMarker = function (lat, lng) {
    if (!window.globalLeafletMap) return;
    var latlng = [lat, lng];
    if (window.currentMarker) {
        window.globalLeafletMap.removeLayer(window.currentMarker);
    } else {
        // Fallback in case currentMarker wasn't caught, try to find and remove default marker without touching existingStoresLayer
        window.globalLeafletMap.eachLayer(function (layer) {
            if (layer instanceof L.Marker && (!window.existingStoresLayer || !window.existingStoresLayer.hasLayer(layer))) {
                window.globalLeafletMap.removeLayer(layer);
            }
        });
    }
    window.currentMarker = L.marker(latlng, { draggable: true }).addTo(window.globalLeafletMap);
    window.currentMarker.on('dragend', function (event) {
        var position = event.target.getLatLng();
        window.updateLocationInput(position.lat, position.lng);
        window.hasManuallyDraggedMarker = true;
        if (window.checkDuplicateStore) window.checkDuplicateStore();
    });
    window.globalLeafletMap.flyTo(latlng, 16);
    if (window.checkDuplicateStore) window.checkDuplicateStore();
}

function getCookie(name) {
    var cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// 2. MAP EVENT
window.addEventListener("map:init", function (e) {
    var detail = e.detail;
    if (detail.id.indexOf('location') !== -1) {
        window.globalLeafletMap = detail.map;
        window.setupExistingMarker(detail.map);

        // Load existing stores onto the map to visually check for duplicates
        window.loadExistingStores(detail.map);
    }
});

window.loadExistingStores = function (map) {
    if (!map) return;
    fetch('/api/stores/')
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (window.existingStoresLayer) {
                map.removeLayer(window.existingStoresLayer);
            }

            // Save globally for duplicate name checking
            window.allExistingStores = data.features ? data.features : (data.results ? data.results.features || data.results : data);

            checkDuplicateStore(); // Call immediately in case name is already filled

            var existingStoreIcon = L.icon({
                iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-grey.png',
                shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
                iconSize: [25, 41],
                iconAnchor: [12, 41],
                popupAnchor: [1, -34],
                shadowSize: [41, 41]
            });

            window.existingStoresLayer = L.geoJSON(data, {
                pointToLayer: function (feature, latlng) {
                    // Cửa hàng hiện tại đang chỉnh sửa sẽ có tên hoặc id, có thể bỏ qua nếu trùng vị trí không?
                    // Ở đây cứ hiển thị tất cả
                    return L.marker(latlng, {
                        icon: existingStoreIcon,
                        title: feature.properties.name || 'Cửa hàng đã tồn tại'
                    });
                },
                onEachFeature: function (feature, layer) {
                    var popupContent = '<div style="font-family: sans-serif; min-width: 150px;">' +
                        '<b style="color: #dc3545;">\u26A0 Cửa hàng đã tồn tại:</b><br>' +
                        '<b>' + (feature.properties.name || 'Không tên') + '</b><br>' +
                        '<span style="font-size: 11px; color: #666;">' + (feature.properties.address || 'Không có địa chỉ') + '</span>' +
                        '</div>';
                    layer.bindPopup(popupContent);
                }
            }).addTo(map);
        })
        .catch(function (err) { console.error('Error fetching existing stores:', err); });
}

// ============================================================
// 2.5. DUPLICATE STORE WARNING (NAME & GPS)
// ============================================================
window.checkDuplicateStore = function () {
    if (!window.allExistingStores) return;
    var nameInput = document.querySelector('#id_name');
    var val = nameInput ? nameInput.value.trim().toLowerCase() : '';

    var currLat = null, currLng = null;
    if (window.currentMarker) {
        var pos = window.currentMarker.getLatLng();
        currLat = pos.lat; currLng = pos.lng;
    } else {
        var locInput = document.querySelector('#id_location');
        if (locInput && locInput.value) {
            var matchObj = locInput.value.match(/POINT\(([\d\.-]+)\s+([\d\.-]+)\)/);
            if (matchObj) {
                currLng = parseFloat(matchObj[1]);
                currLat = parseFloat(matchObj[2]);
            }
        }
    }

    function calcDist(lat1, lon1, lat2, lon2) {
        if (!lat1 || !lon1 || !lat2 || !lon2) return 999999;
        var R = 6371e3;
        var f1 = lat1 * Math.PI / 180;
        var f2 = lat2 * Math.PI / 180;
        var df = (lat2 - lat1) * Math.PI / 180;
        var dl = (lon2 - lon1) * Math.PI / 180;
        var a = Math.sin(df / 2) * Math.sin(df / 2) + Math.cos(f1) * Math.cos(f2) * Math.sin(dl / 2) * Math.sin(dl / 2);
        var c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return R * c;
    }

    var nameSuspectedIds = [];
    var nameWarningMessages = [];

    var distSuspectedIds = [];
    var distWarningMessages = [];

    var DUPLICATE_DIST_M = 15; // 15 meters

    // --- Fuzzy Matching Helpers ---
    function normalizeStr(s) {
        return (s || "").toLowerCase()
            .normalize("NFD").replace(/[\u0300-\u036f]/g, "") // Remove accents
            .replace(/đ/g, "d").replace(/Đ/g, "d")
            .replace(/[^a-z0-9\s]/g, " ") // Special chars to space
            .replace(/\s+/g, " ").trim();
    }

    function levenshteinDist(a, b) {
        if (a.length === 0) return b.length;
        if (b.length === 0) return a.length;
        var matrix = [];
        for (var i = 0; i <= b.length; i++) matrix[i] = [i];
        for (var j = 0; j <= a.length; j++) matrix[0][j] = j;
        for (var i = 1; i <= b.length; i++) {
            for (var j = 1; j <= a.length; j++) {
                if (b.charAt(i - 1) === a.charAt(j - 1)) {
                    matrix[i][j] = matrix[i - 1][j - 1];
                } else {
                    matrix[i][j] = Math.min(
                        matrix[i - 1][j - 1] + 1, // substitution
                        Math.min(matrix[i][j - 1] + 1, matrix[i - 1][j] + 1) // insert, delete
                    );
                }
            }
        }
        return matrix[b.length][a.length];
    }

    function getFuzzyScore(str1, str2) {
        var s1 = normalizeStr(str1);
        var s2 = normalizeStr(str2);
        if (s1 === s2) return 1.0;

        var words1 = s1.split(" ").filter(w => w.length > 0);
        var words2 = s2.split(" ").filter(w => w.length > 0);
        if (words1.length === 0 || words2.length === 0) return 0;

        function wordSim(w1, w2) {
            var dist = levenshteinDist(w1, w2);
            var maxL = Math.max(w1.length, w2.length);
            return maxL === 0 ? 1 : (1 - dist / maxL);
        }

        var score1 = 0;
        words1.forEach(function (w1) {
            var best = 0;
            words2.forEach(function (w2) {
                var sim = wordSim(w1, w2);
                if (sim > best) best = sim;
            });
            score1 += best;
        });
        score1 /= words1.length;

        var score2 = 0;
        words2.forEach(function (w2) {
            var best = 0;
            words1.forEach(function (w1) {
                var sim = wordSim(w2, w1);
                if (sim > best) best = sim;
            });
            score2 += best;
        });
        score2 /= words2.length;

        // Trọng số 70% thuộc về chuỗi có điểm cao hơn để châm chước lỗi vi phạm do dư/thiếu chữ.
        // Ví dụ: Nhập "Cafe" vào "Cafe Giao" không nên bị đánh rớt điểm quá thấp.
        var maxScore = Math.max(score1, score2);
        var minScore = Math.min(score1, score2);
        return (maxScore * 0.7) + (minScore * 0.3);
    }
    // --- End Fuzzy ---

    window.allExistingStores.forEach(function (s) {
        var sProp = s.properties || s;
        var sGeom = s.geometry || s;
        var sName = sProp.name || '';
        var sId = sProp.id || sProp.ID || s.id;

        // Match >= 80%
        var simScore = 0;
        if (val && sName) {
            simScore = getFuzzyScore(val, sName);
        }
        var isDuplicateName = simScore >= 0.80;

        if (isDuplicateName) {
            var cLng = s.lng; var cLat = s.lat;
            if (sGeom && sGeom.coordinates && sGeom.coordinates.length >= 2) {
                cLng = sGeom.coordinates[0]; cLat = sGeom.coordinates[1];
            } else if (sProp && sProp.lng) {
                cLng = sProp.lng; cLat = sProp.lat;
            }

            var isFarEnough = false;
            var isCloseEnough = false;

            if (currLat !== null && currLng !== null && cLat && cLng) {
                if (calcDist(currLat, currLng, cLat, cLng) < DUPLICATE_DIST_M) {
                    isCloseEnough = true;
                } else if (window.hasManuallyDraggedMarker) {
                    isFarEnough = true;
                }
            }

            if (!isFarEnough) {
                nameSuspectedIds.push(sId);
                if (nameWarningMessages.indexOf(sProp.name) === -1) {
                    nameWarningMessages.push(' - ' + sProp.name);
                }

                if (isCloseEnough) {
                    distSuspectedIds.push(sId);
                    if (distWarningMessages.indexOf(sProp.name) === -1) {
                        distWarningMessages.push(' - ' + sProp.name);
                    }
                }
            }
        }
    });

    // 1. Name Warning
    var nameWarningDiv = document.getElementById('name-warning-msg');

    if (!nameWarningDiv && nameInput) {
        nameWarningDiv = document.createElement('div');
        nameWarningDiv.id = 'name-warning-msg';
        nameWarningDiv.style.cssText = 'color: #856404; font-weight: bold; margin-top: 5px; font-size: 13px; display: none; background: #fff3cd; padding: 5px 10px; border-radius: 4px; border: 1px solid #ffeeba;';
        nameInput.parentNode.insertBefore(nameWarningDiv, nameInput.nextSibling);
    }

    if (nameWarningDiv) {
        if (nameSuspectedIds.length > 0) {
            nameWarningDiv.innerHTML = '⚠️ <b>Cảnh báo trùng TÊN:</b><br>' + nameWarningMessages.join('<br>');
            nameWarningDiv.style.display = 'block';
        } else {
            nameWarningDiv.style.display = 'none';
        }
    }

    // 2. Map (Location) Warning
    var mapWarningDiv = document.getElementById('map-warning-msg');
    var locInput = document.querySelector('#id_location');

    if (!mapWarningDiv && locInput) {
        mapWarningDiv = document.createElement('div');
        mapWarningDiv.id = 'map-warning-msg';
        mapWarningDiv.style.cssText = 'color: #856404; font-weight: bold; margin-bottom: 10px; font-size: 13px; display: none; background: #fff3cd; padding: 5px 10px; border-radius: 4px; border: 1px solid #ffeeba;';

        var mapContainer = null;
        if (window.globalLeafletMap) {
            mapContainer = window.globalLeafletMap.getContainer();
        }

        if (mapContainer && mapContainer.parentNode) {
            mapContainer.parentNode.insertBefore(mapWarningDiv, mapContainer);
        } else {
            locInput.parentNode.insertBefore(mapWarningDiv, locInput.nextSibling);
        }
    }

    if (mapWarningDiv) {
        if (distSuspectedIds.length > 0) {
            mapWarningDiv.innerHTML = '⚠️ <b>Phát hiện vị trí kéo cờ RẤT GẦN với cửa hàng đang bị trùng tên:</b><br>' + distWarningMessages.join('<br>');
            mapWarningDiv.style.display = 'block';
        } else {
            mapWarningDiv.style.display = 'none';
        }
    }

    var mapPingYellowIds = distSuspectedIds.length > 0 ? distSuspectedIds : nameSuspectedIds;
    window.hasDuplicateWarning = nameSuspectedIds.length > 0;

    if (window.existingStoresLayer) {
        var existingStoreIcon = L.icon({
            iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-grey.png',
            shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
            iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41]
        });
        var duplicateStoreIcon = L.icon({
            iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-yellow.png',
            shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
            iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41]
        });

        window.existingStoresLayer.eachLayer(function (layer) {
            var featureId = layer.feature.properties.id || layer.feature.properties.ID || layer.feature.id;
            if (nameSuspectedIds.indexOf(featureId) !== -1) {
                layer.setIcon(duplicateStoreIcon);
                // Also bump z-index and open popup
                layer.setZIndexOffset(1000);
            } else {
                layer.setIcon(existingStoreIcon);
                layer.setZIndexOffset(0);
            }
        });
    }
}

document.addEventListener('DOMContentLoaded', function () {
    // 1. Fetch stores early to ensure immediate name duplicate validation
    if (!window.allExistingStores) {
        fetch('/api/stores/')
            .then(function (res) { return res.json(); })
            .then(function (data) {
                window.allExistingStores = data.features ? data.features : (data.results ? data.results.features || data.results : data);
            })
            .catch(function (err) { console.error('Early fetch error:', err); });
    }

    // 2. Attach Name Input Listeners
    var nameInput = document.querySelector('#id_name');
    if (nameInput) {
        // Evaluate as user types AND when they click away
        ['input', 'blur'].forEach(function (evt) {
            nameInput.addEventListener(evt, function () {
                if (window.checkDuplicateStore) window.checkDuplicateStore();
            });
        });
    }

    // 3. Form Submit confirmation
    var form = document.getElementById('store_form');
    if (form) {
        form.addEventListener('submit', function (e) {
            if (window.hasDuplicateWarning) {
                var c = confirm("⚠️ Hệ thống nghi ngờ cửa hàng này bị TRÙNG LẶP (tên hoặc tọa độ) với một cửa hàng khác!\n\nBạn có CHẮC CHẮN muốn tiếp tục lưu?");
                if (!c) {
                    e.preventDefault();
                }
            }
        });
    }
});

// ============================================================
// 3. IMAGE PREVIEW ON UPLOAD
// ============================================================
function initAdminImagePreview() {
    var imageInput = document.querySelector('#id_quick_image')
        || document.querySelector('input[name="quick_image"]');
    var idsInput = document.querySelector('#id_uploaded_image_ids')
        || document.querySelector('input[name="uploaded_image_ids"]');
    var addressInput = document.querySelector('#id_address');

    if (!imageInput || imageInput._previewBound) return;
    imageInput._previewBound = true;

    var uploadedIds = [];
    var totalCards = 0;
    var previewGrid = null;

    // ---- Create preview grid ABOVE the tabs / fieldsets ----
    function ensurePreviewGrid() {
        if (previewGrid) {
            var existingWrapper = document.getElementById('admin-preview-wrapper');
            if (existingWrapper) existingWrapper.style.display = 'block';
            return previewGrid;
        }

        var wrapper = document.createElement('div');
        wrapper.id = 'admin-preview-wrapper';
        wrapper.style.cssText = [
            'margin: 0 0 18px 0;',
            'padding: 14px 16px;',
            'background: #f0f4ff;',
            'border: 1px solid #c2cfe0;',
            'border-radius: 10px;',
            'width: 100%;',
            'box-sizing: border-box;'
        ].join('');

        var titleContainer = document.createElement('div');
        titleContainer.style.cssText = 'display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;';

        var title = document.createElement('p');
        title.style.cssText = 'font-weight:700;font-size:14px;color:#1f2d3d;margin:0;';
        title.textContent = '\uD83D\uDDBC\uFE0F Uploaded Images:';
        titleContainer.appendChild(title);

        var clearBtn = document.createElement('button');
        clearBtn.type = 'button';
        clearBtn.innerHTML = '<i class="fas fa-trash"></i> Xóa tất cả ảnh đã chọn';
        clearBtn.style.cssText = 'background:#dc3545; color:white; border:none; padding:4px 10px; border-radius:4px; font-size:12px; cursor:pointer;';
        clearBtn.addEventListener('click', function () {
            var imageInput = document.querySelector('#id_quick_image') || document.querySelector('input[name="quick_image"]');
            if (imageInput) imageInput.value = '';
            if (previewGrid) previewGrid.innerHTML = '';
            totalCards = 0;
            wrapper.style.display = 'none';
        });
        titleContainer.appendChild(clearBtn);

        wrapper.appendChild(titleContainer);

        previewGrid = document.createElement('div');
        previewGrid.style.cssText = 'display:flex;flex-wrap:wrap;gap:12px;';
        wrapper.appendChild(previewGrid);

        // Insert ABOVE all tabs / fieldsets — anchor to #content-main or closest form
        var anchor = document.querySelector('#content-main')
            || document.querySelector('.content-main')
            || document.querySelector('.change-form')
            || imageInput.closest('form');

        if (anchor) {
            // Prepend so it sits at the very top of the content area
            anchor.insertBefore(wrapper, anchor.firstChild);
        } else {
            // Fallback: insert after the fieldset that contains the input
            var fieldset = imageInput.closest('fieldset') || imageInput.parentNode;
            fieldset.parentNode.insertBefore(wrapper, fieldset.nextSibling);
        }

        return previewGrid;
    }

    // ---- Add thumbnail card ----
    function addCard(file, cardIndex) {
        var grid = ensurePreviewGrid();

        var card = document.createElement('div');
        card.style.cssText = 'position:relative;width:140px;text-align:center;background:white;border:1px solid #c2cfe0;border-radius:8px;padding:8px;box-shadow:0 2px 6px rgba(0,0,0,.12);';

        var removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.innerHTML = '&times;';
        removeBtn.style.cssText = 'position:absolute;top:-8px;right:-8px;width:24px;height:24px;border-radius:50%;background:#dc3545;color:white;border:none;font-weight:bold;font-size:16px;cursor:pointer;line-height:22px;padding:0;z-index:10;box-shadow:0 2px 4px rgba(0,0,0,0.3);';
        removeBtn.title = 'Xóa ảnh này khỏi danh sách tải lên';
        removeBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            var imageInput = document.querySelector('#id_quick_image') || document.querySelector('input[name="quick_image"]');
            if (imageInput && imageInput.files && window.DataTransfer) {
                var dt = new DataTransfer();
                var currentFiles = Array.from(imageInput.files);
                for (var i = 0; i < currentFiles.length; i++) {
                    // Giữ lại các file không trùng với file đang bấm xóa
                    // (So sánh qua reference)
                    if (currentFiles[i] !== file && currentFiles[i].name !== file.name) {
                        dt.items.add(currentFiles[i]);
                    }
                }
                imageInput.files = dt.files;
            }
            card.remove();
            
            if (grid.children.length === 0) {
                var wrapper = document.getElementById('admin-preview-wrapper');
                if (wrapper) wrapper.style.display = 'none';
                if (imageInput) imageInput.value = '';
            }
        });
        card.appendChild(removeBtn);

        var img = document.createElement('img');
        img.style.cssText = 'width:124px;height:124px;object-fit:cover;border-radius:6px;display:block;cursor:zoom-in;';
        img.title = 'Click to enlarge';
        img.addEventListener('click', function () { openLightbox(img.src); });

        var reader = new FileReader();
        reader.onload = function (ev) { img.src = ev.target.result; };
        reader.readAsDataURL(file);
        card.appendChild(img);

        var nameTxt = document.createElement('p');
        nameTxt.style.cssText = 'font-size:10px;color:#666;margin:5px 0 4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
        nameTxt.textContent = file.name;
        nameTxt.title = file.name;
        card.appendChild(nameTxt);

        var badge = document.createElement('span');
        badge.setAttribute('data-badge', cardIndex);
        badge.style.cssText = 'font-size:10px;padding:2px 7px;border-radius:10px;display:inline-block;background:#ffc107;color:#212529;';
        badge.textContent = 'Uploading...';
        card.appendChild(badge);

        grid.appendChild(card);
    }

    function setBadge(cardIndex, success) {
        if (!previewGrid) return;
        var badge = previewGrid.querySelector('[data-badge="' + cardIndex + '"]');
        if (!badge) return;
        if (success) {
            badge.style.background = '#28a745';
            badge.style.color = 'white';
            badge.textContent = 'Uploaded';
        } else {
            badge.style.background = '#dc3545';
            badge.style.color = 'white';
            badge.textContent = 'Upload failed';
        }
    }

    // ---- Lightbox ----
    function openLightbox(src) {
        var overlay = document.getElementById('admin-img-lb');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'admin-img-lb';
            overlay.style.cssText = 'position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.88);display:flex;align-items:center;justify-content:center;cursor:zoom-out;';
            overlay.addEventListener('click', function () { overlay.style.display = 'none'; });

            var lbImg = document.createElement('img');
            lbImg.id = 'admin-lb-img';
            lbImg.style.cssText = 'max-width:90vw;max-height:90vh;object-fit:contain;border-radius:8px;';
            lbImg.addEventListener('click', function (e) { e.stopPropagation(); });
            overlay.appendChild(lbImg);

            var closeBtn = document.createElement('button');
            closeBtn.textContent = '\u00D7';
            closeBtn.style.cssText = 'position:absolute;top:20px;right:20px;background:rgba(255,255,255,.2);border:none;border-radius:50%;width:40px;height:40px;color:white;font-size:22px;cursor:pointer;';
            closeBtn.addEventListener('click', function () { overlay.style.display = 'none'; });
            overlay.appendChild(closeBtn);

            document.body.appendChild(overlay);
        }
        document.getElementById('admin-lb-img').src = src;
        overlay.style.display = 'flex';
    }

    // ---- File selection event ----
    imageInput.addEventListener('change', function (e) {
        var files = Array.from(e.target.files);
        if (!files.length) {
            if (previewGrid) previewGrid.innerHTML = '';
            totalCards = 0;
            var wrapper = document.getElementById('admin-preview-wrapper');
            if (wrapper) wrapper.style.display = 'none';
            return;
        }

        // Mỗi lần chọn mới (browse file lại), input sẽ ghi đè các file cũ
        // nên ta cần reset giao diện để phản ánh chính xác mảng files được chọn.
        if (previewGrid) previewGrid.innerHTML = '';
        totalCards = 0;
        
        var wrapperObj = document.getElementById('admin-preview-wrapper');
        if (wrapperObj) wrapperObj.style.display = 'block';

        files.forEach(function (file, idx) {
            var cardIndex = totalCards++;
            addCard(file, cardIndex);

            // Only analyze the FIRST file for ML + GPS to save resources
            if (idx === 0) {
                uploadOne(file, true, cardIndex);
            } else {
                // Just mark it as "Queued" or "Ready"
                var badge = previewGrid.querySelector('[data-badge="' + cardIndex + '"]');
                if (badge) {
                    badge.style.background = '#17a2b8';
                    badge.style.color = 'white';
                    badge.textContent = 'Pending Save';
                }
            }
        });

        // Bỏ việc clear input, giữ file để browser POST cùng form khi nhấn Lưu cửa hàng
        // imageInput.value = '';
    });

    // ---- Upload temp for Analysis (Step 1: detect signs) ----
    function uploadOne(file, isFirst, cardIndex) {
        var fd = new FormData();
        fd.append('image', file);

        var badge = previewGrid ? previewGrid.querySelector('[data-badge="' + cardIndex + '"]') : null;
        if (badge) {
            badge.style.background = '#ffc107';
            badge.style.color = '#333';
            badge.textContent = 'Đang phân tích...';
        }

        fetch('/api/utils/quick-upload/', {
            method: 'POST',
            body: fd,
            headers: { 'X-CSRFToken': getCookie('csrftoken') }
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (badge) {
                badge.style.background = '#28a745';
                badge.style.color = 'white';
                badge.textContent = 'Analyzed & Pending';
            }

            // ── Nhiều biển hiệu? Mở dialog chọn ─────────────────────────────
            if (data.multiple_signs && data.signs && data.signs.length > 1) {
                showSignSelectionDialog(data.signs, data.tmp_path, data.gps, cardIndex, isFirst);
                return;
            }

            // ── Chỉ 1 biển hiệu: điền ngay ──────────────────────────────────
            if (isFirst) {
                applyOcrData(data, cardIndex);
            }
        })
        .catch(function (err) {
            console.error('Upload error:', err);
            if (badge) {
                badge.style.background = '#dc3545';
                badge.style.color = 'white';
                badge.textContent = 'Upload failed';
            }
        });
    }

    // ---- Hiển thị dialog chọn biển hiệu --------------------------------
    function showSignSelectionDialog(signs, tmpPath, gps, cardIndex, isFirst) {
        // Lưu dữ liệu vào global (cho nút "Đổi biển hiệu" dùng lại)
        window._signData.signs     = signs;
        window._signData.tmpPath   = tmpPath;
        window._signData.gps       = gps;
        window._signData.cardIndex = cardIndex;
        window._signData.isFirst   = isFirst;

        // Xóa dialog cũ nếu có
        var existDlg = document.getElementById('sign-select-dialog');
        if (existDlg) existDlg.remove();

        var curIdx = window._signData.currentIdx; // biển đang dùng (null nếu chưa chọn lần nào)

        var overlay = document.createElement('div');
        overlay.id = 'sign-select-dialog';
        overlay.style.cssText = [
            'position:fixed;inset:0;z-index:100000;',
            'background:rgba(0,0,0,0.7);',
            'display:flex;align-items:center;justify-content:center;',
        ].join('');

        var dialog = document.createElement('div');
        dialog.style.cssText = [
            'background:#fff;border-radius:12px;padding:24px;',
            'max-width:680px;width:95%;max-height:90vh;overflow-y:auto;',
            'box-shadow:0 20px 60px rgba(0,0,0,0.4);',
        ].join('');

        // Header
        var header = document.createElement('div');
        header.style.cssText = 'display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;';
        var title = document.createElement('h3');
        title.style.cssText = 'margin:0;font-size:16px;color:#1f2d3d;';
        var headerVerb = curIdx !== null ? 'Đổi lựa chọn' : 'Chọn biển hiệu cần trích xuất';
        title.innerHTML = '🏪 Tìm thấy <b style="color:#e74c3c;">' + signs.length + '</b> biển hiệu &mdash; ' + headerVerb + ':';
        var closeBtn = document.createElement('button');
        closeBtn.textContent = '✕';
        closeBtn.style.cssText = 'background:none;border:none;font-size:20px;cursor:pointer;color:#999;';
        closeBtn.onclick = function() { overlay.remove(); };
        header.appendChild(title);
        header.appendChild(closeBtn);
        dialog.appendChild(header);

        // Sign cards
        var grid = document.createElement('div');
        grid.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;margin-bottom:20px;';

        // Default: chọn biển đang dùng (nếu có), hoặc biển đầu tiên
        var selectedIndex = curIdx !== null ? curIdx : signs[0].index;
        var cards = [];

        signs.forEach(function(sign, i) {
            var isCurrent = sign.index === curIdx;
            var isSelected = sign.index === selectedIndex;

            var card = document.createElement('div');
            card.style.cssText = [
                'border:3px solid ' + (isSelected ? '#3498db' : '#ddd') + ';',
                'border-radius:10px;padding:10px;cursor:pointer;',
                'text-align:center;transition:all 0.2s;background:' + (isSelected ? '#ebf5fb' : '#f9f9f9') + ';',
                'position:relative;'
            ].join('');
            card.dataset.signIndex = sign.index;

            // Badge "✔ Đang dùng"
            if (isCurrent) {
                var currentBadge = document.createElement('div');
                currentBadge.style.cssText = [
                    'position:absolute;top:-9px;left:50%;transform:translateX(-50%);',
                    'background:#8e44ad;color:white;font-size:10px;font-weight:700;',
                    'padding:2px 8px;border-radius:10px;white-space:nowrap;z-index:1;'
                ].join('');
                currentBadge.textContent = '✔ Đang dùng';
                card.appendChild(currentBadge);
            }

            var img = document.createElement('img');
            img.src = sign.preview;
            img.style.cssText = 'width:100%;height:120px;object-fit:contain;border-radius:6px;display:block;margin-bottom:8px;background:#eee;';
            card.appendChild(img);

            var confTag = document.createElement('div');
            confTag.style.cssText = [
                'display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:700;',
                'background:' + (sign.conf >= 0.85 ? '#27ae60' : sign.conf >= 0.70 ? '#f39c12' : '#e74c3c') + ';',
                'color:white;margin-bottom:4px;',
            ].join('');
            confTag.textContent = 'Biển ' + (i + 1) + ': ' + sign.conf_pct;
            card.appendChild(confTag);

            card.onclick = function() {
                selectedIndex = sign.index;
                cards.forEach(function(c, ci) {
                    c.style.borderColor = ci === i ? '#3498db' : '#ddd';
                    c.style.background  = ci === i ? '#ebf5fb' : '#f9f9f9';
                });
                updateConfirmBtn();
            };

            cards.push(card);
            grid.appendChild(card);
        });

        dialog.appendChild(grid);

        // Confirm button
        var confirmBtn = document.createElement('button');
        confirmBtn.style.cssText = [
            'width:100%;padding:12px;color:white;',
            'border:none;border-radius:8px;font-size:14px;font-weight:700;',
            'cursor:pointer;transition:background 0.2s;',
        ].join('');

        function updateConfirmBtn() {
            var isSame = selectedIndex === curIdx;
            confirmBtn.textContent = isSame ? '⚠️ Vui lòng chọn biển hiệu khác' : '✅ Xác nhận đổi sang biển hiệu này';
            confirmBtn.disabled = isSame;
            confirmBtn.style.background = isSame ? '#bdc3c7' : '#2980b9';
            confirmBtn.style.cursor = isSame ? 'not-allowed' : 'pointer';
        }
        updateConfirmBtn();

        confirmBtn.onmouseover = function() {
            if (!confirmBtn.disabled) confirmBtn.style.background = '#1a6fa8';
        };
        confirmBtn.onmouseout = function() {
            if (!confirmBtn.disabled) confirmBtn.style.background = '#2980b9';
        };
        confirmBtn.onclick = function() {
            if (confirmBtn.disabled) return;
            overlay.remove();
            analyzeSelectedSign(window._signData.tmpPath, selectedIndex, gps, cardIndex, isFirst);
        };
        dialog.appendChild(confirmBtn);

        overlay.appendChild(dialog);
        document.body.appendChild(overlay);
    }

    // ---- Gọi bước 2: phân tích biển hiệu đã chọn ----------------------
    function analyzeSelectedSign(tmpPath, boxIndex, gps, cardIndex, isFirst) {
        var badge = previewGrid ? previewGrid.querySelector('[data-badge="' + cardIndex + '"]') : null;
        if (badge) {
            badge.style.background = '#ffc107';
            badge.style.color = '#333';
            badge.textContent = 'Đang trích xuất...';
        }

        fetch('/api/utils/analyze-sign/', {
            method: 'POST',
            body: JSON.stringify({ tmp_path: tmpPath, box_index: boxIndex }),
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            }
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (badge) {
                badge.style.background = '#28a745';
                badge.style.color = 'white';
                badge.textContent = 'Analyzed & Pending';
            }
            // Gộp thêm GPS đã có
            if (gps) {
                if (!data.latitude   && gps.latitude)    data.latitude    = gps.latitude;
                if (!data.longitude  && gps.longitude)   data.longitude   = gps.longitude;
                if (!data.address_gps && gps.address_gps) data.address_gps = gps.address_gps;
            }
            // Cập nhật tmp_path mới nhất từ server (server giữ lại để đổi biển hiệu)
            if (data.tmp_path) window._signData.tmpPath = data.tmp_path;
            window._signData.currentIdx = boxIndex;

            if (isFirst) applyOcrData(data, cardIndex);
        })
        .catch(function(err) {
            console.error('Analyze sign error:', err);
            if (badge) {
                badge.style.background = '#dc3545';
                badge.style.color = 'white';
                badge.textContent = 'Thất bại';
            }
        });
    }

    // ---- Áp dụng dữ liệu OCR vào form ----------------------------------
    function applyOcrData(data, cardIndex) {
        var ci = data.contact_info || {};

        // 1. CẬP NHẬT VỊ TRÍ BẢN ĐỒ (không tự động điền địa chỉ ở đây)
        if (data.latitude && data.longitude) {
            window.updateLocationInput(data.latitude, data.longitude);
            window.updateMapMarker(data.latitude, data.longitude);
        }

        // 2. DANH MỤC — tự động chọn nếu ô còn trống
        if (data.category_id) {
            var catSelect = document.querySelector('#id_category');
            if (catSelect && !catSelect.value) {
                catSelect.value = data.category_id;
                if (window.jQuery && window.jQuery(catSelect).data('select2')) {
                    window.jQuery(catSelect).trigger('change');
                }
            }
        }

        // 3. TỰ ĐỘNG ĐIỀN CÁC Ô — chỉ điền khi ô còn trống
        // 3a. Tên cửa hàng ← BRAND
        var nameFilled = autoFillInput('#id_name', ci.brand ? ci.brand[0] : null);
        addSuggestions('#id_name', ci.brand); // Thêm gợi ý nếu có nhiều thương hiệu

        // Kích hoạt ngay cảnh báo trùng tên (thay vì chờ user click/blur)
        if (nameFilled && window.checkDuplicateStore) {
            // Đợi stores tải xong trước (nếu chưa tải thì thử lại)
            var _dupRetry = 0;
            var _tryDupCheck = function() {
                if (window.allExistingStores) {
                    window.checkDuplicateStore();
                } else if (_dupRetry++ < 10) {
                    setTimeout(_tryDupCheck, 300); // thử lại sau 300ms
                }
            };
            setTimeout(_tryDupCheck, 150);
        }

        // 3b. Điện thoại ← PHONE
        autoFillInput('#id_phone', ci.phone ? ci.phone[0] : null);
        addSuggestions('#id_phone', ci.phone);

        // 3c. Email ← EMAIL
        autoFillInput('#id_email', ci.email ? ci.email[0] : null);
        addSuggestions('#id_email', ci.email);

        // 3d. Địa chỉ — ưu tiên: Địa chỉ trên biển hiệu > Địa chỉ GPS
        if (ci.address && ci.address.length > 0) {
            // Biển hiệu có địa chỉ → điền thẳng vào ô
            autoFillInput('#id_address', ci.address[0]);
            addSuggestions('#id_address', ci.address);
        } else if (data.address_gps) {
            // Không có địa chỉ trên biển → suy luận từ GPS
            autoFillInput('#id_address', data.address_gps);
        }

        // 3e. Mô tả ← SERVICE (loại hình kinh doanh)
        autoFillInput('#id_describe', ci.service ? ci.service[0] : null);
        addSuggestions('#id_describe', ci.service);

        // 3f. Thông tin phụ (O — slogan, chứng chỉ...) → gợi ý cho cả tên lẫn mô tả
        if (ci.other && ci.other.length) {
            addSuggestions('#id_name',     filterForName(ci.other, ci));   // đã lọc phone/address
            addSuggestions('#id_describe', ci.other);                       // mô tả: hiển thị tất cả
        }

        // 3g. Raw texts → gợi ý cho tên (lọc) và mô tả (không lọc)
        addSuggestions('#id_name',     filterForName(data.raw_texts || [], ci));
        addSuggestions('#id_describe', data.raw_texts);

        // 4. Chip biển hiệu đang dùng + nút đổi
        renderActiveSignChip();

        if (data.latitude || data.category_id || (ci.brand && ci.brand.length)) {
            alert('✅ Phân tích ảnh hoàn tất!\nCác ô đã được tự động điền. Kiểm tra và chỉnh sửa nếu cần.');
        }
    }

    // ---- Tự động điền vào ô input nếu còn trống — trả về true nếu đã điền ----
    function autoFillInput(inputId, value) {
        if (!value) return false;
        var input = document.querySelector(inputId);
        if (input && !input.value.trim()) {
            input.value = value;
            return true;   // đã điền
        }
        return false;      // không điền (ô đã có giá trị hoặc không tìm thấy)
    }

    // ---- Lọc phone/address khỏi danh sách gợi ý cho ô Tên ----------
    var _PHONE_RE_ADM   = /^[\d\s.\-+()ः]{7,}$|^0\d{8,9}$|^\+84\d{8,9}$/;
    var _ADDRESS_RE_ADM = /\d+\/\d*|(nguyễn|trần|lê|võ|phạm|hoàng|huỳnh|đinh|phan)|(^đường|phường|quận|xã|huyện|tp\.|thành phố|tỉnh|khu |nối dài|ấp |thị trấn)/i;

    function isPhoneOrAddressAdmin(text) {
        if (!text) return false;
        var t = text.trim();
        if (_PHONE_RE_ADM.test(t))   return true;
        if (_ADDRESS_RE_ADM.test(t)) return true;
        return false;
    }

    function filterForName(arr, ci) {
        var knownPhones   = (ci.phone   || []).concat(ci.address || []);
        return (arr || []).filter(function(v) {
            if (!v) return false;
            if (knownPhones.indexOf(v) !== -1) return false;  // trùng với phone/address đã biết
            if (isPhoneOrAddressAdmin(v))       return false;  // trông như phone hoặc địa chỉ
            return true;
        });
    }

    // ---- Render chip "Biển hiệu đang dùng" + nút Đổi ------------------
    function renderActiveSignChip() {
        var signs = window._signData.signs;
        var curIdx = window._signData.currentIdx;
        if (!signs || signs.length <= 1 || curIdx === null) return;

        var activeSgn = null;
        for (var k = 0; k < signs.length; k++) {
            if (signs[k].index === curIdx) { activeSgn = signs[k]; break; }
        }
        if (!activeSgn) return;

        // Xóa chip cũ nếu có
        var old = document.getElementById('active-sign-chip');
        if (old) old.remove();

        var confColor = activeSgn.conf >= 0.85 ? '#27ae60' : activeSgn.conf >= 0.70 ? '#f39c12' : '#e74c3c';

        var chip = document.createElement('div');
        chip.id = 'active-sign-chip';
        chip.style.cssText = [
            'display:flex;align-items:center;gap:10px;',
            'background:linear-gradient(135deg,#f0f9ff,#e0f2fe);',
            'border:1.5px solid #7dd3fc;border-radius:10px;',
            'padding:10px 14px;margin-bottom:12px;'
        ].join('');

        // Thumbnail
        var img = document.createElement('img');
        img.src = activeSgn.preview;
        img.style.cssText = 'width:52px;height:40px;object-fit:contain;border-radius:6px;border:1px solid #bae6fd;background:#f0f9ff;flex-shrink:0;';
        chip.appendChild(img);

        // Info
        var info = document.createElement('div');
        info.style.cssText = 'flex:1;min-width:0;';
        var lbl = document.createElement('div');
        lbl.style.cssText = 'font-size:11px;color:#0369a1;font-weight:600;margin-bottom:3px;';
        lbl.textContent = '📌 Biển hiệu đang được trích xuất';
        var badge = document.createElement('span');
        badge.style.cssText = 'display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700;background:' + confColor + ';color:white;';
        badge.textContent = 'Biển ' + (activeSgn.index + 1) + ' — Độ tin cậy: ' + activeSgn.conf_pct;
        var subLbl = document.createElement('span');
        subLbl.style.cssText = 'font-size:11px;color:#64748b;margin-left:6px;';
        subLbl.textContent = '/ ' + signs.length + ' biển';
        info.appendChild(lbl);
        info.appendChild(badge);
        info.appendChild(subLbl);
        chip.appendChild(info);

        // Nút đổi
        var changeBtn = document.createElement('button');
        changeBtn.type = 'button';
        changeBtn.textContent = '🔄 Đổi biển hiệu';
        changeBtn.style.cssText = [
            'background:#0284c7;color:white;border:none;border-radius:8px;',
            'padding:8px 14px;font-size:12px;font-weight:700;',
            'cursor:pointer;white-space:nowrap;flex-shrink:0;transition:background 0.2s;'
        ].join('');
        changeBtn.onmouseover = function() { changeBtn.style.background = '#0369a1'; };
        changeBtn.onmouseout  = function() { changeBtn.style.background = '#0284c7'; };
        changeBtn.onclick = function() {
            var sd = window._signData;
            if (sd.signs && sd.tmpPath) {
                showSignSelectionDialog(sd.signs, sd.tmpPath, sd.gps, sd.cardIndex, sd.isFirst);
            }
        };
        chip.appendChild(changeBtn);

        // Chèn chip vào trên phần preview grid (hay vào đầu #content-main)
        var wrapper = document.getElementById('admin-preview-wrapper');
        if (wrapper && wrapper.parentNode) {
            wrapper.parentNode.insertBefore(chip, wrapper);
        } else {
            var anchor = document.querySelector('#content-main') || document.querySelector('.change-form');
            if (anchor) anchor.insertBefore(chip, anchor.firstChild);
        }
    }

    // ---- Helper to add visible suggestion tags below input fields ----
    function addSuggestions(inputId, suggestionsArray, autoFillFirst) {
        if (!suggestionsArray || suggestionsArray.length === 0) return;
        var input = document.querySelector(inputId);
        if (!input) return;

        // Auto fill if the input is completely empty and autoFillFirst is true
        if (autoFillFirst && !input.value && suggestionsArray[0]) {
            input.value = suggestionsArray[0];
        }

        // Create or find container for tags
        var containerId = input.id + "_suggestions";
        var container = document.getElementById(containerId);
        if (!container) {
            container = document.createElement('div');
            container.id = containerId;
            container.style.cssText = 'display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px;';

            var label = document.createElement('span');
            label.textContent = "✨ Gợi ý ML:";
            label.style.cssText = 'font-size: 11px; color: #666; font-style: italic; align-self: center; margin-right: 4px;';
            container.appendChild(label);

            // Insert right after the input element
            input.parentNode.insertBefore(container, input.nextSibling);
        }

        // Keep track of existing suggestions to avoid duplicates
        var existingTags = Array.from(container.querySelectorAll('.ml-sugg-btn')).map(function (btn) {
            return btn.textContent;
        });

        suggestionsArray.forEach(function (text) {
            if (text && existingTags.indexOf(text) === -1) {
                var btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'ml-sugg-btn';
                btn.textContent = text;
                btn.style.cssText = 'background: #e3f2fd; border: 1px solid #90caf9; color: #1565c0; border-radius: 4px; padding: 2px 8px; font-size: 11px; cursor: pointer; transition: 0.2s;';

                btn.onmouseover = function () { btn.style.background = '#bbdefb'; };
                btn.onmouseout = function () { btn.style.background = '#e3f2fd'; };

                // Clicking the suggestion adds the text to the input
                btn.onclick = function (e) {
                    e.preventDefault();
                    if (input.value) {
                        input.value = input.value.trim() + ' ' + text;
                    } else {
                        input.value = text;
                    }
                    input.focus();
                };

                container.appendChild(btn);
                existingTags.push(text);
            }
        });
    }
}

// Run when DOM is ready — handle all cases
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAdminImagePreview);
} else {
    initAdminImagePreview();
}
// Fallback after 800ms for late-rendering widgets
setTimeout(initAdminImagePreview, 800);

// End of file