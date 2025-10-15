document.addEventListener('DOMContentLoaded', function() {
    const calendarEl = document.getElementById('calendar');
    const uniqueDates = {{ unique_dates | tojson }};
    const elementsData = {{ elements | tojson }};

    let calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'dayGridMonth',
        locale: 'ru',
        dateClick: function(info) {
            fetch(`/athlete/{{ athlete_id }}/dates/${info.dateStr}`)
                .then(response => response.json())
                .then(data => {
                    const elementsList = document.getElementById('elements-list');
                    const noElementsMessage = document.getElementById('no-elements-message');
                    elementsList.innerHTML = '';

                    if (data.length === 0) {
                        noElementsMessage.style.display = 'block';
                    } else {
                        noElementsMessage.style.display = 'none';
                        data.forEach(element => {
                            const li = document.createElement('li');
                            li.className = 'element-header';
                            li.textContent = element.name;
                            li.onclick = () => toggleAttempts(element.id);
                            elementsList.appendChild(li);

                            const attemptsDiv = document.createElement('div');
                            attemptsDiv.id = `attempts-${element.id}`;
                            attemptsDiv.className = 'attempts';
                            attemptsDiv.innerHTML = `<ul>${element.attempts.map((attempt, index) => `
                                <li>
                                    <a class="video-link" href="/video_athlete/{{ athlete_id }}/${element.id}/${attempt.training_date}">
                                        Попытка №${index + 1}
                                    </a>
                                </li>
                            `).join('')}</ul>`;
                            li.appendChild(attemptsDiv);
                        });
                    }

                    document.getElementById('elements-container').style.display = 'block';
                })
                .catch(error => {
                    console.error('Ошибка при загрузке данных:', error);
                });
        },
        events: uniqueDates.map(date => ({
            start: date,
            display: 'background',
            color: '#90EE90'
        }))
    });
    calendar.render();

    const elementFilter = document.getElementById('element-filter');
    elementFilter.addEventListener('change', function() {
        const selectedElementId = this.value;
        calendar.removeAllEvents();

        if (selectedElementId === 'all') {
            calendar.addEventSource(uniqueDates.map(date => ({
                start: date,
                display: 'background',
                color: '#90EE90'
            })));
        } else {
            const element = elementsData[selectedElementId];
            const elementDates = element.attempts.map(attempt => attempt.training_date);

            calendar.addEventSource(elementDates.map(date => ({
                start: date,
                display: 'background',
                color: '#90EE90'
            })));
        }
    });
});

function toggleAttempts(elementId) {
    const attemptsDiv = document.getElementById('attempts-' + elementId);
    if (attemptsDiv.style.display === 'none' || attemptsDiv.style.display === '') {
        attemptsDiv.style.display = 'block';
    } else {
        attemptsDiv.style.display = 'none';
    }
}