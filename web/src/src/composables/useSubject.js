import { ref, readonly } from 'vue'

// 全局学科状态（单例）
const currentSubject = ref('generic')
const subjects = ref([])
const subjectsLoaded = ref(false)

export function useSubject() {
  function setSubject(id) {
    currentSubject.value = id
  }

  function setSubjects(list) {
    subjects.value = list
    subjectsLoaded.value = true
  }

  function addSubject(sub) {
    subjects.value.push(sub)
  }

  function removeSubject(id) {
    subjects.value = subjects.value.filter(s => s.id !== id)
    if (currentSubject.value === id) {
      currentSubject.value = subjects.value[0]?.id || 'generic'
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
