// script.js
document.addEventListener("DOMContentLoaded", function () {
    const stateAreas = document.querySelectorAll('area[data-state]');
    const stateContentDiv = document.getElementById('stateContent');

    stateAreas.forEach(area => {
        area.addEventListener('click', function (event) {
            event.preventDefault();
            const stateName = this.getAttribute('data-state');
            loadStateContent(stateName);
        });
    });

    function loadStateContent(stateName) {
        // Assuming you have separate HTML files for each state (e.g., california.html)
        const stateContentURL = stateName + '.html';
        
        // You can use AJAX or fetch to load the content from the state-specific page
        fetch(stateContentURL)
            .then(response => response.text())
            .then(content => {
                stateContentDiv.innerHTML = content;
            })
            .catch(error => {
                console.error('Error loading state content:', error);
            });
    }
});

