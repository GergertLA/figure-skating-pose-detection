document.addEventListener('DOMContentLoaded', function() {
    let currentDate = new Date();
    const groupId = {{ group_id }};

    function updateWeekRange() {
        const startOfWeek = new Date(currentDate);
        startOfWeek.setDate(currentDate.getDate() - (currentDate.getDay() === 0 ? 6 : currentDate.getDay() - 1));

        const endOfWeek = new Date(startOfWeek);
        endOfWeek.setDate(startOfWeek.getDate() + 6);

        const options = { day: 'numeric', month: 'long' };
        document.getElementById('week-range').textContent =
            `${startOfWeek.toLocaleDateString('ru-RU', options)} - ${endOfWeek.toLocaleDateString('ru-RU', options)}`;

        return { start: startOfWeek, end: endOfWeek };
    }

    function formatDate(date) {
        return date.toISOString().split('T')[0];
    }

    function createCalendarStructure(startDate, endDate) {
        const calendar = document.getElementById('calendar');
        calendar.innerHTML = '';

        const timeHeader = document.createElement('div');
        timeHeader.className = 'time-header day-header';
        timeHeader.textContent = 'Время';
        calendar.appendChild(timeHeader);

        const currentDay = new Date(startDate);
        while (currentDay <= endDate) {
            const dayHeader = document.createElement('div');
            dayHeader.className = 'day-header';
            dayHeader.innerHTML = `
                <div>${currentDay.getDate()}</div>
                <div>${['Вс','Пн','Вт','Ср','Чт','Пт','Сб'][currentDay.getDay()]}</div>
            `;
            calendar.appendChild(dayHeader);
            currentDay.setDate(currentDay.getDate() + 1);
        }

        for (let hour = 7; hour <= 20; hour++) {
            const timeSlot = document.createElement('div');
            timeSlot.className = 'time-slot';
            timeSlot.textContent = `${hour}:00`;
            calendar.appendChild(timeSlot);

            for (let i = 0; i < 7; i++) {
                const dayColumn = document.createElement('div');
                dayColumn.className = 'day-column empty-cell';
                calendar.appendChild(dayColumn);
            }
        }
    }

    function renderWeek(days) {
        const calendar = document.getElementById('calendar');
        const dayColumns = calendar.querySelectorAll('.day-column');

        for (const [date, events] of Object.entries(days)) {
            const dayIndex = (new Date(date).getDay() + 6) % 7; // Пн=0, Вс=6
            const locationFilter = document.getElementById('location-filter').value;

            events.forEach(event => {
                if (locationFilter && event.location !== locationFilter) {
                    return;
                }

                const startHour = parseInt(event.start_time.split(':')[0]);
                const startMinute = parseInt(event.start_time.split(':')[1]);
                const endHour = parseInt(event.end_time.split(':')[0]);
                const endMinute = parseInt(event.end_time.split(':')[1]);

                const timeHeight = 100;
                const startOffset = (startHour - 7) * timeHeight + (startMinute / 60) * timeHeight;
                const eventHeight = ((endHour - startHour) * 60 + (endMinute - startMinute)) / 60 * timeHeight;

                const eventDiv = document.createElement('div');
                eventDiv.className = 'event';
                eventDiv.style.top = `${startOffset}px`;
                eventDiv.style.height = `${eventHeight}px`;
                eventDiv.classList.add(event.training_type);

                eventDiv.innerHTML = `
                    <div class="event-title">${event.training_type === 'group' ? 'Группа' : 'Индивидуально'}</div>
                    <div class="event-time">${event.start_time} - ${event.end_time}</div>
                    <div class="event-location">${event.location || 'Место не указано'}</div>
                    <div class="event-coach">${event.coach_name}</div>
                `;

                const index = (startHour - 7) * 7 + dayIndex;
                if (dayColumns[index]) {
                    dayColumns[index].appendChild(eventDiv);
                }
            });
        }
    }

    function loadWeekData() {
        const { start, end } = updateWeekRange();
        createCalendarStructure(start, end);

        fetch(`/group_schedule_data/${groupId}?start=${formatDate(start)}&end=${formatDate(end)}`)
            .then(response => response.json())
            .then(data => {
                renderWeek(data.days);
            });
    }

    document.getElementById('prev-week').addEventListener('click', () => {
        currentDate.setDate(currentDate.getDate() - 7);
        loadWeekData();
    });

    document.getElementById('next-week').addEventListener('click', () => {
        currentDate.setDate(currentDate.getDate() + 7);
        loadWeekData();
    });

    document.getElementById('location-filter').addEventListener('change', () => {
        loadWeekData();
    });

    loadWeekData();
});
