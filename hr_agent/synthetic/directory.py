"""Справочник сотрудников: подчинённость, группы доступа, HR-партнёры."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Employee:
    """Сотрудник."""

    id: str
    name: str
    position: str
    manager_id: str | None
    hr_partner_id: str | None
    groups: frozenset[str] = field(default_factory=frozenset)
    vacation_days_left: int = 0


EMPLOYEES: dict[str, Employee] = {
    "100001": Employee(
        id="100001",
        name="Иванов Иван Иванович",
        position="Аналитик",
        manager_id="100010",
        hr_partner_id="100020",
        groups=frozenset({"employees"}),
        vacation_days_left=14,
    ),
    "100002": Employee(
        id="100002",
        name="Петрова Мария Сергеевна",
        position="Аналитик",
        manager_id="100010",
        hr_partner_id="100020",
        groups=frozenset({"employees"}),
        vacation_days_left=9,
    ),
    "100003": Employee(
        id="100003",
        name="Николаев Дмитрий Олегович",
        position="Разработчик",
        manager_id="100011",
        hr_partner_id="100020",
        groups=frozenset({"employees"}),
        vacation_days_left=28,
    ),
    "100010": Employee(
        id="100010",
        name="Сидоров Пётр Андреевич",
        position="Руководитель группы аналитики",
        manager_id="100100",
        hr_partner_id="100020",
        groups=frozenset({"employees", "managers"}),
        vacation_days_left=21,
    ),
    "100011": Employee(
        id="100011",
        name="Егорова Анна Викторовна",
        position="Руководитель группы разработки",
        manager_id="100100",
        hr_partner_id="100020",
        groups=frozenset({"employees", "managers"}),
        vacation_days_left=17,
    ),
    "100020": Employee(
        id="100020",
        name="Кузнецова Ольга Павловна",
        position="HR-партнёр",
        manager_id="100100",
        hr_partner_id=None,
        groups=frozenset({"employees", "hr"}),
        vacation_days_left=12,
    ),
    "100030": Employee(
        id="100030",
        name="Смирнов Алексей Юрьевич",
        position="Специалист по обучению",
        manager_id="100020",
        hr_partner_id="100020",
        groups=frozenset({"employees", "l&d"}),
        vacation_days_left=6,
    ),
    "100100": Employee(
        id="100100",
        name="Воронцов Сергей Иванович",
        position="Директор департамента",
        manager_id=None,
        hr_partner_id="100020",
        groups=frozenset({"employees", "managers"}),
        vacation_days_left=30,
    ),
}

# Контакты кадровой службы — общая справка, не привязанная к сотруднику
HR_SERVICE_CONTACTS: dict[str, str] = {
    "hotline": "8-800-000-00-00",
    "email": "hr@example.com",
    "office": "корпус Б, 3 этаж, кабинет 312",
    "worktime": "будни 09:00–18:00",
}
