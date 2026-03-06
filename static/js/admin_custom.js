document.addEventListener('DOMContentLoaded', function () {
    // Create the modal container
    const modal = document.createElement('div');
    modal.id = 'admin-image-modal-container';
    modal.style.display = 'none';
    modal.style.position = 'fixed';
    modal.style.zIndex = '9999';
    modal.style.paddingTop = '50px';
    modal.style.left = '0';
    modal.style.top = '0';
    modal.style.width = '100%';
    modal.style.height = '100%';
    modal.style.overflow = 'auto';
    modal.style.backgroundColor = 'rgba(0,0,0,0.85)';
    modal.style.cursor = 'zoom-out';
    modal.style.display = 'flex';
    modal.style.justifyContent = 'center';
    modal.style.alignItems = 'center';

    // Hide initially via a class or override display later
    modal.style.display = 'none';

    // Create the image element inside the modal
    const modalImg = document.createElement('img');
    modalImg.id = 'admin-image-modal-content';
    modalImg.style.margin = 'auto';
    modalImg.style.display = 'block';
    modalImg.style.maxWidth = '90%';
    modalImg.style.maxHeight = '90%';
    modalImg.style.borderRadius = '8px';
    modalImg.style.boxShadow = '0 4px 25px rgba(0,0,0,0.5)';

    // Close button (optional, since clicking anywhere closes)
    const closeBtn = document.createElement('span');
    closeBtn.innerHTML = '&times;';
    closeBtn.style.position = 'absolute';
    closeBtn.style.top = '15px';
    closeBtn.style.right = '35px';
    closeBtn.style.color = '#f1f1f1';
    closeBtn.style.fontSize = '40px';
    closeBtn.style.fontWeight = 'bold';
    closeBtn.style.cursor = 'pointer';

    modal.appendChild(closeBtn);
    modal.appendChild(modalImg);
    document.body.appendChild(modal);

    // Function to close modal
    const closeModal = function () {
        modal.style.display = 'none';
    };

    modal.onclick = closeModal;
    closeBtn.onclick = closeModal;

    // Attach click event to all links with class 'admin-image-modal'
    const imageLinks = document.querySelectorAll('a.admin-image-modal');
    imageLinks.forEach(function (link) {
        link.addEventListener('click', function (e) {
            e.preventDefault(); // Stop from opening new tab
            modalImg.src = this.href;
            modal.style.display = 'flex'; // Use flex to center the image
        });
    });
});
