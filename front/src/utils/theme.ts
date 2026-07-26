import { ref, watch } from "vue";

export type ThemeType = "light" | "dark";

const THEME_KEY = "sidebar-theme";

export const currentTheme = ref<ThemeType>(
  (localStorage.getItem(THEME_KEY) as ThemeType) || "light",
);

export const toggleTheme = () => {
  currentTheme.value = currentTheme.value === "light" ? "dark" : "light";
};

// 监听变化并保持
watch(
  currentTheme,
  (newTheme) => {
    localStorage.setItem(THEME_KEY, newTheme);
    // 同时更新 body 的 class，方便全局样式适配
    document.body.classList.toggle("theme-dark", newTheme === "dark");
    document.body.classList.toggle("theme-light", newTheme === "light");
    document.documentElement.classList.toggle("dark", newTheme === "dark");
    document.documentElement.style.colorScheme = newTheme;
  },
  { immediate: true },
);
