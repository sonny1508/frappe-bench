document.addEventListener('DOMContentLoaded', function() {
    // Only run on login page
    if (!document.getElementById('page-login')) return;

    // Configuration
    const IMAGE_FOLDER = 'login_backgrounds'; // Folder name in File Manager
    const SLIDE_DURATION = 10000;
    const FADE_DURATION = 1500;   // 1.5 second fade (matches CSS transition)

    // Create slideshow container
    const slideshowContainer = document.createElement('div');
    slideshowContainer.className = 'login-slideshow';
    document.body.prepend(slideshowContainer);

    // Fetch images and start slideshow
    frappe.call({
        method: 'gs_customizations.api.get_login_backgrounds',
        args: { folder: IMAGE_FOLDER },
        async: true,
        callback: function(r) {
            if (r.message && r.message.length > 0) {
                initSlideshow(r.message);
            }
        }
    });

    function initSlideshow(images) {
        // Create slide elements
        images.forEach((src, index) => {
            const slide = document.createElement('div');
            slide.className = 'slide' + (index === 0 ? ' active' : '');
            slide.style.backgroundImage = `url('${src}')`;
            slideshowContainer.appendChild(slide);
        });

        // Don't animate if only one image
        if (images.length <= 1) return;

        let currentIndex = 0;
        const slides = slideshowContainer.querySelectorAll('.slide');

        setInterval(() => {
            const currentSlide = slides[currentIndex];
            currentIndex = (currentIndex + 1) % slides.length;
            const nextSlide = slides[currentIndex];

            currentSlide.classList.remove('active');
            nextSlide.classList.add('active');
        }, SLIDE_DURATION);
    }
});