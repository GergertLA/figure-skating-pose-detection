function toggleAthletes(groupId) {
    const athletesDiv = document.getElementById('athletes-' + groupId);
    if (athletesDiv.style.display === 'none' || athletesDiv.style.display === '') {
        athletesDiv.style.display = 'table-row';
    } else {
        athletesDiv.style.display = 'none';
    }
}

function searchAthlete() {
    const searchTerm = document.getElementById('searchInput').value.toLowerCase();
    const athleteItems = document.querySelectorAll('.athlete-item');
    const groupHeaders = document.querySelectorAll('.group-header');
    const athletesTables = document.querySelectorAll('.athletes');

    groupHeaders.forEach(group => {
        group.style.display = 'none';
    });
    athletesTables.forEach(table => {
        table.style.display = 'none';
    });

    athleteItems.forEach(item => {
        const athleteName = item.querySelector('.athlete-name').textContent.toLowerCase();
        if (athleteName.includes(searchTerm)) {
            item.style.display = 'table-row';
            const groupRow = item.closest('.athletes');
            if (groupRow) {
                groupRow.style.display = 'table-row';
                const groupHeader = groupRow.previousElementSibling;
                if (groupHeader) {
                    groupHeader.style.display = 'table-row';
                }
            }
        } else {
            item.style.display = 'none';
        }
    });
}