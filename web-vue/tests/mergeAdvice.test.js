import test from 'node:test'
import assert from 'node:assert/strict'
import { advisorLabel, isBulkEligible, recommendationDraft } from '../src/components/graph/merge-review/mergeAdvice.js'

test('ready merge advice preselects a draft without reviewing the candidate', () => {
  const candidate = {
    right: '检索增强生成', advisor_status: 'ready', decision: null,
    advisor: { decision: 'MERGE', confidence: 0.96, canonical_name: '检索增强生成' },
  }
  assert.deepEqual(recommendationDraft(candidate), {
    decision: 'merge', canonicalName: '检索增强生成', relationDecision: '',
  })
  assert.equal(candidate.decision, null)
  assert.equal(advisorLabel(candidate), '建议合并')
  assert.equal(isBulkEligible(candidate), true)
})

test('conflicted advice is neither preselected nor bulk eligible', () => {
  const candidate = {
    advisor_status: 'ready', advisor_conflict: true,
    advisor: { decision: 'SEPARATE', confidence: 0.99 },
  }
  assert.equal(recommendationDraft(candidate), null)
  assert.equal(advisorLabel(candidate), '建议冲突')
  assert.equal(isBulkEligible(candidate), false)
})

test('separate advice maps the directional relation', () => {
  const candidate = {
    advisor_status: 'ready', advisor_conflict: false,
    advisor: {
      decision: 'SEPARATE', confidence: 0.92,
      relation_if_separate: 'LEFT_NARROWER_THAN_RIGHT',
    },
  }
  assert.deepEqual(recommendationDraft(candidate), {
    decision: 'separate', canonicalName: '',
    relationDecision: 'LEFT_NARROWER_THAN_RIGHT',
  })
})
