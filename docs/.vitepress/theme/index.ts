import DefaultTheme from 'vitepress/theme'
import { h } from 'vue'
import NavBarStats from '../components/NavBarStats.vue'
import './custom.css'

export default {
    extends: DefaultTheme,
    Layout() {
        return h(DefaultTheme.Layout, null, {
            'nav-bar-content-after': () => h(NavBarStats)
        })
    }
}
