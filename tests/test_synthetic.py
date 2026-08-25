import pytest

from hr_agent.synthetic import api
from hr_agent.synthetic.kb import rank


async def test_employee_with_history():
    records = await api.training_history("100001")
    assert {r.course_id for r in records} == {19, 21, 17}
    assert next(r for r in records if r.course_id == 19).status == "completed"


async def test_manager_and_groups():
    assert await api.manager_of("100001") == "100010"
    assert await api.manager_of("100100") is None
    assert "hr" in await api.get_groups("100020")
    assert "hr" not in await api.get_groups("100001")


async def test_unknown_employee_raises():
    with pytest.raises(api.ApiNotFound):
        await api.get_employee("999999")
    with pytest.raises(api.ApiNotFound):
        await api.training_history("999999")


async def test_assignment_present_and_absent():
    found = await api.assignment("100001", 17)
    assert found is not None
    assert "резерв" in found.reason

    assert await api.assignment("100002", 17) is None


async def test_find_course_by_substring():
    assert [c.id for c in await api.find_course("скрам")] == [17]
    assert {c.id for c in await api.find_course("основы")} == {18, 22}
    assert await api.find_course("не существует") == []


async def test_hr_partner_resolution():
    partner = await api.hr_partner("100001")
    assert partner is not None
    assert partner.id == "100020"
    # у самого HR-партнёра закреплённого партнёра нет
    assert await api.hr_partner("100020") is None


def test_kb_ranking_prefers_topical_instruction():
    ranked = rank("почему мне назначен курс", limit=5)
    assert ranked[0][0].id == "KB-001"
    assert ranked[0][1] > ranked[1][1]


def test_kb_ranking_empty_for_offtopic():
    assert rank("прогноз погоды на выходные", limit=5) == []
