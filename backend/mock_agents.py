from backend.schemas import Pipeline
from backend.skills import read_skill


def _latest_reject_reason(pipeline: Pipeline, stage_id: str) -> str:
    for record in reversed(pipeline.reviewHistory):
        if record.stageId == stage_id and record.decision == "reject":
            return record.reason
    return ""


def generate_requirement(pipeline: Pipeline) -> str:
    return "\n\n".join(
        [
            "用户故事：作为任务管理系统用户，我希望可以按高、中、低优先级筛选任务，以便优先处理重要事项。",
            "功能范围：在任务列表上方增加优先级筛选控件，支持全部、高、中、低四种选项。",
            "验收标准：切换筛选项后，列表只显示匹配任务；选择全部时恢复完整列表；无匹配任务时显示空状态。",
            f"原始需求：{pipeline.requirement}",
        ]
    )


def generate_design(pipeline: Pipeline) -> str:
    reject_reason = _latest_reject_reason(pipeline, "design")
    review_note = (
        f"\n\n针对上次驳回补充：已加入“{reject_reason}”处理，空状态会显示提示文案，并保留重置筛选入口。"
        if reject_reason
        else ""
    )
    return "\n\n".join(
        [
            "技术方案：在任务列表顶部增加 segmented filter 控件，筛选状态由前端维护。",
            "涉及模块：TaskToolbar、TaskList、Task 数据结构、空状态组件。",
            "数据结构：Task 增加 priority 字段，可取 high / medium / low。",
            "UI 变化：新增优先级筛选按钮组，并在无结果时展示空状态。",
            "风险点：筛选条件需要与搜索条件共存，避免状态互相覆盖。",
        ]
    ) + review_note


def generate_code(pipeline: Pipeline) -> str:
    return "\n".join(
        [
            "修改文件列表：",
            "- src/components/TaskToolbar.tsx",
            "- src/components/TaskList.tsx",
            "- src/types/task.ts",
            "",
            "Diff 摘要：",
            "+ 为 Task 类型增加 priority 字段。",
            "+ 新增 priorityFilter 状态，并按筛选条件过滤任务列表。",
            "+ 增加空状态提示：当前优先级下暂无任务。",
            "",
            "关键实现：筛选逻辑保持在列表层，后续可平滑迁移到 API 查询参数。",
        ]
    )


def generate_test(pipeline: Pipeline) -> str:
    return "\n".join(
        [
            "测试用例：",
            "1. 默认显示全部任务。",
            "2. 选择高优先级后，只显示 high 任务。",
            "3. 选择中/低优先级后，列表正确更新。",
            "4. 无匹配任务时显示空状态。",
            "",
            "模拟测试结果：4/4 通过。",
            "未覆盖风险：暂未覆盖筛选条件与搜索关键词组合的边界情况。",
        ]
    )


def generate_review(pipeline: Pipeline) -> str:
    return "\n".join(
        [
            "评审结论：建议交付。",
            "",
            "正确性：筛选逻辑与需求一致，默认态和空状态均已覆盖。",
            "稳定性：当前方案只影响任务列表展示层，不改变存储结构。",
            "代码质量建议：后续可将 priority 选项抽成常量，避免多处硬编码。",
            "风险列表：与搜索、排序组合使用时需要补充集成测试。",
        ]
    )


def generate_delivery(pipeline: Pipeline) -> str:
    return "\n".join(
        [
            "交付总结：已完成任务管理系统按优先级筛选任务的功能设计与交付材料生成。",
            "",
            "变更摘要：新增优先级筛选控件、任务 priority 字段、空状态提示和筛选逻辑。",
            "测试摘要：已覆盖默认展示、高/中/低优先级筛选、无匹配任务空状态。",
            "",
            "MR 描述草稿：",
            "本次变更新增任务优先级筛选能力，用户可以在任务列表中快速查看不同优先级的任务。实现包含筛选控件、列表过滤逻辑和空状态提示。",
            "",
            "后续建议：补充搜索 + 优先级组合筛选的集成测试。",
        ]
    )


GENERATORS = {
    "requirement": generate_requirement,
    "design": generate_design,
    "code": generate_code,
    "test": generate_test,
    "review": generate_review,
    "delivery": generate_delivery,
}


def run_mock_agent(stage_id: str, pipeline: Pipeline) -> str:
    # The skill text is read now so the future LLM path can reuse the same stage contract.
    read_skill(stage_id)
    return GENERATORS[stage_id](pipeline)
