
### P0-INT-6: Agent 间消息总线
- **状态**: ✅ **已完成**
- **实现**:
  - 新增 `agents/message_bus.py` — MessageBus 类（内存型发布-订阅，审计日志，统计）
  - 修改 `agents/coordinator.py` — 创建共享总线，自动设置订阅关系
  - 修改 `agents/quiz_agent.py` — 出题后发布 `quiz_generated`，订阅 `ability_updated`
  - 修改 `agents/coach_agent.py` — 评分后发布 `ability_updated` + `weak_area_detected`
  - 修改 `agents/tutor_agent.py` — 订阅 `weak_area_detected`
  - 修改 `agents/headhunter_agent.py` — 接受 message_bus 参数
- **消息流**:
  - QuizAgent --quiz_generated--> CoachAgent
  - CoachAgent --ability_updated--> QuizAgent
  - CoachAgent --weak_area_detected--> TutorAgent
- **可观测性**: Console 日志 `[MessageBus] PUBLISH/DELIVER`
- **验证脚本**: `scripts/test_message_bus.py`
- **优先级**: P2
