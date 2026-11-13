import { createRouter, createWebHistory } from 'vue-router'
import LabHome from './views/LabHome.vue'
import AnalysisView from './views/AnalysisView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: LabHome },
    { path: '/analysis/:id', name: 'analysis', component: AnalysisView, props: true },
  ],
})
