from pathlib import Path

from backend.schemas import SkillInfo


ROOT_DIR = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT_DIR / "skills"


SKILL_FILES = {
    "requirement": ("requirements-analysis", "需求分析 Skill", "requirements-analysis.skill.md"),
    "design": ("technical-design", "方案设计 Skill", "technical-design.skill.md"),
    "code": ("code-change", "代码生成 Skill", "code-change.skill.md"),
    "test": ("test-design", "测试生成 Skill", "test-design.skill.md"),
    "review": ("code-review", "代码评审 Skill", "code-review.skill.md"),
    "delivery": ("delivery-summary", "交付总结 Skill", "delivery-summary.skill.md"),
}


def get_skill_info(stage_id: str) -> SkillInfo:
    skill_id, name, filename = SKILL_FILES[stage_id]
    return SkillInfo(id=skill_id, name=name, path=f"skills/{filename}")


def read_skill(stage_id: str) -> str:
    _, _, filename = SKILL_FILES[stage_id]
    path = SKILLS_DIR / filename
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")
