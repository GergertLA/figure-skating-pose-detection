document.addEventListener('DOMContentLoaded', function() {
    // Обработка переключения между разделами
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const sectionId = this.getAttribute('data-section');
            if (sectionId) {
                // Скрыть все разделы
                document.querySelectorAll('.content').forEach(content => {
                    content.classList.remove('active');
                });
                
                // Показать выбранный раздел
                document.getElementById(sectionId).classList.add('active');
            }
        });
    });
});

function showSection(sectionId) {
    // Скрываем все разделы
    document.querySelectorAll('.content').forEach(section => {
        section.classList.remove('active');
    });

    // Показываем выбранный раздел
    document.getElementById(sectionId).classList.add('active');
}

function toggleAthletes(groupId) {
    const athletesDiv = document.getElementById('athletes-' + groupId);
    if (athletesDiv.style.display === 'none' || athletesDiv.style.display === '') {
        athletesDiv.style.display = 'table-row';
    } else {
        athletesDiv.style.display = 'none';
    }
}

function showEditForm(athleteId) {
    const editForm = document.getElementById(`edit-form-${athleteId}`);
    if (editForm.style.display === 'none') {
        editForm.style.display = 'block';
    } else {
        editForm.style.display = 'none';
    }
}

function confirmDelete(athleteId) {
    if (confirm('Удалить спортсмена?')) {
        document.getElementById(`delete-form-${athleteId}`).submit();
    }
}

function showEditCoachForm(coachId) {
    const editForm = document.getElementById(`edit-coach-form-${coachId}`);
    if (editForm.style.display === 'none') {
        editForm.style.display = 'block';
    } else {
        editForm.style.display = 'none';
    }
}

function hideEditCoachForm(coachId) {
    const editForm = document.getElementById(`edit-coach-form-${coachId}`);
    editForm.style.display = 'none';
}

async function confirmDeleteCoach(coachId) {
    const response = await fetch(`/check-coach-groups/${coachId}`);
    const data = await response.json();
    
    if (data.has_groups) {
        // Показываем формы для переноса групп
        const reassignForms = document.getElementById(`reassign-forms-${coachId}`);
        reassignForms.style.display = 'block';
        
        // Скрываем другие элементы (если нужно)
        const editForm = document.getElementById(`edit-coach-form-${coachId}`);
        if (editForm) editForm.style.display = 'none';
    } else {
        // Если групп нет, сразу удаляем тренера
        if (confirm('Удалить тренера?')) {
            document.getElementById(`delete-form-${coachId}`).submit();
        }
    }
}

async function submitAllReassignments(coachId) {
    const groupAssignments = {};
    const forms = document.querySelectorAll(`#reassign-forms-${coachId} .reassign-form`);
    
    // Проверяем, что для всех групп выбран новый тренер
    let allSelected = true;
    forms.forEach(form => {
        const select = form.querySelector('.new-coach-select');
        if (!select.value) {
            allSelected = false;
            select.style.border = '1px solid red';
        } else {
            select.style.border = '';
        }
    });

    if (!allSelected) {
        alert('Пожалуйста, выберите нового тренера для всех групп.');
        return;
    }

    // Собираем данные для отправки
    forms.forEach(form => {
        const groupId = form.getAttribute('data-group-id');
        const newCoachId = form.querySelector('.new-coach-select').value;
        groupAssignments[groupId] = newCoachId;
    });

    try {
        const response = await fetch(`/reassign_all_groups/${coachId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ group_assignments: groupAssignments }),
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            // После успешного переноса групп удаляем тренера
            const deleteResponse = await fetch(`/delete_coach/${coachId}`, {
                method: 'POST',
            });
            
            if (deleteResponse.ok) {
                alert('Все группы перенесены, тренер удален.');
                location.reload();
            } else {
                alert('Ошибка при удалении тренера.');
            }
        } else {
            alert('Ошибка при переносе групп: ' + data.message);
        }
    } catch (error) {
        console.error('Ошибка:', error);
        alert('Произошла ошибка при выполнении операции.');
    }
}

function hideReassignForms(coachId) {
    const reassignForms = document.getElementById(`reassign-forms-${coachId}`);
    if (reassignForms) {
        reassignForms.style.display = 'none';
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

function showEditGroupForm(groupId) {
    const editForm = document.getElementById(`edit-group-form-${groupId}`);
    if (editForm.style.display === 'none') {
        editForm.style.display = 'block';
    } else {
        editForm.style.display = 'none';
    }
}

function hideEditGroupForm(groupId) {
    const editForm = document.getElementById(`edit-group-form-${groupId}`);
    editForm.style.display = 'none';
}

function confirmDeleteGroup(groupId) {
    if (confirm('Удалить группу?')) {
        document.getElementById(`delete-form-${groupId}`).submit();
    }
}

function searchCoach() {
    const searchTerm = document.getElementById('searchCoachInput').value.toLowerCase();
    const coachTables = document.querySelectorAll('.coach-table');

    coachTables.forEach(table => {
        const coachName = table.querySelector('th').textContent.toLowerCase();
        if (coachName.includes(searchTerm)) {
            table.style.display = 'block';
        } else {
            table.style.display = 'none';
        }
    });
}

function searchGroup() {
    const searchTerm = document.getElementById('searchGroupInput').value.toLowerCase();
    const groupRows = document.querySelectorAll('#groups-section table tbody tr.group-row');

    groupRows.forEach(row => {
        const groupName = row.querySelector('td:first-child').textContent.toLowerCase();
        if (groupName.includes(searchTerm)) {
            // Показываем группу
            row.style.display = 'table-row';
            // Показываем связанные строки (тренера и спортсменов)
            const nextRow = row.nextElementSibling;
            if (nextRow && nextRow.classList.contains('group-details')) {
                nextRow.style.display = 'table-row';
            }
        } else {
            // Скрываем группу
            row.style.display = 'none';
            // Скрываем связанные строки (тренера и спортсменов)
            const nextRow = row.nextElementSibling;
            if (nextRow && nextRow.classList.contains('group-details')) {
                nextRow.style.display = 'none';
            }
        }
    });
}

const athleteGroups = JSON.parse('{{ athlete_groups_json | safe }}');