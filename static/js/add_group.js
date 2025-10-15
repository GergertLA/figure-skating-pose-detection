function addAthlete() {
    const container = document.getElementById('athletes-container');
    const newAthlete = document.createElement('div');
    newAthlete.className = 'new-athlete';
    newAthlete.innerHTML = `
        <label for="surname">Фамилия:</label>
        <input type="text" name="surname[]" required>
        <label for="name">Имя:</label>
        <input type="text" name="name[]" required>
        <label for="patronymic">Отчество (если есть):</label>
        <input type="text" name="patronymic[]">
        <label for="username">Имя пользователя:</label>
        <input type="text" name="username[]" required>
        <label for="password">Пароль:</label>
        <input type="password" name="password[]" required>
    `;
    container.appendChild(newAthlete);
}

function validateForm() {
    const checkboxes = document.querySelectorAll('input[name="athletes[]"]:checked');
    const newAthletes = document.querySelectorAll('.new-athlete');
    const errorMessage = document.getElementById('error-message');

    if (checkboxes.length === 0 && newAthletes.length === 0) {
        errorMessage.style.display = 'block';
        return false; // Остановить отправку формы
    } else {
        errorMessage.style.display = 'none';
        return true; // Продолжить отправку формы
    }
}
