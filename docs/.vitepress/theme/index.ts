import DefaultTheme from 'vitepress/theme'
import { h } from 'vue'
import NavBarStats from '../components/NavBarStats.vue'
import DocComments from '../components/DocComments.vue'
import './custom.css'

export default {
    extends: DefaultTheme,
    Layout() {
        return h(DefaultTheme.Layout, null, {
            'nav-bar-content-after': () => h(NavBarStats),
            'doc-after': () => h(DocComments),
            'home-features-after': () => h('div', { class: 'home-comments' }, h(DocComments))
        })
    }
}
