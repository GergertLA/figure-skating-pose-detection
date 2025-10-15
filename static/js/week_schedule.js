document.addEventListener('DOMContentLoaded', () => {
    const calendar = document.getElementById('calendar');
    const weekRange = document.getElementById('week-range');
    let currentDate = new Date();

    function formatDate(date) {
        return date.toISOString().split('T')[0];
    }

    function renderWeek(startDate) {
        const endDate = new Date(startDate);
        endDate.setDate(startDate.getDate() + 6);

        const options = { day: 'numeric', month: 'short' };
        weekRange.textContent = `${startDate.toLocaleDateString('ru-RU', options)} - ${endDate.toLocaleDateString('ru-RU', options)}`;

        calendar.innerHTML = '';

        // Заголовки дней
        const daysRow = document.createElement('div');
        daysRow.className = 'd-flex border-bottom bg-light fw-bold';
        for (let i = 0; i < 7; i++) {
            const day = new Date(startDate);
            day.setDate(day.getDate() + i);
            const col = document.createElement('div');
            col.className = 'flex-fill text-center p-2 border-end';
            col.textContent = day.toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric' });
            daysRow.appendChild(col);
        }
        calendar.appendChild(daysRow);

        // Часы с 7 до 20
        for (let hour = 7; hour <= 20; hour++) {
            const row = document.createElement('div');
            row.className = 'd-flex border-bottom';
            for (let i = 0; i < 7; i++) {
                const cell = document.createElement('div');
                cell.className = 'flex-fill p-2 border-end';
                const date = new Date(startDate);
                date.setDate(date.getDate() + i);
                const dateStr = formatDate(date);

                const events = (groupDays[dateStr] || []).filter(ev => parseInt(ev.start_time.split(':')[0]) === hour);
                for (const ev of events) {
                    const div = document.createElement('div');
                    div.className = 'border rounded bg-white mb-1 p-1 small';
                    div.innerHTML = `
                        <strong>${ev.start_time}–${ev.end_time}</strong><br>
                        ${ev.coach}<br>
                        <em>${ev.location}</em>
                    `;
                    cell.appendChild(div);
                }

                row.appendChild(cell);
            }
            calendar.appendChild(row);
        }
    }

    function getWeekStart(date) {
        const d = new Date(date);
        const day = d.getDay() || 7;
        d.setDate(d.getDate() - day + 1);
        return new Date(d.getFullYear(), d.getMonth(), d.getDate());
    }

    document.getElementById('prev-week').addEventListener('click', () => {
        currentDate.setDate(currentDate.getDate() - 7);
        renderWeek(getWeekStart(currentDate));
    });

    document.getElementById('next-week').addEventListener('click', () => {
        currentDate.setDate(currentDate.getDate() + 7);
        renderWeek(getWeekStart(currentDate));
    });

    renderWeek(getWeekStart(currentDate));
});
