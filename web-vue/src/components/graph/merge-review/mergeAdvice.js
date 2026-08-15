export function recommendationDraft(candidate) {
  const advisor = candidate?.advisor
  if (!advisor || candidate?.advisor_status !== 'ready' || candidate?.advisor_conflict || advisor.needs_more_context) return null
  if (!['MERGE', 'SEPARATE'].includes(advisor.decision)) return null
  return {
    decision: advisor.decision === 'MERGE' ? 'merge' : 'separate',
    canonicalName: advisor.decision === 'MERGE'
      ? advisor.canonical_name || candidate.right
      : '',
    relationDecision: advisor.decision === 'SEPARATE' && advisor.relation_if_separate !== 'NONE'
      ? advisor.relation_if_separate || ''
      : '',
  }
}

export function advisorLabel(candidate) {
  if (candidate?.advisor_conflict) return '建议冲突'
  if (candidate?.advisor_status === 'failed') return '建议失败'
  if (candidate?.advisor_status === 'pending') return '待生成建议'
  const decision = candidate?.advisor?.decision
  if (decision === 'MERGE') return '建议合并'
  if (decision === 'SEPARATE') return '建议分离'
  return candidate?.advisor_status === 'ready' ? '证据不足' : '未生成建议'
}

export function isBulkEligible(candidate, threshold = 0.9) {
  const advisor = candidate?.advisor || {}
  return !candidate?.decision
    && candidate?.advisor_status === 'ready'
    && !candidate?.advisor_conflict
    && !advisor.needs_more_context
    && !(advisor.conflicts || []).length
    && ['MERGE', 'SEPARATE'].includes(advisor.decision)
    && Number(advisor.confidence || 0) >= threshold
}
