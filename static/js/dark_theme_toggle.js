// Function to toggle the dark theme
function toggleTheme() {
    const body = document.body;
    const currentTheme = body.classList.toggle('dark-theme');
    
    // Save the user's preference in localStorage
    localStorage.setItem('dark-theme', currentTheme ? 'enabled' : 'disabled');
}

// // Add event listener to the toggle button
// document.getElementById('theme-toggle').addEventListener('click', toggleTheme);

// Check the user's preference on page load
// window.onload = function() {
//     const darkThemeEnabled = localStorage.getItem('dark-theme') === 'enabled';
//     if (darkThemeEnabled) {
//         document.body.classList.add('dark-theme');
//     }
// };

document.getElementById('toggle').addEventListener('change', function() {
    toggleTheme();
});

var toggleElem = document.getElementById('toggle');
if (toggleElem != undefined) {
    const darkThemeEnabled = localStorage.getItem('dark-theme') === 'enabled';
    if (darkThemeEnabled) {
        document.body.classList.add('dark-theme');
        var checkbox = document.getElementById('toggle');
        checkbox.checked = true;
    }
}


