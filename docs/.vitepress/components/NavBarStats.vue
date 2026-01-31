<script setup>
const repo = '600888/ems_simulate'
</script>

<template>
  <div class="github-stats">
    <a :href="`https://github.com/${repo}`" target="_blank" rel="noopener">
      <img :src="`https://img.shields.io/badge/GitHub-600888%2Fems__simulate-181717?logo=github`" alt="Repo" />
    </a>
    <a :href="`https://github.com/${repo}/releases`" target="_blank" rel="noopener">
      <img :src="`https://img.shields.io/github/v/release/${repo}?label=v&color=orange`" alt="Version" />
    </a>
    <a :href="`https://github.com/${repo}/stargazers`" target="_blank" rel="noopener">
      <img :src="`https://img.shields.io/github/stars/${repo}?style=flat&color=yellow`" alt="Stars" />
    </a>
    <a :href="`https://github.com/${repo}/network/members`" target="_blank" rel="noopener">
      <img :src="`https://img.shields.io/github/forks/${repo}?style=flat&color=blue`" alt="Forks" />
    </a>
  </div>
</template>

<style scoped>
.github-stats {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: 16px;
}

.github-stats a {
  display: flex;
  height: 20px;
}

.github-stats img {
  height: 20px;
}

/* Hide on mobile to avoid overcrowding */
@media (max-width: 768px) {
  .github-stats {
    display: none;
  }
}
</style>
