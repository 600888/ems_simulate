<template>
  <el-container>
    <Sidebar />
  </el-container>
</template>

<script>
import Sidebar from "./views/SideBar.vue";

export default {
  name: "App",
  components: {
    Sidebar,
  },
};
</script>

<style lang="scss" scoped></style>
