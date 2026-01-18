<template>
  <div class="text-container" :style="{ backgroundColor: backgroundColor }">
    <div class="label">{{ label }}:</div>
    <div class="text">{{ name }}</div>
  </div>
</template>

<script lang="ts">
import { defineComponent, onMounted, ref, computed } from "vue";
export default defineComponent({
  name: "TextNode",
  props: {
    label: {
      type: String,
      required: true,
    },
    name: {
      type: String,
      required: true,
    },
    status: {
      type: Boolean,
      default: null,
    },
  },
  setup(props) {
    const backgroundColor = computed(() => {
      if (props.status === null) {
        return "#e3f2fd"; // 默认颜色 - 浅蓝
      } else if (props.status === false) {
        return "#ffebee"; // 浅红
      } else if (props.status === true) {
        return "#e8f5e8"; // 浅绿
      }
      return "#e3f2fd";
    });
    onMounted(() => {});
    return { backgroundColor };
  },
});
</script>

<style scoped>
.text-container {
  margin: 0;
  min-width: 160px;
  height: 40px;
  cursor: pointer;
  border-radius: 6px;
  border: 1px solid rgba(0, 0, 0, 0.1);
  color: #000;
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 15px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);

  .label {
    font-size: 14px;
    font-weight: 500;
    white-space: nowrap;
    color: #333;
  }

  .text {
    font-size: 14px;
    font-weight: 600;
    white-space: nowrap;
    flex: 1;
    text-align: right;
    color: #1890ff;
  }
}

.text-container:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  transform: translateY(-1px);
}

.indicator {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  margin-right: 10px;
}
</style>
