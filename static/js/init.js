function sessionInit(nextUrl) {
    let unaskedSet = ["word", "preposition"];
    localStorage.setItem("unasked", JSON.stringify(unaskedSet));

    let storedData = localStorage.getItem('basicScores');
    // let start = localStorage.getItem('last');
    // const combinedObj = { ...JSON.parse(storedData), ...JSON.parse(start)};
    // const postData = JSON.stringify(combinedObj);
    const postData = JSON.stringify(storedData);

    if (postData) {
        $.ajax({
            url: '/init',
            type: 'POST',
            contentType: 'application/json',
            data: postData,
            success: function(response, textStatus, jqXHR) {
                const sessionId = response.session_id;
                window.location.href = nextUrl + "&session_id=" + sessionId; 
            },
            error: function(xhr, status, error) {
                console.error('Error:', error);
            }
        });
    } else {
        console.log('No scores found in local storage.')
        window.location.href = 'play';
    }
}
