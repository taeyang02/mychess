import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import './styles.css'
import 'chessground/assets/chessground.base.css'
import 'chessground/assets/chessground.brown.css'
import 'chessground/assets/chessground.cburnett.css'

createApp(App).use(router).mount('#app')
