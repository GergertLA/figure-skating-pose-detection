function validateFile() {
    const fileInput = document.getElementById('original_video');
    const file = fileInput.files[0];
    const allowedTypes = ['video/mp4', 'video/avi', 'video/mov', 'video/wmv']; // Разрешенные типы видеофайлов

    if (file && !allowedTypes.includes(file.type)) {
        alert('Пожалуйста, загрузите только видеофайлы (MP4, AVI, MOV, WMV).');
        return false; // Останавливаем отправку формы
    }
    return true; // Продолжаем отправку формы
}

function showProcessingMessage() {
    if (!validateFile()) {
        return false; // Если файл не прошел проверку, не показываем сообщение о обработке
    }

    // Блокируем все кнопки на странице
    const buttons = document.querySelectorAll('button');
    buttons.forEach(button => {
        button.disabled = true;
    });

    // Блокируем кнопку "Выберите файл"
    const fileInputButton = document.querySelector('.custom-file-input');
    if (fileInputButton) {
        fileInputButton.disabled = true;
        fileInputButton.style.backgroundColor = '#cccccc'; // Меняем цвет, чтобы показать, что кнопка заблокирована
        fileInputButton.style.cursor = 'not-allowed'; // Меняем курсор
    }

    // Показываем сообщение о обработке
    document.getElementById("processing-container").style.display = "block";
    return true; // Продолжаем отправку формы
}

function loadAthletes(groupId) {
    const athleteSelect = document.getElementById('athlete_id');
    athleteSelect.innerHTML = '<option value="">Загрузка...</option>';

    fetch(`/athletes_by_group/${groupId}`)
        .then(response => response.json())
        .then(data => {
            athleteSelect.innerHTML = '<option value="">Выберите спортсмена</option>';
            data.forEach(athlete => {
                const option = document.createElement('option');
                option.value = athlete.athlete_id;
                option.textContent = `${athlete.athlete_surname} ${athlete.athlete_name}`;
                athleteSelect.appendChild(option);
            });
        })
        .catch(error => {
            athleteSelect.innerHTML = '<option value="">Сначала выберите группу</option>';
            console.error('Error loading athletes:', error);
        });
}

function updateFileName() {
    const fileInput = document.getElementById('original_video');
    const fileNameDisplay = document.getElementById('file-name');
    if (fileInput.files.length > 0) {
        fileNameDisplay.textContent = fileInput.files[0].name;
    } else {
        fileNameDisplay.textContent = "Файл не выбран";
    }
}

// Автоматически заполняем поля группы и спортсмена, если они переданы
window.onload = function() {
    const groupId = "{{ group_id }}";
    const athleteId = "{{ athlete_id }}";

    if (groupId && athleteId) {
        document.getElementById('group_id').value = groupId;
        loadAthletes(groupId);

        // Ждем, пока загрузятся спортсмены, и затем выбираем нужного
        setTimeout(() => {
            document.getElementById('athlete_id').value = athleteId;
        }, 500);
    } else {
        // Если group_id и athlete_id не переданы, устанавливаем значения по умолчанию
        document.getElementById('group_id').value = "";
        document.getElementById('athlete_id').innerHTML = '<option value="">Выберите спортсмена</option>';
    }

    // Инициализация отображения имени файла
    updateFileName();
};