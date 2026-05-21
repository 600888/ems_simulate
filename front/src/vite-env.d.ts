declare module '*.vue' {
    import { ComponentOptions } from 'vue'
    const componentOptions: ComponentOptions
    export default componentOptions
}

/// <reference types="vite/client" />

interface Window {
    __TAURI_INTERNALS__?: Record<string, unknown>
}
