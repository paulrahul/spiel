/*********** Things to do with saving and showing basic stats ********/
let stats = {
    num_questions: 0,
    start_time: Date.now(),

    historical_num_questions: 0
};

function updateStats(num_questions) {
    stats.num_questions = num_questions;
    displayStats();
}

function incrementStats() {
    updateStats(stats.num_questions + 1);
}

function displayStats() {
    document.getElementById("num_questions").textContent = `${stats.num_questions} questions attempted`
}

function resetStats() {
    updateStats(0);

    if (stats.start_time == null) {
        stats.start_time = Date.now();
    }    
}
/*********** Things to do with saving and showing basic stats ********/

// Define your map data structure
let basicScores = new Map();

// Function to save data to localStorage
function saveDataToLocalStorage() {
    localStorage.setItem('basicScores',
        JSON.stringify(Array.from(basicScores.entries())));

    localStorage.setItem('stats', JSON.stringify(stats));
      
    console.log('Data saved to localStorage.');
}

// Function to load data from localStorage
function loadDataFromLocalStorage() {
    let storedData = localStorage.getItem('basicScores');
    if (storedData) {
        basicScores = new Map(JSON.parse(storedData));
        console.log('Data loaded from localStorage.');
    }

    let storedStats = localStorage.getItem('stats');
    if (storedStats) {
        stats = JSON.parse(storedStats);
    }
}

function flushStats() {
    stats.historical_num_questions += stats.num_questions;
    
    stats.num_questions = 0;
    stats.start_time = null;
}

// Function to handle clicking of the "exit" link
function handleExitLinkClick() {
    // flushStats();
    saveDataToLocalStorage();
}

function handleNextLinkClick() {
    const radios = document.getElementsByName('order');
    let selectedValue;
    for (const radio of radios) {
        if (radio.checked) {
            selectedValue = radio.value;
            break;
        }
    }
    
    if (selectedValue != undefined && selectedValue == "serial") {
        localStorage.setItem('order', "serial");
        window.location.href = "/next_question?order=serial";
    } else {
        localStorage.setItem('order', "random");
        window.location.href = "/next_question";
    }
}

// Function to handle periodic saving of data
function periodicSaveData() {
    saveDataToLocalStorage();
}

// Attach event listener to the "exit" link
const exitLinks = document.querySelectorAll('.exit-link');
exitLinks.forEach(function(exitLink) {
    exitLink.addEventListener('click', handleExitLinkClick);
});

document.querySelectorAll('.next-link').forEach(function(nextLink) {
    nextLink.addEventListener('click', handleNextLinkClick);
});

// window.addEventListener('beforeunload', function (event) {
//     // Cancel the event
//     event.preventDefault();
    
//     // Chrome requires returnValue to be set
//     event.returnValue = '';

//     handleExitLinkClick();
// });

// Periodically save data every 2 minutes
setInterval(periodicSaveData, 2 * 60 * 1000); // 2 minutes in milliseconds

function updateWordScore(word, score) {
    if (basicScores.has(word)) {
        // If the key exists, retrieve the existing list and append the new value to it
        let existingList = basicScores.get(word);
        existingList.push(score);
        basicScores.set(word, existingList); // Update the value for the key in the map
    } else {
        // If the key doesn't exist, create a new list with the new value and set it as the value for the key
        basicScores.set(word, [score]);
    }

    incrementStats();
    saveDataToLocalStorage();
}
