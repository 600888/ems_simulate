declare module '*.vue' {
    import { ComponentOptions } from 'vue'
    const componentOptions: ComponentOptions
    export default componentOptions
}

/// <reference types="vite/client" />

interface Window {
    __TAURI_INTERNALS__?: Record<string, unknown>
    showSaveFilePicker?: (options?: SaveFilePickerOptions) => Promise<FileSystemFileHandle>
}

interface SaveFilePickerOptions {
    suggestedName?: string
    types?: Array<{
        description?: string
        accept: Record<string, string[]>
    }>
}

interface FileSystemFileHandle {
    createWritable(): Promise<FileSystemWritableFileStream>
}

interface FileSystemWritableFileStream extends WritableStream {
    write(data: Blob | Uint8Array): Promise<void>
    close(): Promise<void>
}
