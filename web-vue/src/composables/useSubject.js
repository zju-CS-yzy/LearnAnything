import { ref, readonly } from 'vue'

// 全局学科状态（单例）
const currentSubject = ref('generic')
const subjects = ref([])
const subjectsLoaded = ref(false)

// LA-SUBJECT-PERSIST: 记住每个用户上次选择的学科（按 user_id 分别记录）
const LAST_SUBJECTS_KEY = 'la_last_subjects'
let subjectDirty = false  // 本次会话是否已显式选择过学科（防止列表刷新覆盖用户选择）

function currentUserId() {
  try {
    const saved = localStorage.getItem('la_current_user')
    if (saved) return JSON.parse(saved).user_id || 'default'
  } catch { /* ignore */ }
  return 'default'
}

function loadLastSubjects() {
  try {
    return JSON.parse(localStorage.getItem(LAST_SUBJECTS_KEY) || '{}')
  } catch { return {} }
}

function persistSubject(id) {
  try {
    const map = loadLastSubjects()
    map[currentUserId()] = id
    localStorage.setItem(LAST_SUBJECTS_KEY, JSON.stringify(map))
  } catch { /* ignore */ }
}

export function useSubject() {
  function setSubject(id) {
    subjectDirty = true
    currentSubject.value = id
    persistSubject(id)
  }

  function setSubjects(list) {
    subjects.value = list
    subjectsLoaded.value = true
    // LA-SUBJECT-PERSIST: 恢复该用户上次选择的学科（仅当本次会话尚未显式选择过）
    if (!subjectDirty) {
      const saved = loadLastSubjects()[currentUserId()]
      if (saved && list.some(s => s.id === saved)) {
        currentSubject.value = saved
        console.log('[useSubject] 恢复上次选择的学科:', saved)
      }
    }
  }

  function addSubject(sub) {
    subjects.value.push(sub)
  }

  function removeSubject(id) {
    subjects.value = subjects.value.filter(s => s.id !== id)
    if (currentSubject.value === id) {
      const next = subjects.value[0]?.id || 'generic'
      subjectDirty = true
      currentSubject.value = next
      persistSubject(next)
    }
  }

  return {
    currentSubject: readonly(currentSubject),
    subjects: readonly(subjects),
    subjectsLoaded: readonly(subjectsLoaded),
    setSubject,
    setSubjects,
    addSubject,
    removeSubject,
  }
}
