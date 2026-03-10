/* static/js/admin_auto_gps.js */

// 1. GLOBAL VARIABLES
window.globalLeafletMap = null;
window.currentMarker = null;

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
                });
            }
        }
    });
}

window.updateMapMarker = function (lat, lng) {
    if (!window.globalLeafletMap) return;
    var latlng = [lat, lng];
    if (window.currentMarker) window.globalLeafletMap.removeLayer(window.currentMarker);
    window.globalLeafletMap.eachLayer(function (layer) {
        if (layer instanceof L.Marker) window.globalLeafletMap.removeLayer(layer);
    });
    window.currentMarker = L.marker(latlng, { draggable: true }).addTo(window.globalLeafletMap);
    window.currentMarker.on('dragend', function (event) {
        var position = event.target.getLatLng();
        window.updateLocationInput(position.lat, position.lng);
    });
    window.globalLeafletMap.flyTo(latlng, 16);
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
        if (previewGrid) return previewGrid;

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

        var title = document.createElement('p');
        title.style.cssText = 'font-weight:700;font-size:14px;color:#1f2d3d;margin-bottom:12px;';
        title.textContent = '\uD83D\uDDBC\uFE0F Uploaded Images:';
        wrapper.appendChild(title);

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
        card.style.cssText = 'width:140px;text-align:center;background:white;border:1px solid #c2cfe0;border-radius:8px;padding:8px;box-shadow:0 2px 6px rgba(0,0,0,.12);';

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
        if (!files.length) return;

        files.forEach(function (file, idx) {
            var cardIndex = totalCards++;
            addCard(file, cardIndex);
            uploadOne(file, idx === 0, cardIndex);
        });

        // Clear input to avoid re-submitting large files with the form
        imageInput.value = '';
    });

    // ---- Upload a single file ----
    function uploadOne(file, isFirst, cardIndex) {
        var fd = new FormData();
        fd.append('image', file);

        fetch('/api/utils/quick-upload/', {
            method: 'POST',
            body: fd,
            headers: { 'X-CSRFToken': getCookie('csrftoken') }
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.id) { setBadge(cardIndex, false); return; }
                uploadedIds.push(data.id);
                if (idsInput) idsInput.value = uploadedIds.join(',');
                setBadge(cardIndex, true);

                if (isFirst) {
                    if (data.latitude && data.longitude) {
                        if (addressInput && !addressInput.value) addressInput.value = data.address_gps || '';
                        if (!window.globalLeafletMap && window.id_location_map) {
                            window.globalLeafletMap = window.id_location_map;
                        }
                        window.updateLocationInput(data.latitude, data.longitude);
                        window.updateMapMarker(data.latitude, data.longitude);
                    }

                    // Automatically select category
                    if (data.category_id) {
                        var catSelect = document.querySelector('#id_category');
                        if (catSelect && !catSelect.value) {
                            catSelect.value = data.category_id;
                            if (window.jQuery && window.jQuery(catSelect).data('select2')) {
                                window.jQuery(catSelect).trigger('change');
                            }
                        }
                    }

                    // Supply extracted information as autocomplete suggestions (datalists)
                    if (data.contact_info) {
                        addSuggestions('#id_phone', data.contact_info.phone);
                        addSuggestions('#id_email', data.contact_info.email);
                        addSuggestions('#id_address', data.contact_info.address);
                    }
                    if (data.raw_texts) {
                        addSuggestions('#id_name', data.raw_texts);
                    }

                    if (data.latitude && data.longitude || data.category_id || data.raw_texts) {
                        alert('Image analyzed! Check the fields for automatically filled data and suggestions!');
                    }
                }
            })
            .catch(function (err) {
                console.error('Upload error:', err);
                setBadge(cardIndex, false);
            });
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