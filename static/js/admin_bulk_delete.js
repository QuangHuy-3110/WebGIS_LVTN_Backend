document.addEventListener('DOMContentLoaded', function () {
    var actionSelect = document.querySelector('select[name="action"]');
    var actionContainer = document.querySelector('.actions');

    if (actionSelect && actionContainer) {
        // Kiểm tra xem có action xóa mặc định hoặc tùy chỉnh không
        var targetAction = null;
        var hasDeleteAction = Array.from(actionSelect.options).some(function (o) {
            if (o.value === 'delete_selected_stores_with_images' || o.value === 'delete_selected') {
                targetAction = o.value;
                return true;
            }
            return false;
        });

        if (hasDeleteAction && targetAction) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'button btn btn-danger';
            btn.innerHTML = '<i class="fas fa-trash"></i> Xóa các mục đã chọn';
            btn.style.cssText = 'margin-left: 10px; background: #dc3545; color: white; border: none; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-weight: bold;';

            btn.addEventListener('click', function (e) {
                e.preventDefault();
                var checkboxes = document.querySelectorAll('input.action-select:checked');
                if (checkboxes.length === 0) {
                    alert('⚠️ Bạn chưa chọn mục nào để xóa!');
                    return;
                }
                var c = confirm('Bạn có chắc chắn muốn xóa ' + checkboxes.length + ' mục đã chọn không? Thao tác này không thể hoàn tác!');
                if (c) {
                    actionSelect.value = targetAction;
                    var form = document.querySelector('#changelist-form');
                    if (form) {
                        form.submit();
                    }
                }
            });

            actionContainer.appendChild(btn);
        }
    }
});
