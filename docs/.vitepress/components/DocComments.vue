<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { useData, useRoute } from 'vitepress'

const comments = ref<HTMLElement | null>(null)
const route = useRoute()
const { isDark } = useData()

function loadComments() {
  if (!comments.value) return

  // Utterances reads the current pathname when its script runs. Recreate it
  // after client-side navigation so each document has its own issue.
  comments.value.replaceChildren()
  const script = document.createElement('script')
  script.src = 'https://utteranc.es/client.js'
  script.setAttribute('repo', '600888/ems_simulate')
  script.setAttribute('issue-term', 'pathname')
  script.setAttribute('theme', isDark.value ? 'github-dark' : 'github-light')
  script.setAttribute('crossorigin', 'anonymous')
  script.async = true
  comments.value.appendChild(script)
}

onMounted(loadComments)

watch(() => route.path, async () => {
  await nextTick()
  loadComments()
})

watch(isDark, (dark) => {
  const frame = comments.value?.querySelector<HTMLIFrameElement>('.utterances-frame')
  frame?.contentWindow?.postMessage(
    { type: 'set-theme', theme: dark ? 'github-dark' : 'github-light' },
    'https://utteranc.es'
  )
})
</script>

<template>
  <section class="doc-comments" aria-label="文档评论">
    <h2>评论与讨论</h2>
    <div ref="comments" />
  </section>
</template>
