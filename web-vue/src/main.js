import { createApp } from 'vue'
import App from './App.vue'
import 'katex/dist/katex.min.css'
import './styles/global.css'

// 创建 Vue 应用实例
const app = createApp(App)

// 挂载到 DOM
app.mount('#app')
